"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAccess } from "@/lib/access";
import { snapshotStatus } from "@/lib/interview-status";
import type { ChatMessage, QuestionEvent, ScoreEvent, VoiceEvent, WireEvent } from "@/lib/types";

const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE ?? "ws://localhost:8000";
export type SessionStatus = "connecting" | "active" | "finished" | "cancelled" | "error";
interface PendingAnswer {
  type: "answer"; message_id: string; turn_id: string; version: number; text: string; code?: string;
}

/** 语音下行事件的订阅者（由 useVoiceChannel 注册）。 */
export type VoiceSink = (event: VoiceEvent) => void;

const VOICE_EVENT_TYPES = new Set([
  "asr_partial", "asr_final", "tts_chunk", "tts_end", "barge_in_ack",
  "voice_gap", "voice_empty", "voice_error", "voice_cancelled",
]);

export function useInterviewSession(interviewId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<SessionStatus>("connecting");
  const [currentState, setCurrentState] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState<QuestionEvent | null>(null);
  const [lastScore, setLastScore] = useState<ScoreEvent | null>(null);
  const [scores, setScores] = useState<ScoreEvent[]>([]);
  const [pending, setPending] = useState(false);
  // 语音字幕：partial 覆盖显示，final 定稿。
  const [subtitle, setSubtitle] = useState<{ partial: string; final: string }>({
    partial: "", final: "",
  });
  const wsRef = useRef<WebSocket | null>(null);
  const questionRef = useRef<QuestionEvent | null>(null);
  const versionRef = useRef(0);
  const pendingRef = useRef<PendingAnswer | null>(null);
  const voiceSinkRef = useRef<VoiceSink | null>(null);
  const messageSeq = useRef(0);
  const lastSeq = useRef(-1);
  const pendingKey = `interview:${interviewId}:pending`;

  const registerVoiceSink = useCallback((sink: VoiceSink | null) => {
    voiceSinkRef.current = sink;
  }, []);

  /** 发送语音相关上行消息（audio / audio_end / interrupt）。 */
  const sendVoice = useCallback((payload: object) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(payload));
    return true;
  }, []);

  useEffect(() => {
    let disposed = false;
    let finished = false;
    let retries = 0;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    const token = getAccess("interview", interviewId);
    if (!token) {
      setStatus("error");
      setMessages([{ id: 1, role: "agent", text: "此标签页没有面试访问凭据，请从首页创建面试。" }]);
      return;
    }
    try {
      pendingRef.current = JSON.parse(sessionStorage.getItem(pendingKey) ?? "null");
    } catch { sessionStorage.removeItem(pendingKey); }
    setPending(Boolean(pendingRef.current));

    const clearPending = () => {
      pendingRef.current = null;
      setPending(false);
      sessionStorage.removeItem(pendingKey);
    };
    const push = (role: ChatMessage["role"], text: string, kind?: ChatMessage["kind"]) => {
      const id = ++messageSeq.current;
      setMessages(prev => [...prev, { id, role, text, kind }]);
    };
    const dispatch = (data: WireEvent, replay = false) => {
      if (data.type === "snapshot") {
        setMessages([]); setScores([]); setLastScore(null);
        messageSeq.current = 0; lastSeq.current = -1;
        for (const event of data.events) dispatch(event, true);
        versionRef.current = data.version;
        questionRef.current = data.current_question;
        setCurrentQuestion(data.current_question);
        setCurrentState(data.state);
        finished = data.finished;
        setStatus(snapshotStatus(data));
        const submission = pendingRef.current;
        if (submission) {
          const committed = data.events.some(e => e.type === "answer_ack" && e.message_id === submission.message_id);
          if (committed || finished) clearPending();
          else if (submission.turn_id === data.current_question?.turn_id && submission.version === data.version) {
            wsRef.current?.send(JSON.stringify(submission));
          } else {
            clearPending();
            push("agent", "面试已同步到最新轮次，未提交的旧轮回答没有用于新题。", "reaction");
          }
        }
        if (finished) wsRef.current?.close();
        return;
      }
      if (data.seq !== undefined) {
        if (data.seq <= lastSeq.current) return;
        lastSeq.current = data.seq;
      }
      if (data.version !== undefined) versionRef.current = data.version;
      // 语音事件不进入聊天流：字幕单独渲染，音频交给 useVoiceChannel。
      if (VOICE_EVENT_TYPES.has(data.type)) {
        if (data.type === "asr_partial") {
          setSubtitle(prev => ({ ...prev, partial: data.text }));
        } else if (data.type === "asr_final") {
          setSubtitle({ partial: "", final: data.text });
        }
        voiceSinkRef.current?.(data as VoiceEvent);
        return;
      }
      switch (data.type) {
        case "state": setCurrentState(data.state); break;
        case "greeting": push("agent", data.text, "greeting"); break;
        case "question":
          questionRef.current = data; setCurrentQuestion(data);
          setSubtitle({ partial: "", final: "" });
          if (!replay && data.turn_id !== pendingRef.current?.turn_id) clearPending();
          push("agent", `${data.is_probe ? `【追问 L${data.probe_depth}】` : data.is_coding ? "【编程题】" : `【${data.theme}】`}${data.content}`,
            data.is_probe ? "probe" : data.is_coding ? "coding" : "question");
          break;
        case "answer_ack": push("user", data.answer_text); break;
        case "score":
          setLastScore(data); setScores(prev => [...prev, data]);
          push("agent", `本轮得分 ${data.score.toFixed(1)} / 10。${data.evidence}`, "reaction");
          break;
        case "agent_message": push("agent", data.text, "reaction"); break;
        case "closing": push("agent", data.text, "closing"); break;
        case "report_ready":
          finished = true; setStatus("finished"); setCurrentQuestion(null); questionRef.current = null;
          if (!replay) { clearPending(); wsRef.current?.close(); }
          break;
        case "interview_cancelled":
          finished = true; setStatus("cancelled"); setCurrentState("cancelled");
          setCurrentQuestion(null); questionRef.current = null; clearPending();
          push("agent", data.text, "closing");
          if (!replay) wsRef.current?.close();
          break;
        case "error":
          clearPending();
          push("agent", data.detail, "reaction");
          if (data.code === "stale_turn") {
            setStatus("connecting"); wsRef.current?.send(JSON.stringify({ type: "start" }));
          }
          break;
      }
    };
    const connect = () => {
      if (disposed || finished) return;
      setStatus("connecting");
      const ws = new WebSocket(`${WS_BASE}/ws/interview/${interviewId}`, ["interview", token]);
      wsRef.current = ws;
      ws.onopen = () => { if (!disposed) ws.send(JSON.stringify({ type: "start" })); };
      ws.onmessage = event => {
        if (disposed || ws !== wsRef.current) return;
        try {
          const data = JSON.parse(event.data as string) as WireEvent;
          if (data.type === "snapshot") retries = 0;
          dispatch(data);
        } catch { push("agent", "服务器消息无法解析，请刷新同步。", "reaction"); }
      };
      ws.onclose = () => {
        if (disposed || finished || ws !== wsRef.current) return;
        if (++retries > 6) { setStatus("error"); return; }
        setStatus("connecting");
        reconnect = setTimeout(connect, Math.min(1000 * 2 ** (retries - 1), 10000));
      };
      ws.onerror = () => { if (!disposed && !finished) setStatus("connecting"); };
    };
    connect();
    return () => {
      disposed = true;
      if (reconnect) clearTimeout(reconnect);
      const ws = wsRef.current;
      if (ws) { ws.onclose = null; ws.onmessage = null; ws.close(); }
      wsRef.current = null;
    };
  }, [interviewId, pendingKey]);

  const sendAnswer = useCallback((text: string, code?: string) => {
    const ws = wsRef.current;
    const question = questionRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !question || pendingRef.current || status !== "active") return false;
    if (!text.trim() && !code?.trim()) return false;
    const payload: PendingAnswer = { type: "answer", message_id: crypto.randomUUID(),
      turn_id: question.turn_id, version: versionRef.current, text, ...(code ? { code } : {}) };
    // 先存再发，刷新或 ACK 丢失时沿用 message_id 安全重试。
    sessionStorage.setItem(pendingKey, JSON.stringify(payload));
    pendingRef.current = payload; setPending(true);
    ws.send(JSON.stringify(payload));
    return true;
  }, [pendingKey, status]);

  return {
    messages, status, currentState, currentQuestion, lastScore, scores, pending, sendAnswer,
    subtitle, sendVoice, registerVoiceSink,
  };
}
