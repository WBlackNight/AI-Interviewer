"""Assistant smoke probe; --live explicitly enables configured model calls with public input."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.factories import load_assets
from app.services.assistant import respond


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    # Use the normal backend configuration location, without printing its values.
    os.chdir(ROOT / 'backend')
    settings = Settings(retrieval_provider='bm25', embedding_provider='hash')
    if args.live and not settings.llm_api_key:
        raise SystemExit('No configured model; live probe not run.')
    trees, bank = load_assets(settings)
    started = time.monotonic()
    events, first_delta = [], None
    for item in respond(settings, trees, bank, position='java_backend',
        text='我准备Java后端面试，请先检索题库，再用一个例子解释MySQL联合索引的使用边界，并推荐一道练习题。',
        allow_model=args.live):
        if item['type'] == 'delta' and first_delta is None:
            first_delta = round(time.monotonic() - started, 3)
        events.append(item)
    mode = next((item['value'] for item in reversed(events) if item['type'] == 'mode'), None)
    evidence = next((item for item in events if item['type'] == 'evidence'), {})
    result = {'passed': mode == ('ai' if args.live else 'local') and not any(item['type'] == 'error' for item in events),
        'live': args.live, 'mode': mode, 'workflow': evidence.get('workflow'),
        'source_count': len(evidence.get('sources', [])), 'delta_count': sum(item['type'] == 'delta' for item in events),
        'first_delta_seconds': first_delta, 'elapsed_seconds': round(time.monotonic() - started, 3),
        'note': 'One public synthetic query; not a semantic quality benchmark or load test.'}
    if args.output:
        target = args.output if args.output.is_absolute() else ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
