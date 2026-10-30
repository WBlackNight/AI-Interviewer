import type { PerQuestionReport } from "./types";

export type ReviewKind = "all" | "weak" | "probe";

export function filterReportTurns(turns: PerQuestionReport[], theme: string,
                                  kind: ReviewKind, weakScore = 7): PerQuestionReport[] {
  return turns.filter(turn => (!theme || turn.theme === theme) &&
    (kind === "all" || (kind === "weak" ? turn.score < weakScore : turn.probe_depth > 0)));
}
