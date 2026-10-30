import assert from "node:assert/strict";
import { test } from "node:test";
import { filterReportTurns } from "../lib/report-filter";
import type { PerQuestionReport } from "../lib/types";

const turns: PerQuestionReport[] = [
  { question_id: "a", theme: "MySQL", score: 6.9, probe_depth: 0 },
  { question_id: "b", theme: "MySQL", score: 7, probe_depth: 1 },
  { question_id: "c", theme: "JVM", score: 0, probe_depth: 2 },
].map(turn => ({ ...turn, content: "题目", evidence: "依据", key_points_hit: [], key_points_missed: [], sandbox: null }));

test("weak review includes zero scores and excludes the exact pass boundary", () => {
  assert.deepEqual(filterReportTurns(turns, "", "weak").map(t => t.question_id), ["a", "c"]);
  assert.deepEqual(filterReportTurns(turns, "", "weak", 8).map(t => t.question_id), ["a", "b", "c"]);
});
test("theme and probe filters compose without changing report order or data", () => {
  const before = JSON.stringify(turns);
  assert.deepEqual(filterReportTurns(turns, "MySQL", "probe").map(t => t.question_id), ["b"]);
  assert.equal(JSON.stringify(turns), before);
  assert.equal(filterReportTurns(turns, "missing", "all").length, 0);
  assert.equal(filterReportTurns([], "", "all").length, 0);
});
