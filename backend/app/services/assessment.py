"""Evidence-based diagnostics derived from an existing report, with no model call."""
from app.services.score_aggregation import group_question_rounds


def assessment_summary(per_question, *, threshold, complete):
    groups = group_question_rounds(per_question)
    cards = []
    for (theme, main_id), rows in groups.items():
        main = next((row for row in rows if row['probe_depth'] == 0), rows[0])
        hit = list(dict.fromkeys(point for row in rows for point in row['key_points_hit']))
        # Follow-ups assess different anchors. Preserve the remaining gaps of the main question.
        missed = [point for point in main['key_points_missed'] if point not in hit]
        score = sum(row['score'] for row in rows) / len(rows)
        cards.append({
            'question_id': main_id, 'theme': theme, 'content': main['content'],
            'score': round(score, 1), 'round_count': len(rows),
            'strengths': hit[:4], 'gaps': missed[:4],
            'next_step': ('围绕“' + missed[0] + '”，补充原因和一个具体例子。') if missed
                         else '换一个情境，练习解释边界与取舍。',
            'evidence': main['evidence'],
        })
    ordered = sorted(cards, key=lambda card: card['score'])
    strong = sorted((card for card in cards if card['score'] >= threshold and card['strengths']),
                    key=lambda card: -card['score'])[:2]
    focus = [card for card in ordered if card['score'] < threshold][:3]
    return {
        'status': 'complete' if complete else 'partial',
        'summary': f'已完成 {len(cards)} 道主问题、{len(per_question)} 轮作答。' if cards else '完成作答后查看具体反馈。',
        'strengths': [{'theme': card['theme'], 'point': card['strengths'][0]} for card in strong],
        'priorities': [{'theme': card['theme'], 'question_id': card['question_id'],
                        'action': card['next_step']} for card in focus],
        'questions': cards,
    }
