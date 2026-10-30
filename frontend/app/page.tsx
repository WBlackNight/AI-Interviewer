"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createInterview, createResume, createResumePdf, getPositions, getResumeLimits, type ResumeLimits } from "@/lib/api";
import type { PlanItem, PositionOption } from "@/lib/types";
import { WorkspaceIcon } from "@/components/WorkspaceShell";

const DIFFICULTIES = [
  { id: "easy", name: "轻松" },
  { id: "mid", name: "标准" },
  { id: "hard", name: "地狱" },
];

const SAMPLE_RESUME = `教育经历
XX大学 计算机科学与技术 2022-2026

专业技能
Java、Spring、MySQL、Redis、并发编程、JVM

项目经历
电商秒杀系统：负责库存超卖防护与缓存设计
在线评测平台：负责判题沙箱与并发压测`;

export default function HomePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [position, setPosition] = useState("");
  const [positions, setPositions] = useState<PositionOption[]>([]);
  const [positionsLoading, setPositionsLoading] = useState(true);
  const [positionsError, setPositionsError] = useState("");
  const positionsVersion = useRef(0);
  const loadPositions = async () => {
    const version = ++positionsVersion.current;
    setPositionsLoading(true); setPositionsError("");
    try {
      const data = await getPositions();
      if (version !== positionsVersion.current) return;
      setPositions(data.positions);
      setPosition(current => data.positions.some(p => p.id === current) ? current : data.positions[0]?.id ?? "");
      if (!data.positions.length) setPositionsError("暂无可用岗位，请稍后重试");
    } catch {
      if (version === positionsVersion.current) { setPositionsError("岗位加载失败，请确认后端已启动后重试"); setPositions([]); setPosition(""); }
    } finally { if (version === positionsVersion.current) setPositionsLoading(false); }
  };
  const [difficulty, setDifficulty] = useState("mid");
  const [practiceMode, setPracticeMode] = useState(false);
  const [selectedThemes, setSelectedThemes] = useState<string[]>([]);
  const selectedPosition = positions.find(p => p.id === position);
  const themeLimit = selectedPosition?.practice_theme_limit ?? 0;
  const [resumeText, setResumeText] = useState("");
  const [resumeMode, setResumeMode] = useState<"text" | "pdf">("text");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [limits, setLimits] = useState<ResumeLimits | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const starting = useRef(false);
  const [plan, setPlan] = useState<PlanItem[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    getResumeLimits().then(value => { if (active) setLimits(value); }).catch(() => {});
    void loadPositions();
    return () => { active = false; positionsVersion.current++; };
  }, []);

  useEffect(() => { setSelectedThemes([]); }, [position]);

  const start = async () => {
    if (starting.current) return;
    if (!positions.some(p => p.id === position) || positionsLoading) { setError("请先选择可用岗位"); return; }
    if (practiceMode && (!selectedThemes.length || selectedThemes.length > themeLimit)) {
      setError(`请选择1至${themeLimit}个知识主题`); return;
    }
    starting.current = true;
    setError("");
    setLoading(true);
    try {
      let resumeId: string | undefined;
      if (!practiceMode && resumeMode === "pdf") {
        if (!resumeFile) throw new Error("请先选择 PDF，或切换到粘贴文本");
        if (limits && resumeFile.size > limits.pdf_max_bytes) throw new Error("PDF 超过大小限制，请精简或粘贴文本");
        const resume = await createResumePdf(resumeFile, name || "匿名用户");
        resumeId = resume.resume_id;
      } else if (!practiceMode && resumeText.trim()) {
        const resume = await createResume({ name: name || "匿名用户", resume_text: resumeText });
        resumeId = resume.resume_id;
      }
      const created = await createInterview({
        resume_id: resumeId,
        position,
        difficulty,
        ...(practiceMode ? { themes: selectedThemes } : {}),
      });
      setPlan(created.plan);
      router.push(`/interview/${created.interview_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败，请确认后端已启动");
    } finally {
      starting.current = false;
      setLoading(false);
    }
  };

  return (
    <div className="home-workspace">
      <section className="home-hero">
        <div className="home-hero-copy">
          <span className="hero-eyebrow"><span /> 专注练习，从容表达</span>
          <h1>把准备，<br />变成<span>底气。</span></h1>
          <p>在这里，把面试提前练习一遍。<br />从一次认真表达，到一份清晰的复盘。</p>
          <div className="hero-chips"><span>多轮技术问答</span><span>逐题复盘</span><span>主题专项</span></div>
        </div>
        <div className="hero-illustration" aria-hidden="true">
          <div className="orbit orbit-one" /><div className="orbit orbit-two" />
          <div className="hero-star"><WorkspaceIcon name="sparkle" /></div>
          <div className="illustration-card card-question"><span className="mini-avatar">Q</span><div><small>从熟悉的知识开始</small><strong>聊聊你的解题思路。</strong></div><span className="wave-lines"><i /><i /><i /><i /><i /></span></div>
          <div className="illustration-card card-answer"><span className="answer-check"><WorkspaceIcon name="check" /></span><div><strong>每一次尝试，都值得复盘</strong><small>回看回答 · 找到下一步</small></div></div>
          <span className="illustration-caption">A LITTLE PRACTICE. MORE CONFIDENCE.</span>
        </div>
      </section>

      <div className="home-grid">
      <section className="practice-config space-y-6 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="config-heading"><div><span className="section-eyebrow">LET’S GET STARTED</span><h2>开启一场练习</h2></div><span className="quiet-tag">按你的节奏来</span></div>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">怎么称呼你</span>
            <input
              value={name}
              maxLength={64}
              disabled={loading}
              onChange={(e) => setName(e.target.value)}
              placeholder="匿名用户"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-brand-400"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">面试岗位</span>
            <select
              value={position}
              disabled={loading || positionsLoading || !positions.length}
              onChange={(e) => setPosition(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 outline-none focus:border-brand-400"
            >
              {!positions.length && <option value="">{positionsLoading ? "正在加载岗位…" : "暂无可用岗位"}</option>}
              {positions.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">面试强度</span>
            <select
              value={difficulty}
              disabled={loading}
              onChange={(e) => setDifficulty(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 outline-none focus:border-brand-400"
            >
              {DIFFICULTIES.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="space-y-3">
          <p className="field-title">选择练习方式</p>
          <div role="group" aria-label="练习方式" className="practice-mode-grid">
            {([false, true] as const).map(mode => <button key={String(mode)} type="button" disabled={loading}
              aria-label={mode ? "主题专项" : "综合面试"}
              aria-pressed={practiceMode === mode} onClick={() => { setPracticeMode(mode); setError(""); }}
              className={`practice-mode ${practiceMode === mode ? "is-selected" : ""}`}>
              <span className="mode-icon"><WorkspaceIcon name={mode ? "tasks" : "history"} /></span><strong>{mode ? "主题专项" : "综合面试"}</strong>
              <span className="mode-description">{mode ? "集中练习，逐个攻克知识主题" : "围绕岗位，展开多主题对话"}</span><span className="mode-radio" aria-hidden="true">{practiceMode === mode && <span />}</span>
            </button>)}
          </div>
          {practiceMode && <fieldset disabled={loading} className="space-y-3 rounded-xl border border-slate-200 p-4">
            <legend className="px-1 text-sm font-medium">选择知识主题（最多{themeLimit}个）</legend>
            <div className="flex flex-wrap gap-4">
              {(selectedPosition?.practice_themes ?? []).map(value => <label key={value} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={selectedThemes.includes(value)}
                  disabled={!selectedThemes.includes(value) && selectedThemes.length >= themeLimit}
                  onChange={event => setSelectedThemes(current => event.target.checked ? [...current, value] : current.filter(t => t !== value))} />
                {value}
              </label>)}
            </div>
            <p className="text-xs leading-5 text-slate-500">无需简历。每个主题最多2道主问题，保留动态追问，不加入编码题。题目不足时只使用当前主题可用题目；同场不重复，跨场复练可能重复。</p>
          </fieldset>}
        </div>

        {!practiceMode && <>
        <div className="resume-heading"><span className="field-title">补充你的背景</span><span className="quiet-tag">可选</span></div>
        <div className="flex gap-2" role="group" aria-label="简历输入方式">
          {(["text", "pdf"] as const).map(mode => (
            <button key={mode} type="button" disabled={loading} aria-pressed={resumeMode === mode}
              onClick={() => { setResumeMode(mode); setError(""); }}
              className={`rounded-lg border px-4 py-2 text-sm ${resumeMode === mode ? "border-brand-600 bg-brand-50 text-brand-600" : "border-slate-200 text-slate-600"}`}>
              {mode === "text" ? "粘贴文本" : "上传 PDF"}
            </button>
          ))}
        </div>

        {resumeMode === "text" ? <>
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">
            简历文本（可选，用于个性化出题）
          </span>
          <textarea
            value={resumeText}
            maxLength={20000}
            disabled={loading}
            onChange={(e) => setResumeText(e.target.value)}
            rows={6}
            placeholder="粘贴简历文本：技能、项目经历……"
            className="w-full rounded-lg border border-slate-200 px-4 py-3 text-sm leading-6 outline-none focus:border-brand-400"
          />
        </label>
        <div className="resume-tools"><span>{resumeText.length.toLocaleString()} / 20,000 字</span><button
          disabled={loading}
          onClick={() => setResumeText(position === "python_backend" ? "教育经历\n示例大学 计算机科学\n专业技能\nPython、asyncio、SQL、FastAPI\n项目经历\n异步接口服务：使用参数绑定、事务与幂等处理请求" : SAMPLE_RESUME)}
          className="text-xs text-brand-600 underline-offset-2 hover:underline"
        >
          填入示例简历
        </button></div>
        </> : (
          <div className="space-y-3 rounded-xl border border-dashed border-slate-300 p-5 text-sm">
            <label className="block font-medium text-slate-700" htmlFor="resume-pdf">选择 PDF 简历</label>
            <input ref={fileInput} id="resume-pdf" type="file" accept=".pdf,application/pdf" disabled={loading}
              onChange={event => {
                const file = event.target.files?.[0] ?? null;
                setResumeFile(null);
                setError("");
                if (file && (!file.name.toLowerCase().endsWith(".pdf") || file.size === 0 ||
                  (limits && file.size > limits.pdf_max_bytes))) {
                  setError("请选择大小符合限制的非空 PDF，或改用粘贴文本");
                  event.target.value = "";
                  return;
                }
                setResumeFile(file);
              }} className="block w-full text-sm" />
            <p className="text-xs leading-5 text-slate-500">
              {limits ? `最多 ${(limits.pdf_max_bytes / 1024 / 1024).toFixed(1)} MiB、${limits.pdf_max_pages} 页、${limits.text_max_chars} 个提取字符。` : "文件须符合服务端大小、页数和文本长度限制。"}
              支持带文本层的未加密 PDF；扫描件请粘贴文本。点击开始后上传并解析。
            </p>
            {resumeFile && <p className="break-all text-xs text-slate-600">已选择：{resumeFile.name}</p>}
            {resumeFile && <button type="button" disabled={loading} className="text-xs text-slate-600 underline"
              onClick={() => { setResumeFile(null); if (fileInput.current) fileInput.current.value = ""; }}>移除文件</button>}
          </div>
        )}
        </>}

        {error && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}

        <button
          onClick={start}
          disabled={loading || positionsLoading || !positions.length}
          className="start-practice-button w-full rounded-lg bg-brand-600 py-3 font-medium text-white transition hover:bg-brand-800 disabled:opacity-50"
        >
          {loading ? "正在生成面试大纲…" : positionsLoading ? "正在加载岗位…" : practiceMode ? "开始专项练习" : "开始模拟面试"}
          <WorkspaceIcon name="arrow" />
        </button>
        <p className="form-footnote">无需简历也能练习，准备好了就开始。</p>
      </section>
      <aside className="home-guide">
        <section className="practice-brief"><span className="section-eyebrow">YOUR PRACTICE</span><h2>这一次，为自己准备。</h2><div className="brief-separator" />
          <dl><div><dt>目标岗位</dt><dd>{selectedPosition?.display_name ?? (positionsLoading ? "正在加载…" : "等待选择")}</dd></div><div><dt>练习强度</dt><dd>{DIFFICULTIES.find(d => d.id === difficulty)?.name}</dd></div><div><dt>练习方式</dt><dd>{practiceMode ? "主题专项" : "综合面试"}</dd></div></dl>
          {practiceMode && <div className="brief-themes">{selectedThemes.length ? selectedThemes.map(theme => <span key={theme}>{theme}</span>) : <p>选几个你想多练习的主题。</p>}</div>}
          <div className="brief-note"><WorkspaceIcon name="sparkle" /><p>不必一次答得完美。<br />先把你的思路说出来。</p></div>
        </section>
        <section className="practice-journey"><span className="section-eyebrow">HOW IT WORKS</span><h2>让每次练习，都有方向</h2>{[
          ["01", "选定你的方向", "选择岗位与强度，也可补充简历。"], ["02", "认真聊一场", "回答技术问题，展开你的思考。"], ["03", "带走一份复盘", "回看评分与回答，整理复习任务。"],
        ].map(([number, title, description]) => <div className="journey-step" key={number}><span>{number}</span><div><h3>{title}</h3><p>{description}</p></div></div>)}</section>
        <Link href="/revision" className="revision-shortcut"><span><strong>让复盘，不止于看过。</strong><small>到复习任务板整理下一步</small></span><WorkspaceIcon name="arrow" /></Link>
        {!positionsLoading && !positionsError && <p className="catalog-note">当前开放 {positions.length} 个岗位 · {positions.reduce((sum, p) => sum + p.question_count, 0)} 道内置示例题</p>}
      </aside>
      </div>
      {positionsError && <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{positionsError}<button type="button" disabled={positionsLoading || loading} onClick={() => void loadPositions()} className="ml-3 underline">重试加载岗位</button></p>}
    </div>
  );
}
