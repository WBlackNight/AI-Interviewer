"""离线生成或校验候选资产包，不读取.env、调用模型或自动激活。"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.question_release import ReleaseError, prepare_release, verify_release


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank-dir', type=Path, default=ROOT / 'data/question_bank')
    parser.add_argument('--skill-tree-dir', type=Path, default=ROOT / 'data/skill_tree')
    parser.add_argument('--candidates', type=Path, default=ROOT / 'data/question_candidates')
    parser.add_argument('--skill-overrides', type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path)
    action.add_argument('--verify', type=Path)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args(argv)
    bundle = (args.verify or args.output).resolve()
    protected = [bundle, args.bank_dir.resolve(), args.skill_tree_dir.resolve(), args.candidates.resolve()]
    if args.skill_overrides:
        protected.append(args.skill_overrides.resolve())
    if args.json_out and any(args.json_out.resolve().is_relative_to(path) for path in protected):
        print(json.dumps({'result': 'failed', 'activated': False, 'external_model_calls': 0,
                          'error_code': 'report_overlaps_release'}))
        return 1
    try:
        manifest = (verify_release(args.verify) if args.verify else prepare_release(
            args.bank_dir, args.skill_tree_dir, args.candidates, args.output, skill_overrides=args.skill_overrides))
        result = {'result': 'passed', 'action': 'verify' if args.verify else 'prepare',
                  'activated': False, 'semantic_model': False, 'external_model_calls': 0,
                  'expert_review_verified': False, 'variants': manifest['variants']}
    except Exception as exc:
        result = {'result': 'failed', 'activated': False, 'external_model_calls': 0,
                  'error_code': str(exc) if isinstance(exc, ReleaseError) else 'assets_unreadable_or_invalid'}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['result'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
