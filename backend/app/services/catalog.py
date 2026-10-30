"""当前运行题库的公开预览；仅读取题干与来源，不调用召回、模型或业务数据库。"""
from collections import Counter

from fastapi import HTTPException

from app.services.practice import available_themes


def question_catalog(trees, bank, *, position=None, theme=None, difficulty=None,
                     kind='all', query=None, offset=0, limit=6, theme_limit=3):
    questions = bank.questions
    positions = []
    for key, tree in trees.items():
        rows = [question for question in questions if question.position == key]
        if not rows:
            continue
        allowed = available_themes(tree, bank, key)
        topics = list(dict.fromkeys(tree.root_names() + sorted({question.theme for question in rows})))
        positions.append({'id': key, 'display_name': tree.display_name, 'total': len(rows),
            'knowledge': sum(not row.is_coding for row in rows), 'coding': sum(row.is_coding for row in rows),
            'practice_theme_limit': min(12, theme_limit),
            'themes': [{'name': topic, 'question_count': sum(row.theme == topic for row in rows),
                        'knowledge_count': sum(row.theme == topic and not row.is_coding for row in rows),
                        'can_practice': topic in allowed,
                        'topics': [node.name for node in tree.children_of(topic)[:4]]} for topic in topics]})
    if position is None:
        position = positions[0]['id'] if positions else None
    selected = next((item for item in positions if item['id'] == position), None)
    if position is not None and selected is None:
        raise HTTPException(404, '该岗位当前没有可浏览题目，请选择可用岗位')
    query = (query or '').strip()
    pool = [question for question in questions if question.position == position]
    if theme is not None:
        pool = [question for question in pool if question.theme == theme]
    if difficulty is not None:
        pool = [question for question in pool if question.difficulty == difficulty]
    if query:
        term = query.casefold()
        pool = [question for question in pool if term in '\n'.join(
            [question.id, question.theme, question.content, question.source]).casefold()]
    counts = Counter('coding' if question.is_coding else 'knowledge' for question in pool)
    if kind != 'all':
        pool = [question for question in pool if question.is_coding == (kind == 'coding')]
    order = {'easy': 0, 'mid': 1, 'hard': 2}
    pool.sort(key=lambda question: (question.theme, order.get(question.difficulty, 3), question.id))
    allowed = {item['name'] for item in selected['themes'] if item['can_practice']} if selected else set()
    # 明确白名单，不序列化Question本体，避免把评分锚点或判题用例带到预览。
    items = [{'id': row.id, 'position': row.position, 'theme': row.theme, 'difficulty': row.difficulty,
              'content': row.content, 'source': row.source, 'is_coding': row.is_coding,
              'can_practice': not row.is_coding and row.theme in allowed} for row in pool[offset:offset + limit]]
    return {'positions': positions, 'position': position, 'theme': theme, 'difficulty': difficulty,
            'kind': kind, 'query': query, 'items': items, 'total': len(pool), 'offset': offset, 'limit': limit,
            'has_more': offset + len(items) < len(pool),
            'counts': {'all': sum(counts.values()), 'knowledge': counts['knowledge'], 'coding': counts['coding']},
            'note': '浏览难度严格匹配；专项按主题创建，每主题最多2道主问题并保留追问，实际题目与难度可能放宽，不锁定本页预览题。'}
