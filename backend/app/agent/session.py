"""面试会话编排器：状态机驱动的 Agent 核心。

职责边界：
- 只依赖 domain / bank / scorer / prober（纯逻辑，无 IO，可全量单测）；
- 产出事件流（dict 列表），由 API 层负责发送与持久化；
- 所有状态变更必须经 state_machine.transition() —— 非法路径直接崩溃。
"""
from __future__ import annotations
from dataclasses import asdict, replace
from app.score_origin import question_version
import uuid
import hashlib
import json
import re

from app.agent.prober import Probe
from app.agent.scorer import Scorer
from app.agent.state_machine import InterviewState, transition
from app.domain import (
    EventType,
    PlanItem,
    Question,
    ScoreRecord,
    ScoreResult,
    ScoreOrigin,
    SandboxResult,
)
from app.rag.question_bank import QuestionBank

PASS_REACTIONS = (
    "回答得不错，几个关键点都覆盖到了。",
    "嗯，这个回答比较完整，我们继续。",
    "可以，看得出你对这块是有实践积累的。",
)
GIVEUP_REACTIONS = (
    "没关系，这个点我们后面可以再补，先看下一个问题。",
    "好的，这个问题先到这里，我们换个方向。",
)

# 只识别独立的明确跳过意图，不把“不知道是否需要加锁”等技术回答当成放弃。
SKIP_ANSWER = re.compile(r"(?:跳过(?:本题|这题)?|下一题|这题不会|我不知道|不知道|不会|skip)[。.!！\s]*", re.I)


class AssetVersionError(ValueError):
    pass


class InterviewSession:
    def __init__(
        self,
        *,
        interview_id: str,
        position: str,
        plan: list[PlanItem],
        bank: QuestionBank,
        scorer: Scorer,
        prober: Probe,
        pass_score: float = 7.0,
        probe_score: float = 4.0,
        probe_depth_limit: int = 3,
        sandbox=None,  # SandboxProtocol | None
    ) -> None:
        self.interview_id = interview_id
        self.position = position
        self.plan = plan
        self.bank = bank
        self.scorer = scorer
        self.prober = prober
        self.pass_score = pass_score
        self.probe_score = probe_score
        self.probe_depth_limit = probe_depth_limit
        self.sandbox = sandbox

        self.state = InterviewState.GREETING
        self.finished = False

        self._records: list[ScoreRecord] = []
        self._asked: set[str] = set()
        self._current: Question | None = None
        #: 当前评分所依据的题目。正常提问时等于 _current；
        #: 进入追问后替换为带「追问锚点」的临时题目，避免用原题锚点评判追问回答。
        self._scoring_target: Question | None = None
        self._probe_depth = 0
        self._theme_index = 0
        self._theme_asked = 0
        self._coding_done = False
        self._reaction_cursor = 0
        self._turn_id = ""
        self._question_event: dict | None = None
        self._skill_node_id: str | None = None
        tree = getattr(prober, "tree", None)
        assets = {"questions": [asdict(q) for q in bank],
                  "skills": sorted(tree.all_names()) if tree else []}
        # 无路由的旧树保持原摘要；路由变更须触发同样的资产恢复保护。
        if tree and tree.question_routes:
            assets["question_routes"] = tree.question_routes
        self._asset_version = hashlib.sha256(json.dumps(assets, ensure_ascii=False,
            sort_keys=True).encode()).hexdigest()
        if not 0 <= probe_score <= pass_score <= 10 or probe_depth_limit < 0:
            raise ValueError("面试策略非法")

    @property
    def current_question(self) -> dict | None:
        return self._question_event if not self.finished else None

    def snapshot(self) -> dict:
        return {
            "format": 1, "state": self.state.value, "finished": self.finished,
            "asset_version": self._asset_version,
            "retrieval_version": self.bank.retrieval_version,
            "asked": sorted(self._asked), "current": asdict(self._current) if self._current else None,
            "scoring_target": asdict(self._scoring_target) if self._scoring_target else None,
            "probe_depth": self._probe_depth, "theme_index": self._theme_index,
            "theme_asked": self._theme_asked, "coding_done": self._coding_done,
            "reaction_cursor": self._reaction_cursor, "turn_id": self._turn_id,
            "question_event": self._question_event, "skill_node_id": self._skill_node_id,
            "plan": [asdict(p) for p in self.plan],
            "strategy": {"pass_score": self.pass_score, "probe_score": self.probe_score,
                         "probe_depth_limit": self.probe_depth_limit},
        }

    def restore(self, snapshot: dict) -> None:
        if snapshot.get("format") != 1:
            raise ValueError("不支持的会话快照版本")
        if snapshot.get("asset_version") != self._asset_version and not snapshot.get("finished"):
            raise AssetVersionError("进行中会话的题库或技能树版本已变化")
        if (snapshot.get("retrieval_version", "bm25-v1") != self.bank.retrieval_version
                and not snapshot.get("finished")):
            raise AssetVersionError("进行中会话的检索策略或索引版本已变化")
        self.state = InterviewState(snapshot["state"])
        self.finished = snapshot["finished"]
        self._asked = set(snapshot["asked"])
        self._current = Question.from_dict(snapshot["current"]) if snapshot["current"] else None
        target = snapshot["scoring_target"]
        self._scoring_target = Question.from_dict(target) if target else None
        self._probe_depth = snapshot["probe_depth"]
        self._theme_index = snapshot["theme_index"]
        self._theme_asked = snapshot["theme_asked"]
        self._coding_done = snapshot["coding_done"]
        self._reaction_cursor = snapshot["reaction_cursor"]
        self._turn_id = snapshot["turn_id"]
        self._question_event = snapshot["question_event"]
        self._skill_node_id = snapshot["skill_node_id"]
        self.plan = [PlanItem(**p) for p in snapshot["plan"]]
        for key, value in snapshot["strategy"].items():
            setattr(self, key, value)

    # ------------------------------------------------------------ 对外接口

    @property
    def records(self) -> list[ScoreRecord]:
        return list(self._records)

    def drain_records(self) -> list[ScoreRecord]:
        out, self._records = self._records, []
        return out

    def start(self) -> list[dict]:
        """开场：greeting → QUESTIONING → 首题。"""
        if self.state is not InterviewState.GREETING:
            return [{"type": EventType.ERROR, "detail": "面试已开始，不可重复开场"}]
        events: list[dict] = [
            {
                "type": EventType.GREETING,
                "text": self._greeting_text(),
            }
        ]
        self._move(events, InterviewState.QUESTIONING)
        events.extend(self._ask_next_theme_question())
        return events

    def handle_answer(self, text: str, *, code: str | None = None) -> list[dict]:
        """处理候选人回答：评分 → 决策（通过/追问/放弃）→ 产生下一事件。"""
        if self.finished:
            return [{"type": EventType.ERROR, "detail": "面试已结束"}]
        if self._current is None:
            return [{"type": EventType.ERROR, "detail": "当前没有待回答的问题"}]

        answer = (code or "").strip() or text.strip()
        if not answer:
            return [{"type": EventType.ERROR, "detail": "回答不能为空", "code": "invalid_answer"}]
        answer = f"{text.strip()}\n[代码]\n{code.strip()}" if code else answer
        target = self._scoring_target or self._current
        skipped = not code and SKIP_ANSWER.fullmatch(answer) is not None
        result = (ScoreResult(0, dimensions={k: 0 for k in ("技术深度", "表达逻辑", "岗位匹配")},
                  key_points_missed=tuple(p.point for p in target.answer_points),
                  evidence=f"本轮主动跳过，未作技术回答。原话：{answer}",
                  origin=ScoreOrigin(source="heuristic", scorer_version="explicit-skip-v1"))
                  if skipped else self._score_answer(answer, code=code))
        record = ScoreRecord(
            question_id=target.id,
            theme=self._current.theme,
            content=target.content,
            result=result,
            probe_depth=self._probe_depth,
            answer_text=answer,
            turn_id=self._turn_id,
            main_question_id=self._current.id,
            skill_node_id=self._skill_node_id,
              question_version=question_version(target),
              main_question_version=question_version(self._current),
              question_difficulty=target.difficulty,
              is_coding=target.is_coding,
        )
        self._records.append(record)

        events: list[dict] = [
            {
                "type": EventType.ANSWER_ACK,
                "question_id": target.id,
                "turn_id": self._turn_id,
                "answer_text": answer,
                "probe_depth": self._probe_depth,
            },
            self._score_event(result),
        ]

        if self.state is InterviewState.CODING:
            events.append(self._reaction(result.score >= self.pass_score))
            events.extend(self._advance_after_question())
            return events

        if skipped:
            events.append(self._reaction(False))
            events.extend(self._advance_after_question())
            return events

        if result.score >= self.pass_score:
            events.append(self._reaction(True))
            events.extend(self._advance_after_question())
            return events

        # 未达通过线：有追问预算就下钻，否则放弃本题推进
        if self._probe_depth < self.probe_depth_limit:
            events.extend(self._enter_probe(result, answer=answer))
            return events

        events.append(self._reaction(False))
        events.extend(self._advance_after_question())
        return events

    # ------------------------------------------------------------ 内部流转

    def _score_answer(self, answer: str, *, code: str | None) -> ScoreResult:
        # 追问场景使用带追问锚点的临时题目评分（见 _enter_probe）
        target = self._scoring_target or self._current
        assert target is not None
        result = self.scorer.score(target, answer)
        if (
            self.state is InterviewState.CODING
            and self.sandbox is not None
            and self._current.testcases
        ):
            sandbox_result: SandboxResult = self.sandbox.judge(
                code or answer, list(self._current.testcases)
            )
            merged = round(
                min(10.0, 0.6 * result.score + 4.0 * sandbox_result.pass_ratio), 1
            )
            result = replace(result,
                score=merged,
                dimensions={**result.dimensions, "技术深度": merged, "岗位匹配": merged},
                key_points_hit=result.key_points_hit,
                key_points_missed=result.key_points_missed,
                evidence=result.evidence,
                sandbox={
                    "passed": sandbox_result.passed,
                    "total": sandbox_result.total,
                    "detail": sandbox_result.detail,
                    "subjective_score": result.score,
                    "objective_score": round(10 * sandbox_result.pass_ratio, 1),
                },
                  origin=replace(result.origin, sandbox_applied=True),
            )
        return result

    def _score_event(self, result: ScoreResult) -> dict:
        return {
            "type": EventType.SCORE,
            "question_id": self._scoring_target.id if self._scoring_target else "",
            "turn_id": self._turn_id,
            "score": result.score,
            "dimensions": result.dimensions,
            "key_points_hit": list(result.key_points_hit),
            "key_points_missed": list(result.key_points_missed),
            "evidence": result.evidence,
            "sandbox": result.sandbox,
            "scoring_origin": asdict(result.origin),
        }

    def _greeting_text(self) -> str:
        themes = "、".join(item.theme for item in self.plan)
        return (
            f"你好，我是今天的面试官，接下来我们进行一场约 15 分钟的"
            f"{self.position} 岗位模拟面试，主要围绕 {themes} 展开。"
            "放松一点，就当正式面试来练，准备好了我们就开始。"
        )

    def _move(self, events: list[dict], dst: InterviewState) -> None:
        self.state = transition(self.state, dst)
        events.append({"type": EventType.STATE, "state": self.state.value})

    def _reaction(self, positive: bool) -> dict:
        if positive:
            text = PASS_REACTIONS[self._reaction_cursor % len(PASS_REACTIONS)]
        else:
            text = GIVEUP_REACTIONS[self._reaction_cursor % len(GIVEUP_REACTIONS)]
        self._reaction_cursor += 1
        return {"type": EventType.AGENT_MESSAGE, "text": text}

    # ---- 问题推进

    def _ask(self, question: Question, *, coding: bool = False) -> dict:
        self._current = question
        self._scoring_target = question  # 新问题重置评分目标
        self._asked.add(question.id)
        self._probe_depth = 0
        self._skill_node_id = question.theme
        self._turn_id = uuid.uuid4().hex
        if not coding:
            self._theme_asked += 1
        self._question_event = {
            "type": EventType.QUESTION,
            "turn_id": self._turn_id,
            "id": question.id,
            "theme": question.theme,
            "content": question.content,
            "difficulty": question.difficulty,
            "is_coding": question.is_coding,
            "testcases": (
                [{"input": t.input, "expected": t.expected} for t in question.testcases]
                if question.is_coding
                else None
            ),
        }
        return self._question_event

    def _ask_next_theme_question(self) -> list[dict]:
        """在当前主题内取下一题；主题无题则跳下一主题；大纲耗尽进入收尾。"""
        events: list[dict] = []
        while self._theme_index < len(self.plan):
            item = self.plan[self._theme_index]
            question = self.bank.next_question(
                position=self.position,
                theme=item.theme,
                difficulty=item.difficulty,
                exclude=self._asked,
            )
            if question is not None:
                if self.state is not InterviewState.QUESTIONING:
                    self._move(events, InterviewState.QUESTIONING)  # CODING→QUESTIONING
                events.append(self._ask(question))
                return events
            self._theme_index += 1
            self._theme_asked = 0
        return self._close_interview(events)

    def _advance_after_question(self) -> list[dict]:
        """当前问题已终结（通过/放弃/编码完成）后的统一推进。"""
        events: list[dict] = []
        if self.state is InterviewState.PROBING:
            self._move(events, InterviewState.QUESTIONING)
        elif self.state is InterviewState.CODING:
            self._coding_done = True

        item = self.plan[self._theme_index]
        if self._theme_asked < item.question_count:
            events.extend(self._ask_next_theme_question())
            return events

        # 主题问满：先看是否挂编码题
        if (
            item.include_coding
            and not self._coding_done
            and self.bank.has_coding(self.position)
        ):
            self._coding_done = True
            coding_q = self.bank.next_coding_question(
                position=self.position, exclude=self._asked
            )
            if coding_q is not None:
                self._move(events, InterviewState.CODING)
                events.append(self._ask(coding_q, coding=True))
                return events

        # 进入下一主题
        self._theme_index += 1
        self._theme_asked = 0
        events.extend(self._ask_next_theme_question())
        return events

    # ---- 追问

    def _enter_probe(self, result: ScoreResult, *, answer: str = "") -> list[dict]:
        events: list[dict] = []
        self._move(events, InterviewState.PROBING)  # QUESTIONING→PROBING 或 PROBING 自转移
        self._probe_depth += 1
        assert self._current is not None
        # PROBE_SCORE 区分基础澄清与深入追问，均保留追问机会。
        target = self.prober.propose(
            question=self._scoring_target or self._current,
            result=result,
            depth=self._probe_depth,
            answer=answer, node_id=self._skill_node_id,
            basic=result.score < self.probe_score,
        )
        # 追问是围绕子话题展开的，评分锚点必须切换为该子话题，
        # 否则会用原题的锚点误判追问回答（真实面试语义）。
        self._skill_node_id = target.node_id
        self._turn_id = uuid.uuid4().hex
        self._scoring_target = Question(
            id=f"{self._current.id}#p{self._probe_depth}", position=self.position,
            theme=self._current.theme, difficulty=self._current.difficulty,
            content=target.content, answer_points=target.points,
        )
        self._question_event = {
                "type": EventType.QUESTION,
                "turn_id": self._turn_id,
                "skill_node_id": target.node_id,
                "id": f"{self._current.id}#p{self._probe_depth}",
                "theme": self._current.theme,
                "content": target.content,
                "is_probe": True,
                "probe_depth": self._probe_depth,
            }
        events.append(self._question_event)
        return events

    # ---- 收尾

    def _close_interview(self, events: list[dict]) -> list[dict]:
        if self.finished:
            return events
        if self.state in (
            InterviewState.QUESTIONING,
            InterviewState.PROBING,
            InterviewState.CODING,
        ):
            self._move(events, InterviewState.CLOSING)
        events.append(
            {
                "type": EventType.CLOSING,
                "text": (
                    "好，今天的问题就到这里。"
                    "稍后我会给你一份能力雷达图和逐题复盘，祝你拿到心仪的 offer。"
                ),
            }
        )
        self._move(events, InterviewState.REPORT)
        self._move(events, InterviewState.FINISHED)
        self.finished = True
        events.append({"type": EventType.REPORT_READY, "interview_id": self.interview_id})
        return events
