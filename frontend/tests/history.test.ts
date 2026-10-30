import assert from "node:assert/strict";
import { test } from "node:test";
import { listInterviewIds, getAccess } from "../lib/access";
import { loadHistory } from "../lib/history";
import type { InterviewSummary } from "../lib/types";

const id = (n: number) => n.toString(16).padStart(32, "0");
const summary = (value: string, time: string | null = null): InterviewSummary => ({
  interview_id: value, position: "java_backend", difficulty: "mid", status: "created",
  theme_count: 1, answer_count: 0, started_at: null, ended_at: null, last_activity_at: time,
});

test("only discovers valid interview grants; ignores pending answers, resumes and malformed keys", () => {
  const values = new Map<string, string>([
    [`interview:${id(1)}:token`, "a".repeat(64)], [`interview:${id(1)}:pending`, "private answer"],
    [`resume:${id(2)}:token`, "a".repeat(64)], [`interview:${id(3)}:token`, "invalid"],
    ["interview:../unexpected:token", "a".repeat(64)],
  ]);
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: {
    length: values.size, key: (i: number) => [...values.keys()][i], getItem: (key: string) => values.get(key) ?? null,
  } });
  assert.deepEqual(listInterviewIds(), [id(1)]);
});

test("unavailable browser storage returns no grants and does not crash history", () => {
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, get() { throw new Error("blocked"); } });
  assert.deepEqual(listInterviewIds(), []);
  assert.equal(getAccess("interview", id(1)), null);
});

test("isolates failures, deduplicates and sorts by actual activity", async () => {
  const result = await loadHistory([id(1), id(1), id(2), id(3)], async value => {
    if (value === id(2)) throw new Error("无效凭据");
    return summary(value, value === id(3) ? "2026-10-22T01:00:00+00:00" : null);
  });
  assert.equal(result.length, 3);
  assert.equal(result[0].id, id(3));
  assert.equal(result.find(row => row.id === id(2))?.error, "无效凭据");
});

test("bounds request count to 50 and concurrent reads to four", async () => {
  let active = 0, max = 0, calls = 0;
  const result = await loadHistory(Array.from({ length: 70 }, (_, i) => id(i)), async value => {
    calls++; active++; max = Math.max(max, active);
    await new Promise(resolve => setTimeout(resolve, 1));
    active--; return summary(value);
  });
  assert.equal(calls, 50); assert.equal(result.length, 50); assert.equal(max, 4);
});
