"""按独立主问题聚合，再按主题大纲权重聚合，追问数量不放大权重。"""
from collections import Counter, defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agent.skill_tree import SkillTree
from app.config import get_settings
from app.models.entities import Interview, TurnMetadata, ScoreOriginRecord
from app.score_origin import read_origin
from app.repositories import load_scores
from app.services.revision_links import revision_source

DIMENSION_KEYS = ("技术深度", "表达逻辑", "岗位匹配")


def build_report(db: Session, interview: Interview, skill_tree: SkillTree | None) -> dict:
    scores = load_scores(db, interview.id)
    origins = {o.score_id: read_origin(o.data) for o in db.scalars(select(ScoreOriginRecord).where(
        ScoreOriginRecord.score_id.in_([s.id for s in scores])))} if scores else {}
    meta = {m.score_id: m for m in db.scalars(select(TurnMetadata).where(
        TurnMetadata.score_id.in_([s.id for s in scores])))} if scores else {}
    groups = defaultdict(list)
    per_question = []
    for s in scores:
        m = meta.get(s.id)
        main_id = m.main_question_id if m else s.question_id.split("#p")[0]
        groups[(s.theme, main_id)].append(s)
        per_question.append({
            "question_id": s.question_id, "main_question_id": main_id,
            "turn_id": m.turn_id if m else None, "skill_node_id": m.skill_node_id if m else None,
            "theme": s.theme, "content": s.content, "answer_text": s.answer_text,
            "score": s.score, "probe_depth": s.probe_depth, "evidence": s.evidence,
            "key_points_hit": s.key_points_hit, "key_points_missed": s.key_points_missed,
            "sandbox": s.sandbox,
            "scoring_origin": origins.get(s.id, read_origin(None)),
        })
    theme_questions = defaultdict(list)
    for (theme, _), records in groups.items():
        dims = {}
        for key in DIMENSION_KEYS:
            values = [s.score if s.sandbox and key in ("技术深度", "岗位匹配")
                      else float(s.dimensions.get(key, s.score)) for s in records]
            dims[key] = sum(values) / len(values)
        theme_questions[theme].append((sum(s.score for s in records) / len(records), dims))
    theme_raw = {t: sum(s for s, _ in questions) / len(questions)
                 for t, questions in theme_questions.items()}
    weights = {p["theme"]: p["weight"] for p in interview.plan}
    # 编码主题不在大纲中时，采用已规划主题的平均权重。
    default_weight = sum(weights.values()) / len(weights) if weights else 1.0
    effective = {t: weights.get(t, default_weight) for t in theme_raw}
    total_weight = sum(effective.values()) or 1.0
    overall = sum(theme_raw[t] * w for t, w in effective.items()) / total_weight
    dimensions = {key: round(sum(
        sum(d[key] for _, d in theme_questions[t]) / len(theme_questions[t]) * w
        for t, w in effective.items()) / total_weight, 1) for key in DIMENSION_KEYS}
    weak = sorted((t for t, score in theme_raw.items() if score < get_settings().weak_score),
                  key=theme_raw.get)[:2]
    recommendations = []
    for theme in weak:
        children = skill_tree.children_of(theme) if skill_tree else []
        topics = "、".join(n.name for n in children[:3]) or "该主题核心概念"
        recommendations.append(f"「{theme}」得分 {theme_raw[theme]:.1f}：建议重点复习 {topics}")
    return {
        "interview_id": interview.id, "position": interview.position,
        "revision_source": revision_source(db, interview.id),
        "position_display_name": skill_tree.display_name if skill_tree else interview.position,
        "status": interview.status, "is_complete": interview.status == "finished",
        "is_cancelled": interview.status == "cancelled", "is_terminal": interview.status in ("finished", "cancelled"),
        "overall": round(overall, 1) if scores else None,
        "question_count": len(groups), "answer_count": len(scores),
        "dimensions": dimensions, "theme_avg": {t: round(v, 1) for t, v in theme_raw.items()},
        "weak_points": weak, "recommendations": recommendations, "per_question": per_question,
        "weak_score": get_settings().weak_score,
        "scoring_sources": dict(Counter(row["scoring_origin"]["source"] for row in per_question)),
        "message": "面试已取消，仅包含取消前已提交的回答" if interview.status == "cancelled" else ("暂无评分数据" if not scores else None),
        "aggregation": "每主题内各轮均值→主题内主问题等权→大纲主题加权；编码主题采用平均主题权重",
        "started_at": interview.started_at.isoformat() if interview.started_at else None,
        "ended_at": interview.ended_at.isoformat() if interview.ended_at else None,
    }
