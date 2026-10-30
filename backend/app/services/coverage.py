"""当前运行题库的公开覆盖统计；缺口指题目数量，不推断主题覆盖质量。"""
from collections import Counter

from fastapi import HTTPException

from app.rag.vector_index import corpus_version


def catalog_coverage(trees, bank, registry, registry_state, position=None):
    if position is not None and position not in trees:
        raise HTTPException(404, '岗位不存在，请清除筛选后重试')
    questions = bank.questions
    positions = [{'id': key, 'display_name': tree.display_name} for key, tree in trees.items()]
    rows = [q for q in questions if position is None or q.position == position]
    themes, roles = [], []
    for key, tree in trees.items():
        if position is not None and key != position:
            continue
        role_rows = [q for q in rows if q.position == key]
        roles.append({'id': key, 'display_name': tree.display_name, 'total': len(role_rows),
                      'knowledge': sum(not q.is_coding for q in role_rows), 'coding': sum(q.is_coding for q in role_rows)})
        for name in tree.root_names():
            topic = [q for q in role_rows if q.theme == name]
            knowledge = [q for q in topic if not q.is_coding]
            counts = {level: sum(q.difficulty == level for q in knowledge) for level in ('easy', 'mid', 'hard')}
            # 仅编码主题不算知识难度缺口；空主题仍列出，供维护者确认题型。
            coding_only = bool(topic) and all(q.is_coding for q in topic)
            themes.append({'position': key, 'position_name': tree.display_name, 'theme': name,
                           'knowledge': len(knowledge), 'coding': sum(q.is_coding for q in topic),
                           'coding_only': coding_only, 'difficulties': counts,
                           'missing_difficulties': [] if coding_only else [level for level, count in counts.items() if count == 0]})
    sources = []
    for source_id, count in sorted(Counter(q.source for q in rows).items()):
        source = registry.get(source_id)
        sources.append({'id': source_id, 'count': count, 'registered': source is not None,
                        'label': source['label'] if source else '未登记来源',
                        'origin': source['origin'] if source else 'unknown',
                        'review_state': source['review_state'] if source else 'unregistered',
                        'references': source['references'] if source else []})
    knowledge_themes = [row for row in themes if not row['coding_only']]
    return {'position': position, 'positions': positions, 'roles': roles, 'themes': themes, 'sources': sources,
            'registry_state': registry_state, 'corpus_sha256': corpus_version(questions),
            'counts': {'all': len(rows), 'knowledge': sum(not q.is_coding for q in rows),
                       'coding': sum(q.is_coding for q in rows), 'knowledge_themes': len(knowledge_themes),
                       'missing_cells': sum(len(row['missing_difficulties']) for row in knowledge_themes),
                       'under_two_questions': sum(row['knowledge'] < 2 for row in knowledge_themes),
                       'unregistered': sum(row['count'] for row in sources if not row['registered']),
                       'not_reference_checked': sum(row['count'] for row in sources if row['review_state'] != 'reference_checked'),
                       'unmapped': sum(q.position not in trees or q.theme not in trees[q.position].root_names() for q in rows)},
            'note': '缺口按知识根主题×基础/进阶/挑战统计；仅编码主题不计入，空主题待人工确认。数量与资料核对均不等于专家审题、独立评测或能力覆盖。'}
