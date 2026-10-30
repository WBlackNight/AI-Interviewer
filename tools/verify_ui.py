"""Native frontend verification entry point for local development and CI."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'evals')]
from build_ui import build
from native_home_check import check


def verify():
    build(check=True)
    structural = check()
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required for frontend verification')
    commands = [[node, '--check', str(p)] for p in sorted((ROOT / 'assets').glob('*.js'))]
    commands += [[node, 'evals/' + name] for name in
                 ('ui_core_check.mjs', 'account_ui_check.mjs', 'account_menu_check.mjs', 'home_interaction_check.mjs', 'carousel_check.mjs', 'microphone_check.mjs', 'voice_ui_check.mjs', 'realtime_ui_check.mjs')]
    commands.append([node, '--test', 'evals/native_interview_test.cjs'])
    results = []
    for command in commands:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=60)
        results.append({'command': command[1:], 'exit_code': run.returncode,
                        'stdout': run.stdout[-6000:], 'stderr': run.stderr[-6000:]})
    return {'result': 'passed' if all(r['exit_code'] == 0 for r in results) else 'failed',
            'structure': structural, 'checks': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    result = verify()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': result['result'], 'checks': len(result['checks'])}))
    sys.exit(0 if result['result'] == 'passed' else 1)
