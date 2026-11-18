"""Narrow regression guard for observed index misconceptions, not a general fact checker."""
import re


def grounding_issues(sources, answer):
    if not any(source.get('id') == 'G1' and source.get('title', '').startswith('联合索引：') for source in sources):
        return []
    issues = []
    for clause in re.split(r'[。！？\n；;]', answer):
        # Do not reject explanations which explicitly refute these claims.
        if re.search(r'不能|不应|并非|不是|不等同|不意味着|未必|不一定|不保证|无关|不影响|不取决|无需', clause):
            continue
        if re.search(r'(?:WHERE|where|查询条件).{0,25}(?:必须|需要|应当).{0,12}(?:按照|遵循|保持).{0,12}(?:索引|列).{0,8}顺序', clause):
            issues.append('where_order')
        if (re.search(r'(?:等同|相当|一样|一致).{0,18}多个.{0,10}索引', clause)
                or re.search(r'多个.{0,10}索引.{0,15}(?:相当|一样|等同|一致)', clause)):
            issues.append('index_cost')
        if re.search(r'(?:优化器|数据库).{0,15}(?:必然|一定|总是|必定).{0,12}(?:选择|使用).{0,8}(?:联合)?索引', clause):
            issues.append('optimizer_guarantee')
    return sorted(set(issues))
