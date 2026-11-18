"""Shared aggregation contract: rounds → main questions → themes.

No database or model dependency. Repeated follow-ups never increase a main
question's weight. Keep precision until the presentation boundary.
"""
from collections import defaultdict


def group_question_rounds(rows):
    groups = defaultdict(list)
    for row in rows:
        main_id = row.get('main_question_id') or row['question_id'].split('#p')[0]
        groups[(row['theme'], main_id)].append(row)
    return groups


def theme_score_summary(rows):
    themes = defaultdict(list)
    for (theme, _), rounds in group_question_rounds(rows).items():
        themes[theme].append(sum(row['score'] for row in rounds) / len(rounds))
    return {theme: {'score': sum(scores) / len(scores), 'question_count': len(scores)}
            for theme, scores in themes.items()}
