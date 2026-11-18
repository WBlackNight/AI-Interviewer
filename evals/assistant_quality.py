"""Offline, authored regression cases for known grounding failures; not an independent AI benchmark."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.assistant_grounding import grounding_issues


def evaluate():
    sources = [{'id': 'G1', 'title': '联合索引：列顺序、查询条件与优化器'}]
    cases = [json.loads(line) for line in (ROOT / 'data/evals/assistant_grounding.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({row['case_id'] for row in cases}) != len(cases):
        raise ValueError('Duplicate case id')
    rows = [{'case_id': row['case_id'], 'expected_reject': row['reject'],
             'issues': grounding_issues(sources, row['answer'])} for row in cases]
    for row in rows:
        row['passed'] = bool(row['issues']) == row['expected_reject']
    return {'passed': all(row['passed'] for row in rows), 'cases': len(rows), 'results': rows,
            'note': 'Authored regression cases for three observed index misconceptions. No general factual accuracy, expert review or RAG improvement claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'cases': result['cases']}))
    raise SystemExit(0 if result['passed'] else 1)
