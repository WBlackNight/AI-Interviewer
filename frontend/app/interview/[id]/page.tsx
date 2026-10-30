"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import VoicePanel from "@/components/VoicePanel";
import { useInterviewSession } from "@/hooks/useInterviewSession";
import CancelInterviewButton from "@/components/CancelInterviewButton";

/** 语音 UI 开关：默认关闭，与后端 VOICE_ENABLED 的默认保持一致。 */
const VOICE_UI_ENABLED = process.env.NEXT_PUBLIC_VOICE_ENABLED === "true";

const STATE_LABELS: Record<string, string> = {
  greeting: "开场",
  questioning: "主题提问",
  probing: "动态追问",
  coding: "编程环节",
  closing: "收尾",
  report: "生成报告",
  finished: "已结束",
  cancelled: "已取消",
};

export default function InterviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const interviewId = params.id;
  const {
    messages,
    status,
    currentState,
    currentQuestion,
    lastScore,
    scores,
    pending,
    sendAnswer,
    subtitle,
    sendVoice,
    registerVoiceSink,
  } = useInterviewSession(interviewId);

  const [answer, setAnswer] = useState("");
  const [code, setCode] = useState(
    "def two_sum(nums, target):\n    # 在这里实现\n    pass\n\nimport sys\nnums = list(map(int, sys.stdin.readline().split()))\ntarget = int(sys.stdin.readline())\nprint(two_sum(nums, target))"
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const submit = () => {
    if (pending || status !== "active" || !currentQuestion) return;
    if (currentQuestion.is_coding ? !code.trim() : !answer.trim()) return;
    if (sendAnswer(answer.trim() || "（代码实现如下）", currentQuestion.is_coding ? code : undefined)) {
      setAnswer("");
    }
  };

  const avgScore =
    scores.length > 0
      ? (scores.reduce((acc, s) => acc + s.score, 0) / scores.length).toFixed(1)
      : "--";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      {/* 主对话区 */}
      <section className="flex h-[72vh] flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`h-2 w-2 rounded-full ${
                status === "active"
                  ? "bg-emerald-500"
                  : status === "finished" || status === "cancelled"
                    ? "bg-slate-400"
                    : "bg-amber-400"
              }`}
            />
            <span className="font-medium">
              {status === "connecting" ? "正在连接并同步…" : status === "error" ? "连接失败，请刷新重试" : STATE_LABELS[currentState] ?? "连接中…"}
            </span>
          </div>
          <span className="text-xs text-slate-500">已答 {scores.length} 轮</span>
        </div>

        <div className="chat-scroll flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "agent" ? "justify-start" : "justify-end"}`}
            >
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-6 ${
                  message.role === "agent"
                    ? message.kind === "probe"
                      ? "bg-amber-50 text-amber-900"
                      : "bg-brand-50 text-slate-800"
                    : "bg-brand-600 text-white"
                }`}
              >
                {message.text}
              </div>
            </div>
          ))}
          {(status === "finished" || status === "cancelled") && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-center text-sm text-emerald-800">
              {status === "cancelled" ? "面试已取消，" : "面试已结束，"}
              <Link
                href={`/report/${interviewId}`}
                className="font-semibold underline underline-offset-2"
              >
                {status === "cancelled" ? "查看已提交回答的部分报告 →" : "查看能力雷达图与逐题复盘 →"}
              </Link>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* 输入区 */}
        {status === "active" && currentQuestion && (
          <div className="space-y-3 border-t border-slate-100 px-5 py-4">
            {currentQuestion.is_coding && (
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-600">
                    编程题 · 用编辑器实现（Python）
                  </span>
                  {currentQuestion.testcases && (
                    <span className="text-xs text-slate-400">
                      {currentQuestion.testcases.length} 组测试用例
                    </span>
                  )}
                </div>
                <textarea
                  value={code}
                  disabled={pending}
                  onChange={(e) => setCode(e.target.value)}
                  rows={8}
                  spellCheck={false}
                  className="w-full rounded-lg border border-slate-200 bg-slate-900 px-3 py-2 font-mono text-xs leading-5 text-slate-100 outline-none focus:border-brand-400"
                />
              </div>
            )}
            <div className="flex items-end gap-3">
              <textarea
                value={answer}
                disabled={pending}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
                rows={2}
                placeholder={
                  currentQuestion.is_coding
                    ? "补充你的思路（可选），代码写好后提交"
                    : "输入你的回答，Enter 发送 / Shift+Enter 换行"
                }
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-400"
              />
              <button
                onClick={submit}
                disabled={pending || (currentQuestion.is_coding ? !code.trim() : !answer.trim())}
                className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
              >
                {pending ? "评分中…" : "提交回答"}
              </button>
            </div>
          </div>
        )}
      </section>

      {/* 侧栏：实时评分 */}
      <aside className="space-y-4">
        {status !== "finished" && status !== "cancelled" && <CancelInterviewButton interviewId={interviewId}
          onCancelled={() => router.replace(`/report/${interviewId}`)} />}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium text-slate-500">当前均分</div>
          <div className="mt-1 text-3xl font-semibold text-brand-600">{avgScore}</div>
          <div className="mt-1 text-xs text-slate-400">满分 10 · 实时聚合</div>
        </div>

        {lastScore && (
          <div className="space-y-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-medium text-slate-500">上一轮评分</div>
            {Object.entries(lastScore.dimensions).map(([key, value]) => (
              <div key={key}>
                <div className="flex justify-between text-xs text-slate-600">
                  <span>{key}</span>
                  <span>{value.toFixed(1)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-brand-400"
                    style={{ width: `${Math.min(value, 10) * 10}%` }}
                  />
                </div>
              </div>
            ))}
            {lastScore.key_points_missed.length > 0 && (
              <p className="pt-1 text-xs text-amber-700">
                未覆盖：{lastScore.key_points_missed.join("、")}
              </p>
            )}
            {lastScore.sandbox && (
              <p className="text-xs text-emerald-700">
                沙箱判题：{lastScore.sandbox.passed}/{lastScore.sandbox.total} 通过
              </p>
            )}
          </div>
        )}

        <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-xs leading-5 text-slate-500">
          {status === "cancelled" ? "本场已取消，已提交回答保留在部分报告中；如需继续练习，请从首页创建新面试。"
            : status === "finished" ? "本场已完成，可在报告中复盘回答或创建新的专项练习。"
            : VOICE_UI_ENABLED
            ? "语音与文字可随时切换；刷新后可恢复当前面试。"
            : "语音对话（VAD + 流式 ASR/TTS）为下一迭代扩展点，当前版本为文字模式；刷新后可恢复当前面试。"}
        </div>

        {VOICE_UI_ENABLED && status === "active" && (
          <VoicePanel
            turnId={currentQuestion?.turn_id ?? null}
            subtitle={subtitle}
            sendVoice={sendVoice}
            registerVoiceSink={registerVoiceSink}
          />
        )}
      </aside>
    </div>
  );
}
