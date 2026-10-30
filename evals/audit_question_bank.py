"""只读审校当前题库和可选候选目录；不读取.env，不改题库、索引或业务数据库。"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.agent.skill_tree import load_skill_tree
from app.services.question_audit import audit_directories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank-dir', type=Path, default=ROOT / 'data/question_bank')
    parser.add_argument('--skill-tree-dir', type=Path, default=ROOT / 'data/skill_tree')
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--candidates', type=Path)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    try:
        trees = load_skill_tree(args.skill_tree_dir)
        if not trees: raise ValueError('empty trees')
        result = audit_directories(args.bank_dir, trees, args.sources or args.bank_dir / 'source_registry.json', args.candidates)
    except (OSError, ValueError):
        result = {'result': 'failed', 'activated': False, 'errors': [{'code': 'ASSETS_UNREADABLE'}]}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['result'] == 'passed' else 1


if __name__ == '__main__': sys.exit(main())
