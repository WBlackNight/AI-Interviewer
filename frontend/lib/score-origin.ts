import type { ScoringOrigin } from "./types";

export function originLabel(origin?: ScoringOrigin): string {
  const names: Record<string, string> = { heuristic: "规则评分", llm: "模型评分", heuristic_fallback: "模型失败后规则回退", unknown: "来源未记录" };
  const label = names[origin?.source ?? "unknown"] ?? names.unknown;
  return label + (origin?.cached ? " · 缓存命中，本轮未调用评分模型" : "") + (origin?.sandbox_applied ? " · 含客观判题合分" : "");
}

export function originVersions(origin?: ScoringOrigin): string {
  if (!origin || origin.source === "unknown") return "历史来源与版本未记录";
  return [origin.scorer_version, origin.model, origin.prompt_version,
    origin.config_version ? `配置 ${origin.config_version}` : null,
    origin.prompt_digest ? `提示词摘要 ${origin.prompt_digest.slice(0, 12)}` : null,
    origin.fallback_reason ? `回退类别 ${origin.fallback_reason}` : null].filter(Boolean).join(" · ") || "版本未记录";
}
