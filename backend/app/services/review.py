"""账户内已完成面试的主题对照；仅读取评分数值与版本，不读取原回答。"""
from collections import Counter, defaultdict
from datetime import timezone

from sqlalchemy import select, func
from sqlalchemy.orm import aliased

from app.agent.skill_tree import load_skill_tree
from app.models.entities import Interview, QuestionScore, ResourceOwner, ScoreOriginRecord, TurnMetadata, PreparationPractice
from app.score_origin import read_origin


def account_review(db, account_id, skill_tree_dir, *, position=None, theme=None, offset=0, limit=20, plan_id=None):
    ownership = ((ResourceOwner.resource_kind == "interview") &
                 (ResourceOwner.resource_id == Interview.id) & (ResourceOwner.account_id == account_id))
    scope = Interview.id.in_(select(PreparationPractice.interview_id).where(PreparationPractice.plan_id == plan_id)) if plan_id is not None else True
    if plan_id is not None and position is not None:
        scope = scope & (Interview.position == position)
    facets = db.execute(select(Interview.position, QuestionScore.theme).join(ResourceOwner, ownership)
        .join(QuestionScore, QuestionScore.interview_id == Interview.id)
        .where(Interview.status == "finished", scope).distinct().order_by(Interview.position, QuestionScore.theme)).all()
    grouped = defaultdict(list)
    for pos, topic in facets:
        grouped[pos].append(topic)
    trees = load_skill_tree(skill_tree_dir)
    positions = [{"id": pos, "display_name": trees[pos].display_name if pos in trees else pos,
                  "themes": topics} for pos, topics in grouped.items()]
    position = position if position is not None else (positions[0]["id"] if positions else None)
    if plan_id is not None and theme is None:
        theme = next(iter(grouped.get(position, [])), None)
    matching_score = select(QuestionScore.id).where(QuestionScore.interview_id == Interview.id)
    if theme is not None:
        matching_score = matching_score.where(QuestionScore.theme == theme)
    selected = select(Interview).join(ResourceOwner, ownership).where(
        Interview.status == "finished", Interview.position == position, matching_score.exists(), scope)
    total = db.scalar(select(func.count()).select_from(selected.subquery()))
    interviews = list(db.scalars(selected.order_by(Interview.ended_at.desc().nullslast(), Interview.id.desc())
                                .offset(offset).limit(limit)))
    ids = [i.id for i in interviews]
    items = []
    if ids:
        previous_score, previous_origin = aliased(QuestionScore), aliased(ScoreOriginRecord)
        previous_interview, previous_owner = aliased(Interview), aliased(ResourceOwner)
        # “重复”仅指当前账户另一已完成面试中，此主问题首次作答之前的同ID同版本题。
        seen = select(previous_score.id).join(previous_origin, previous_origin.score_id == previous_score.id)
        seen = seen.join(previous_interview, previous_interview.id == previous_score.interview_id)
        seen = seen.join(previous_owner, (previous_owner.resource_kind == "interview") &
                         (previous_owner.resource_id == previous_interview.id))
        seen = seen.where(previous_owner.account_id == account_id, previous_interview.status == "finished",
            previous_interview.position == position, previous_score.interview_id != QuestionScore.interview_id,
            previous_score.id < QuestionScore.id, previous_score.theme == QuestionScore.theme,
            previous_origin.data["main_question_id"].as_string() == ScoreOriginRecord.data["main_question_id"].as_string(),
            previous_origin.data["main_question_version"].as_string() == ScoreOriginRecord.data["main_question_version"].as_string()
        ).correlate(QuestionScore, ScoreOriginRecord).exists()
        query = select(QuestionScore.id, QuestionScore.interview_id, QuestionScore.theme,
            QuestionScore.question_id, QuestionScore.score, ScoreOriginRecord.data,
            TurnMetadata.main_question_id, seen.label("seen")).outerjoin(ScoreOriginRecord,
            ScoreOriginRecord.score_id == QuestionScore.id).outerjoin(TurnMetadata,
            TurnMetadata.score_id == QuestionScore.id).where(QuestionScore.interview_id.in_(ids))
        if theme is not None:
            query = query.where(QuestionScore.theme == theme)
        rounds = defaultdict(list)
        for row in db.execute(query.order_by(QuestionScore.id)):
            rounds[(row.interview_id, row.theme)].append(row)
        for interview in interviews:
            for (_, topic), records in sorted((key, value) for key, value in rounds.items() if key[0] == interview.id):
                mains, origins, profiles = defaultdict(list), Counter(), {}
                for row in records:
                    origin = read_origin(row.data)
                    main_id = row.main_question_id or origin.get("main_question_id") or row.question_id.split("#p")[0]
                    mains[main_id].append(row)
                    origins[origin["source"]] += 1
                    fields = ("source", "scorer_version", "model", "prompt_version", "prompt_digest",
                              "config_version", "fallback_reason", "sandbox_applied")
                    key = tuple(origin.get(field) for field in fields)
                    profile = profiles.setdefault(key, {field: origin.get(field) for field in fields} |
                        {"answer_count": 0, "cached_count": 0})
                    profile["answer_count"] += 1
                    profile["cached_count"] += bool(origin["cached"])
                known, repeated, difficulties = 0, 0, Counter()
                for rows in mains.values():
                    first = rows[0]
                    origin = read_origin(first.data)
                    if origin.get("main_question_version"):
                        known += 1
                        repeated += bool(first.seen)
                    difficulties[origin.get("question_difficulty") or "unknown"] += 1
                avg = sum(sum(r.score for r in rows) / len(rows) for rows in mains.values()) / len(mains)
                items.append({"interview_id": interview.id, "position": interview.position,
                    "position_display_name": trees[position].display_name if position in trees else position,
                    "theme": topic, "difficulty": interview.difficulty,
                    "ended_at": interview.ended_at.astimezone(timezone.utc).isoformat() if interview.ended_at else None,
                    "score": round(avg, 1), "question_count": len(mains), "answer_count": len(records),
                    "repeat_question_count": repeated, "known_question_version_count": known,
                    "unknown_question_version_count": len(mains) - known,
                    "question_difficulties": dict(difficulties), "scoring_sources": dict(origins),
                    "scoring_profiles": list(profiles.values())})
    return {"positions": positions, "position": position, "theme": theme, "items": items,
            "total": total, "offset": offset, "limit": limit, "has_more": offset + len(ids) < total,
            "session_count": len(ids), "completed_only": True,
            "aggregation": "同一主问题各轮均值→同主题内主问题等权；每行是一场面试的一个主题",
            "repeat_definition": "本账户另一已完成面试中，在本题首次作答前出现的同ID同版本主问题；旧题版本未记录时不判定",
            "note": "不同题目、难度、评分来源及版本可能影响分数；记录对照不代表能力提升。"}
