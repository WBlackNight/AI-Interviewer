"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  FrameAssembler,
  base64ToBytes,
  bytesToBase64,
  float32ToInt16Bytes,
  int16BytesToFloat32,
  resampleToTarget,
  TARGET_SAMPLE_RATE,
} from "@/lib/pcm";
import type { VoiceEvent } from "@/lib/types";

export type VoiceStatus =
  | "idle"          // 未开启
  | "unsupported"   // 浏览器不支持
  | "requesting"    // 正在申请麦克风
  | "ready"         // 采集中
  | "denied"        // 用户拒绝授权（仍可用文字作答）
  | "error";        // 设备断开等

/** 有界播放缓冲上限：超出即丢最旧数据，保证延迟不随时间增长。 */
const PLAYBACK_MAX_SECONDS = 6;

/**
 * 打断检测窗：**独立于 100ms 网络帧**。
 * 用 100ms 帧做检测会先耗尽 300ms 预算再留处理时间，无法达到 P95<300ms 的目标。
 */
const BARGE_IN_WINDOW_MS = 20;
/** 能量阈值：初值，必须用真实设备实测调参（评审要求，不得写成"已够用"）。 */
const BARGE_IN_RMS = 0.06;
/** 打断后的静默冷却，避免一句话被拆成多次打断。 */
const BARGE_IN_COOLDOWN_MS = 400;

interface Options {
  turnId: string | null;
  enabled: boolean;
  sendVoice: (payload: object) => boolean;
  registerVoiceSink: (sink: ((event: VoiceEvent) => void) | null) => void;
}

export function useVoiceChannel({ turnId, enabled, sendVoice, registerVoiceSink }: Options) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [message, setMessage] = useState<string>("");
  const [playing, setPlaying] = useState(false);
  const [level, setLevel] = useState(0);
  const [bargeInCount, setBargeInCount] = useState(0);

  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const captureRef = useRef<AudioWorkletNode | null>(null);
  const playbackRef = useRef<AudioWorkletNode | null>(null);
  const nativeBufferRef = useRef(new Float32Array(0));
  const assemblerRef = useRef(new FrameAssembler());
  const seqRef = useRef(0);
  const utteranceRef = useRef<string | null>(null);
  const playingRef = useRef(false);
  const lastBargeInRef = useRef(0);
  const sendRef = useRef(sendVoice);
  const turnRef = useRef(turnId);
  const probeRef = useRef(new Float32Array(0));

  sendRef.current = sendVoice;
  turnRef.current = turnId;

  /** 清空本地播放缓冲 —— 打断时**先本地静音**，不等服务端 ACK。 */
  const clearPlayback = useCallback(() => {
    playbackRef.current?.port.postMessage({ type: "clear" });
    playingRef.current = false;
    utteranceRef.current = null;
    setPlaying(false);
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    captureRef.current?.disconnect();
    captureRef.current = null;
    playbackRef.current?.disconnect();
    playbackRef.current = null;
    const context = contextRef.current;
    contextRef.current = null;
    if (context && context.state !== "closed") void context.close();
    assemblerRef.current.reset();
    nativeBufferRef.current = new Float32Array(0);
    probeRef.current = new Float32Array(0);
    seqRef.current = 0;
    playingRef.current = false;
    utteranceRef.current = null;
    setPlaying(false);
    setLevel(0);
    setStatus("idle");
    setMessage("");
  }, []);

  const triggerBargeIn = useCallback(
    (reason: "speech" | "manual") => {
      const now = Date.now();
      if (reason === "speech" && now - lastBargeInRef.current < BARGE_IN_COOLDOWN_MS) return;
      lastBargeInRef.current = now;
      clearPlayback();
      const utteranceId = utteranceRef.current;
      sendRef.current({
        type: "interrupt",
        ...(utteranceId ? { utterance_id: utteranceId } : {}),
      });
      if (reason === "speech") setBargeInCount((value) => value + 1);
    },
    [clearPlayback]
  );

  /** 处理每个采集块：能量检测（打断）→ 重组 → 重采样 → 成帧上行。 */
  const onCaptureBlock = useCallback(
    (block: Float32Array) => {
      const context = contextRef.current;

      // --- 打断检测：独立 20ms 窗口，与网络帧解耦
      let energy = 0;
      for (let i = 0; i < block.length; i += 1) energy += block[i] * block[i];
      const rms = Math.sqrt(energy / Math.max(block.length, 1));
      setLevel(Math.min(rms * 4, 1));

      if (playingRef.current) {
        const probe = probeRef.current;
        const merged = new Float32Array(probe.length + block.length);
        merged.set(probe, 0);
        merged.set(block, probe.length);
        const sourceRate = context?.sampleRate ?? TARGET_SAMPLE_RATE;
        const windowSamples = Math.max(1, Math.round((sourceRate * BARGE_IN_WINDOW_MS) / 1000));
        if (merged.length >= windowSamples) {
          if (rms >= BARGE_IN_RMS) triggerBargeIn("speech");
          probeRef.current = new Float32Array(0);
        } else {
          probeRef.current = merged;
        }
      }

      // --- 重采样与成帧：在**原生采样率**上攒满 100ms 再转换，
      //     避免逐块重采样在块边界产生不连续。
      const sourceRate = context?.sampleRate ?? TARGET_SAMPLE_RATE;
      const need = Math.round(sourceRate * 0.1);
      const pending = nativeBufferRef.current;
      const combined = new Float32Array(pending.length + block.length);
      combined.set(pending, 0);
      combined.set(block, pending.length);

      let offset = 0;
      while (combined.length - offset >= need) {
        const slice = combined.subarray(offset, offset + need);
        const resampled = resampleToTarget(slice, sourceRate, TARGET_SAMPLE_RATE);
        for (const frame of assemblerRef.current.push(resampled)) {
          const turn = turnRef.current;
          if (!turn) continue;
          const ok = sendRef.current({
            type: "audio",
            turn_id: turn,
            seq: seqRef.current,
            format: "pcm_s16le",
            sample_rate: TARGET_SAMPLE_RATE,
            channels: 1,
            data: bytesToBase64(float32ToInt16Bytes(frame)),
          });
          // 只有发送成功才推进序号：否则服务端会判定为序号缺口。
          if (ok) seqRef.current += 1;
        }
        offset += need;
      }
      nativeBufferRef.current = combined.slice(offset);
    },
    [triggerBargeIn]
  );

  const start = useCallback(async () => {
    if (status === "ready" || status === "requesting") return;
    if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia
        || typeof AudioWorkletNode === "undefined") {
      setStatus("unsupported");
      setMessage("当前浏览器不支持语音采集，可继续使用文字作答。");
      return;
    }
    setStatus("requesting");
    setMessage("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      streamRef.current = stream;
      // 设备被拔出/被系统回收：release 资源并提示回退文字。
      stream.getAudioTracks().forEach((track) =>
        track.addEventListener("ended", () => {
          stop();
          setStatus("error");
          setMessage("麦克风已断开，可继续使用文字作答。");
        })
      );

      const context = new AudioContext();
      await context.audioWorklet.addModule("/worklets/voice-processor.js");
      const source = context.createMediaStreamSource(stream);
      const capture = new AudioWorkletNode(context, "capture-processor");
      capture.port.onmessage = (event) => onCaptureBlock(event.data as Float32Array);
      // 不接 destination：否则会自听回授。
      source.connect(capture);

      const playback = new AudioWorkletNode(context, "playback-processor");
      playback.port.postMessage({
        type: "config",
        maxSamples: Math.round(context.sampleRate * PLAYBACK_MAX_SECONDS),
      });
      playback.connect(context.destination);

      contextRef.current = context;
      captureRef.current = capture;
      playbackRef.current = playback;
      assemblerRef.current.reset();
      nativeBufferRef.current = new Float32Array(0);
      seqRef.current = 0;
      setStatus("ready");
    } catch (error) {
      const denied = error instanceof DOMException
        && (error.name === "NotAllowedError" || error.name === "SecurityError");
      setStatus(denied ? "denied" : "error");
      setMessage(denied ? "未获得麦克风授权，可继续使用文字作答。" : "麦克风初始化失败，可继续使用文字作答。");
    }
  }, [onCaptureBlock, status, stop]);

  // 注册音频下行消费者
  useEffect(() => {
    if (!enabled) {
      registerVoiceSink(null);
      return;
    }
    const sink = (event: VoiceEvent) => {
      switch (event.type) {
        case "tts_chunk": {
          const worklet = playbackRef.current;
          const context = contextRef.current;
          if (!worklet || !context) return;
          // 服务端每个 utterance 的 seq 独立递增；这里只丢弃**已取消** utterance 的迟到包。
          if (utteranceRef.current && utteranceRef.current !== event.utterance_id) {
            // 迟到的旧 utterance：直接丢弃，不进入播放器。
            return;
          }
          utteranceRef.current = event.utterance_id;
          const bytes = base64ToBytes(event.data);
          const samples = int16BytesToFloat32(bytes);
          const resampled = resampleToTarget(samples, event.sample_rate, context.sampleRate);
          worklet.port.postMessage({ type: "push", samples: resampled });
          if (!playingRef.current) {
            playingRef.current = true;
            setPlaying(true);
          }
          break;
        }
        case "tts_end":
          if (utteranceRef.current === event.utterance_id) {
            playingRef.current = false;
            utteranceRef.current = null;
            setPlaying(false);
          }
          break;
        case "barge_in_ack":
          // 服务端确认取消：本地缓冲再清一次，兜住在途分片。
          clearPlayback();
          break;
        case "voice_empty":
          setMessage("未识别到有效语音，请重说或改用文字。");
          break;
        case "voice_error":
          setMessage("识别服务异常，可改用文字作答。");
          break;
        case "voice_gap":
          setMessage("音频流出现缺口，已重置本段缓冲。");
          break;
        default:
          break;
      }
    };
    registerVoiceSink(sink);
    return () => registerVoiceSink(null);
  }, [clearPlayback, enabled, registerVoiceSink]);

  // 切换题目/轮次：序号与缓冲重置，避免把上一轮的音频拼到新一轮。
  useEffect(() => {
    seqRef.current = 0;
    assemblerRef.current.reset();
    nativeBufferRef.current = new Float32Array(0);
    probeRef.current = new Float32Array(0);
  }, [turnId]);

  useEffect(() => () => stop(), [stop]);

  return {
    status,
    message,
    playing,
    level,
    bargeInCount,
    start,
    stop,
    /** 手动打断（用户点按钮）或由 UI 触发。 */
    interrupt: () => triggerBargeIn("manual"),
  };
}
