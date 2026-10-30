"""面试会话端到端测试：验证状态机驱动的完整流程。

场景覆盖：
1. 正常通关：高分回答直通，含编码环节，最终产出报告事件；
2. 薄弱回答：触发动态追问、深度上限、放弃推进；
3. 事件流完整性：所有状态变更都有对应 state 事件。
"""
from __future__ import annotations

import pytest

from app.agent.planner import HeuristicPlanner
from app.agent.prober import SkillTreeProber
from app.agent.session import InterviewSession
from app.agent.skill_tree import SkillTree
from app.agent.scorer import HeuristicScorer
from app.domain import EventType, PlanItem, Question, ResumeData
from app.rag.question_bank import QuestionBank

PASS_ANSWER = "b+树 是多路平衡搜索树，叶子节点构成有序链表支持范围查询，" + "相比哈希索引它适合区间扫描，" + "磁盘IO次数取决于树高，" + "这些特性让 MySQL 选择它，" + "另外我在项目里也实际做过索引优化，补充细节 " * 10
WEAK_ANSWER = "不太清楚，没了解过"


def _bank() -> QuestionBank:
    questions = [
        Question.from_dict(
            {
                "id": "q-a1",
                "position": "java_backend",
                "theme": "MySQL",
                "difficulty": "mid",
                "content": "题目A1",
                "answer_points": [
                    {"point": "要点1", "keywords": ["b+树"]},
                    {"point": "要点2", "keywords": ["范围查询"]},
                    {"point": "要点3", "keywords": ["树高"]},
                ],
            }
        ),
        Question.from_dict(
            {
                "id": "q-b1",
                "position": "java_backend",
                "theme": "Redis",
                "difficulty": "mid",
                "content": "题目B1",
                "answer_points": [{"point": "穿透", "keywords": ["布隆"]}],
            }
        ),
        Question.from_dict(
            {
                "id": "q-c1",
                "position": "java_backend",
                "theme": "MySQL",
                "difficulty": "mid",
                "content": "编程题",
                "answer_points": [{"point": "哈希解法", "keywords": ["哈希"]}],
                "is_coding": True,
                "testcases": [{"input": "1 2", "expected": "3"}],
            }
        ),
    ]
    return QuestionBank(questions)


def _skill_tree() -> SkillTree:
    from app.agent.skill_tree import load_skill_tree
    import tempfile, yaml
    from pathlib import Path

    data = {
        "position": "java_backend",
        "display_name": "Java 后端",
        "roots": [
            {"name": "MySQL", "children": ["索引结构", "事务隔离"]},
            {"name": "Redis", "children": ["缓存三大问题"]},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        trees = load_skill_tree(Path(tmp))
    return trees["java_backend"]


def _plan(bank: QuestionBank) -> list[PlanItem]:
    return [
        PlanItem(theme="MySQL", weight=0.6, difficulty="mid", question_count=1, include_coding=True),
        PlanItem(theme="Redis", weight=0.4, difficulty="mid", question_count=1),
    ]


def _session(bank: QuestionBank, **kwargs) -> InterviewSession:
    defaults = dict(
        interview_id="test-1",
        position="java_backend",
        plan=_plan(bank),
        bank=bank,
        scorer=HeuristicScorer(),
        prober=SkillTreeProber(_skill_tree()),
    )
    defaults.update(kwargs)
    return InterviewSession(**defaults)


def _events_of(events: list[dict], etype: str) -> list[dict]:
    return [e for e in events if e["type"] == etype]


class TestHappyPath:
    def test_full_pass_flow_reaches_report(self):
        """单主题（含编码题）高分通关：提问 → 编码 → 收尾 → 报告。"""
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="MySQL", weight=1.0, difficulty="mid", question_count=1, include_coding=True),
        ])

        events = session.start()
        assert events[0]["type"] == EventType.GREETING
        questions = _events_of(events, EventType.QUESTION)
        assert len(questions) == 1 and not questions[0].get("is_coding")

        # 第一题：高分通过 → 编码题
        events = session.handle_answer(PASS_ANSWER)
        assert session.state.value == "coding"
        coding = _events_of(events, EventType.QUESTION)
        assert coding[0]["is_coding"] is True and coding[0]["testcases"]

        # 编码题：高分 → 收尾 → 报告
        events = session.handle_answer("哈希表一次遍历，时间复杂度 O(n)，" + "边界处理 " * 40)
        assert _events_of(events, EventType.CLOSING)
        assert session.finished is True
        assert _events_of(events, EventType.REPORT_READY)

        records = session.records
        assert len(records) == 2
        assert all(r.result.score >= 7.0 for r in records)

    def test_state_events_mirror_transitions(self):
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="MySQL", weight=1.0, difficulty="mid", question_count=1, include_coding=True),
        ])
        all_events = list(session.start())
        all_events += session.handle_answer(PASS_ANSWER)
        all_events += session.handle_answer("哈希表遍历 " * 30)
        states = [e["state"] for e in _events_of(all_events, EventType.STATE)]
        assert states[0] == "questioning"
        assert "coding" in states and "closing" in states and "finished" in states
        # 状态序列必须相邻合法（复用转移表校验）
        from app.agent.state_machine import ALLOWED_TRANSITIONS, InterviewState

        for prev, nxt in zip(states, states[1:]):
            assert InterviewState(nxt) in ALLOWED_TRANSITIONS[InterviewState(prev)]


class TestProbing:
    def test_weak_answer_triggers_probe_with_depth_limit(self):
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="MySQL", weight=1.0, difficulty="mid", question_count=1),
        ])
        session.start()

        # 连续弱回答：每次触发一层追问，直到深度上限后放弃推进
        total_probes = 0
        for _ in range(6):
            events = session.handle_answer(WEAK_ANSWER)
            probes = [
                q for q in _events_of(events, EventType.QUESTION) if q.get("is_probe")
            ]
            total_probes += len(probes)
            if session.finished:
                break

        # 深度上限 = 3：该题最多被追问 3 次
        assert total_probes == 3
        assert session.finished  # 无编码题，弱回答耗尽后直接收尾

    def test_probe_text_keeps_original_missed_anchor_when_tree_names_do_not_match(self):
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="MySQL", weight=1.0, difficulty="mid", question_count=1),
        ])
        session.start()
        events = session.handle_answer(WEAK_ANSWER)
        probe = [q for q in _events_of(events, EventType.QUESTION)][0]
        assert "要点1" in probe["content"] and "索引结构" not in probe["content"]

    def test_recovery_from_probe_returns_to_questioning(self):
        """追问答得好 → 通过追问 → 回到主流程推下一主题。

        合格回答应解释当前追问的真实锚点，而不是重复任意技能节点名。
        """
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="MySQL", weight=0.5, difficulty="mid", question_count=1),
            PlanItem(theme="Redis", weight=0.5, difficulty="mid", question_count=1),
        ])
        session.start()
        # 弱回答触发追问
        events = session.handle_answer(WEAK_ANSWER)
        assert session.state.value == "probing"
        probe = [q for q in _events_of(events, EventType.QUESTION) if q.get("is_probe")][0]
        strong_answer = "B+树的多路结构降低树高，使一次查询读取更少的磁盘页。" + "因为层数减少，所以读取成本下降。" * 20

        events = session.handle_answer(strong_answer)
        assert session.state.value == "questioning"
        next_q = _events_of(events, EventType.QUESTION)[0]
        assert next_q["theme"] == "Redis"


class TestEdgeCases:
    def test_answer_before_start_rejected(self):
        bank = _bank()
        session = _session(bank)
        events = session.handle_answer("任意回答")
        assert events[0]["type"] == EventType.ERROR

    def test_double_start_rejected(self):
        bank = _bank()
        session = _session(bank)
        session.start()
        events = session.start()
        assert events[0]["type"] == EventType.ERROR

    def test_answer_after_finish_rejected(self):
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="MySQL", weight=1.0, difficulty="mid", question_count=1),
        ])
        session.start()
        for _ in range(6):
            session.handle_answer(WEAK_ANSWER)
        assert session.finished
        events = session.handle_answer("还有话说")
        assert events[0]["type"] == EventType.ERROR

    def test_theme_without_questions_skipped_gracefully(self):
        bank = _bank()
        session = _session(bank, plan=[
            PlanItem(theme="不存在的主题", weight=0.5, difficulty="mid", question_count=1),
            PlanItem(theme="MySQL", weight=0.5, difficulty="mid", question_count=1),
        ])
        events = session.start()
        questions = _events_of(events, EventType.QUESTION)
        # 首主题无题 → 自动落到 MySQL
        assert questions and questions[0]["theme"] == "MySQL"


class TestPlannerIntegration:
    def test_heuristic_planner_prefers_resume_skills(self):
        trees = {"java_backend": _skill_tree()}
        bank = _bank()
        planner = HeuristicPlanner(trees["java_backend"])
        resume = ResumeData(skills=["MySQL", "Spring"])
        plan = planner.build_plan(
            position="java_backend",
            difficulty="mid",
            resume=resume,
            bank=bank,
            max_themes=2,
        )
        assert plan, "应至少产出一个主题"
        # 简历命中的 MySQL 必须进大纲
        assert "MySQL" in [p.theme for p in plan]
        # 只有题库有题的主题才进大纲（Redis 有题、不存在主题被过滤）
        bank_themes = {"MySQL", "Redis"}
        assert all(p.theme in bank_themes for p in plan)
