"""公开覆盖与来源HTTP冒烟；隔离服务、重启一致，不调用供应商或修改题库。"""
import argparse
import json
from pathlib import Path
import tempfile

from smoke_e2e import BACKEND, Server, request
from practice_smoke import denied


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--json-out', type=Path); args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='.smoke-coverage-', dir=BACKEND) as directory:
        server = Server(Path(directory).resolve() / 'coverage.sqlite3')
        try:
            server.start()
            result = request(server.base, '/api/catalog/coverage')
            assert result['counts'] == {'all': 18, 'knowledge': 16, 'coding': 2, 'knowledge_themes': 9,
                'missing_cells': 13, 'under_two_questions': 3, 'unregistered': 0, 'not_reference_checked': 18, 'unmapped': 0}
            assert len(result['themes']) == 11 and sum(row['coding_only'] for row in result['themes']) == 2
            assert len(result['sources']) == 2 and all(row['review_state'] == 'unreviewed' for row in result['sources'])
            assert 'answer_points' not in str(result) and 'testcases' not in str(result)
            for position, count, gaps in [('java_backend', 11, 10), ('python_backend', 7, 3)]:
                scoped = request(server.base, '/api/catalog/coverage?position=' + position)
                assert scoped['counts']['all'] == count and scoped['counts']['missing_cells'] == gaps
                assert scoped['corpus_sha256'] == result['corpus_sha256']
            denied(server.base, '/api/catalog/coverage?position=missing', status=404)
            server.restart()
            assert request(server.base, '/api/catalog/coverage') == result
            assert request(server.base, '/api/health')['question_count'] == 18
            assert not request(server.base, '/api/diagnostics/llm')['llm_configured']
        finally: server.stop()
    evidence = {'result': 'passed', 'synthetic_only': True, 'external_model_calls': 0,
        'active_questions': 18, 'missing_knowledge_difficulty_cells': 13,
        'scope_and_global_version': True, 'unreviewed_sources_explicit': True,
        'public_fields_only': True, 'restart_consistent': True, 'candidate_not_activated': True}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == '__main__': main()
