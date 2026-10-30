"""题库公开预览→匿名/账户专项→真实HTTP/WS与重启；仅读合成数据、无外部模型。"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from urllib.parse import urlencode

from smoke_e2e import BACKEND, Server, request
from practice_smoke import complete, denied


async def run(server):
    def catalog(**params):
        return request(server.base, '/api/catalog?' + urlencode(params))
    first = catalog()
    assert first['position'] == 'java_backend'
    assert sum(role['total'] for role in first['positions']) == 18
    all_ids = set()
    for role in first['positions']:
        offset = 0
        while True:
            page = catalog(position=role['id'], offset=offset, limit=6)
            for row in page['items']:
                assert set(row) == {'id', 'position', 'theme', 'difficulty', 'content', 'source', 'is_coding', 'can_practice'}
                assert row['id'] not in all_ids
                all_ids.add(row['id'])
            if not page['has_more']:
                break
            offset += 6
    assert len(all_ids) == 18
    assert catalog(position='python_backend', theme='Python基础', difficulty='hard', kind='knowledge')['total'] == 0
    assert catalog(position='java_backend', q='jv-mysql-index-001')['total'] > 0
    assert catalog(position='java_backend', q='%')['total'] == 0
    coding = catalog(position='java_backend', kind='coding')
    assert coding['total'] == 1 and not coding['items'][0]['can_practice']
    assert coding['counts']['all'] == 11
    denied(server.base, '/api/catalog?limit=25', status=422)
    denied(server.base, '/api/catalog?position=missing', status=404)
    anonymous = request(server.base, '/api/interview', {'position': 'python_backend', 'themes': ['Python基础'], 'difficulty': 'hard'})
    assert anonymous['access_token'] and not anonymous['account_owned']
    await complete(server, anonymous, ['Python基础'])
    account = request(server.base, '/api/auth/register', {'username': 'catalog_demo', 'password': 'synthetic-catalog-password'})
    headers = {'Authorization': 'Bearer ' + account['access_token']}
    owned = request(server.base, '/api/interview', {'position': 'java_backend', 'themes': ['MySQL', 'Redis'], 'difficulty': 'mid'}, headers)
    assert owned['account_owned'] and owned['access_token'] is None
    assert {row['theme'] for row in owned['plan']} == {'MySQL', 'Redis'}
    assert all(not row['include_coding'] and row['question_count'] <= 2 for row in owned['plan'])
    before = catalog(position='python_backend', kind='coding')
    await asyncio.to_thread(server.restart)
    assert catalog(position='python_backend', kind='coding') == before
    assert request(server.base, '/api/account/interviews', headers=headers)['total'] == 1
    assert not request(server.base, '/api/diagnostics/llm')['llm_configured']
    return {'result': 'passed', 'synthetic_only': True, 'external_model_calls': 0,
            'public_preview_18_unique_questions': True, 'public_field_whitelist': True,
            'strict_browser_filter_and_literal_search': True, 'coding_excluded_from_topic_practice': True,
            'anonymous_practice_2_questions_8_rounds': True, 'account_two_theme_plan': True,
            'restart_preserves_catalog_and_ownership': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='.smoke-catalog-', dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / 'catalog.sqlite3')
        try:
            server.start()
            result = asyncio.run(run(server))
        finally:
            server.stop()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
