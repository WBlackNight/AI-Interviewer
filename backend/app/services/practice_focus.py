"""Minimal read model for the latest completed practice, scoped to its owner.

Select numerical feedback only. Answers, question content and private evidence
never enter the dashboard. No long-term ability prediction is inferred.
"""
from sqlalchemy import select

from app.models.entities import Interview, QuestionScore, ResourceOwner, TurnMetadata, ScoreOriginRecord
from app.score_origin import read_origin
from app.services.score_aggregation import theme_score_summary


def latest_practice_focus(db, account_id, trees, threshold):
    has_scores = select(QuestionScore.id).where(QuestionScore.interview_id == Interview.id).exists()
    interview = db.scalar(select(Interview).join(ResourceOwner,
        (ResourceOwner.resource_kind == 'interview') & (ResourceOwner.resource_id == Interview.id))
        .where(ResourceOwner.account_id == account_id, Interview.status == 'finished', has_scores)
        .order_by(Interview.ended_at.desc().nullslast(), Interview.id.desc()).limit(1))
    if interview is None:
        return None
    rows = list(db.execute(select(QuestionScore.question_id, QuestionScore.theme, QuestionScore.score,
        TurnMetadata.main_question_id, ScoreOriginRecord.data).select_from(QuestionScore).outerjoin(TurnMetadata,
        TurnMetadata.score_id == QuestionScore.id).outerjoin(ScoreOriginRecord,
        ScoreOriginRecord.score_id == QuestionScore.id).where(QuestionScore.interview_id == interview.id)
        .order_by(QuestionScore.id)).mappings())
    themes = theme_score_summary(rows)
    tree = trees.get(interview.position)
    allowed = set(tree.root_names()) if tree else set()
    ordered = sorted(themes.items(), key=lambda item: (item[1]['score'], item[0]))
    return {
        'interview_id': interview.id, 'position': interview.position,
        'position_display_name': tree.display_name if tree else interview.position,
        'themes': [{'name': name, 'score': round(item['score'], 1),
                    'question_count': item['question_count'], 'can_practice': name in allowed,
                    'priority': item['score'] < threshold} for name, item in ordered[:3]],
        'sample_count': sum(item['question_count'] for item in themes.values()),
        'local_feedback': any(read_origin(row['data'])['source'] != 'llm' for row in rows),
        'note': '仅依据最近一场已完成练习；主问题各轮取均值，再在主题内等权。不与不同难度或评分方式的场次直接比较。',
    }
