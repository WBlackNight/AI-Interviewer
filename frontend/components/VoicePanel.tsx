"use client";

import { useVoiceChannel } from "@/hooks/useVoiceChannel";
import type { VoiceEvent } from "@/lib/types";

interface Props {
  turnId: string | null;
  subtitle: { partial: string; final: string };
  sendVoice: (payload: object) => boolean;
  registerVoiceSink: (sink: ((event: VoiceEvent) => void) | null) => void;
}

const STATUS_LABEL: Record<string, string> = {
  idle: "语音未开启",
  requesting: "正在申请麦克风…",
  ready: "采集中",
  denied: "未授权",
  unsupported: "不支持",
  error: "异常",
};

/**
 * 语音面板：麦克风开关、电平、播报状态与打断、实时字幕。
 *
 * 设计约定（docs/技术实现步骤.md 步骤 1.2/1.5）：
 * - 任何语音异常都必须给出**文字回退**，不能把用户困在不能用输入框的状态；
 * - 打断按钮是显式的，同时也有麦克风能量触发的自动打断；
 * - 字幕 partial 用灰字覆盖显示，final 转黑字。
 */
export default function VoicePanel({ turnId, subtitle, sendVoice, registerVoiceSink }: Props) {
  const voice = useVoiceChannel({
    turnId,
    enabled: true,
    sendVoice,
    registerVoiceSink,
  });

  const active = voice.status === "ready";

  return (
    <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">语音对话</span>
        <span
          className={`rounded px-1.5 py-0.5 text-[11px] ${
            active
              ? "bg-emerald-50 text-emerald-700"
              : voice.status === "denied" || voice.status === "error"
                ? "bg-amber-50 text-amber-700"
                : "bg-slate-100 text-slate-600"
          }`}
        >
          {STATUS_LABEL[voice.status] ?? voice.status}
        </span>
      </div>

      <div className="flex gap-2">
        {active ? (
          <button
            onClick={voice.stop}
            className="flex-1 rounded-lg border border-slate-200 py-2 text-sm hover:bg-slate-50"
          >
            结束语音
          </button>
        ) : (
          <button
            onClick={voice.start}
            disabled={voice.status === "requesting"}
            className="flex-1 rounded-lg bg-brand-600 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
          >
            开启语音作答
          </button>
        )}
        <button
          onClick={voice.interrupt}
          disabled={!voice.playing}
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 hover:bg-amber-100 disabled:opacity-40"
          title="打断面试官播报"
        >
          打断
        </button>
      </div>

      {active && (
        <div className="space-y-1">
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-emerald-400 transition-[width] duration-75"
              style={{ width: `${Math.round(voice.level * 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>{voice.playing ? "面试官正在播报" : "等待你说话"}</span>
            <span>打断 {voice.bargeInCount} 次</span>
          </div>
        </div>
      )}

      {(subtitle.partial || subtitle.final) && (
        <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5">
          {subtitle.partial && <span className="text-slate-400">{subtitle.partial}</span>}
          {subtitle.final && <span className="text-slate-700">{subtitle.final}</span>}
        </div>
      )}

      {voice.message && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
          {voice.message}
        </p>
      )}

      <p className="text-[11px] leading-5 text-slate-400">
        建议佩戴耳机：外放时面试官声音可能被麦克风采集，影响打断判定。
        文字输入始终可用。
      </p>
    </div>
  );
}
