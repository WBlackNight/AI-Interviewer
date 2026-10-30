import json
from pathlib import Path

from app.agent.skill_tree import SkillTree, SkillNode, load_skill_tree
from app.services.question_audit import audit_directories, load_registry

ROOT = Path(__file__).resolve().parents[2]


def files(tmp_path, rows):
    bank = tmp_path / 'bank'; bank.mkdir()
    (bank / 'test.jsonl').write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
    registry = bank / 'source_registry.json'
    registry.write_text(json.dumps({'format_version': 1, 'sources': [{'id': 'builtin', 'label': 'synthetic',
        'origin': 'self_authored', 'review_state': 'unreviewed', 'references': []}]}), encoding='utf-8')
    tree = {'java_backend': SkillTree('java_backend', 'Java', [SkillNode('MySQL')])}
    return bank, registry, tree


def row(**changes):
    return {'id': 'q1', 'position': 'java_backend', 'theme': 'MySQL', 'difficulty': 'mid', 'content': 'synthetic question',
            'answer_points': [{'point': 'private-point', 'keywords': ['private-answer']}], **changes}


def test_repository_bank_and_six_candidates_are_read_only_structurally_valid():
    paths = list((ROOT/'data/question_bank').glob('*.jsonl')) + list((ROOT/'data/retrieval').glob('*.json'))
    before = {path: path.read_bytes() for path in paths}
    result = audit_directories(ROOT/'data/question_bank', load_skill_tree(ROOT/'data/skill_tree'),
        ROOT/'data/question_bank/source_registry.json', ROOT/'data/question_candidates')
    assert result['result'] == 'passed' and result['active_count'] == 120 and result['candidate_count'] == 6
    assert len(result['warnings']) == 108 and not result['expert_review_verified'] and not result['activated']
    assert result['active_corpus_sha256'] != result['combined_corpus_sha256']
    assert all(path.read_bytes() == content for path, content in before.items())


def test_schema_errors_are_bounded_and_never_echo_private_values(tmp_path):
    samples = [row(is_coding='false'), row(answer_points=[]), row(content=' '), row(extra='private-secret'),
               row(is_coding=True), row(testcases=[{'input': 'private-secret', 'expected': ''}]),
               row(answer_points=[{'point': 'p', 'keywords': [' ']}]), row(difficulty='advanced')]
    bank, registry, trees = files(tmp_path, samples)
    result = audit_directories(bank, trees, registry)
    assert len(result['errors']) == len(samples)
    assert {item['code'] for item in result['errors']} == {'INVALID_QUESTION_SCHEMA'}
    assert 'private-' not in json.dumps(result)
    assert result['result'] == 'failed' and result['active_count'] == 0


def test_duplicates_sources_and_root_mapping_include_candidate_collisions(tmp_path):
    bank, registry, trees = files(tmp_path, [row()])
    candidates = tmp_path/'drafts'; candidates.mkdir()
    rows = [row(), row(id='q2', content='syntheticquestion'), row(id='q3', content='other', theme='missing'),
            row(id='q4', content='unregistered', source='missing'), row(id='q5', position='missing', content='role')]
    (candidates/'draft.jsonl').write_text('\n'.join(json.dumps(item) for item in rows), encoding='utf-8')
    result = audit_directories(bank, trees, registry, candidates)
    assert {item['code'] for item in result['errors']} == {'DUPLICATE_ID', 'DUPLICATE_CONTENT', 'UNKNOWN_ROOT_THEME', 'UNREGISTERED_SOURCE', 'UNKNOWN_POSITION'}
    assert result['active_count'] == 1 and result['candidate_count'] == 0


def test_registry_rejects_unsafe_links_duplicates_and_false_reference_state(tmp_path):
    path = tmp_path/'sources.json'
    base = {'id': 'builtin', 'label': 'sample', 'origin': 'self_authored', 'review_state': 'reference_checked'}
    for url in ['javascript:alert(1)', 'http://example.org', 'https://user:secret@example.org', 'https://example.org/a b']:
        source = {**base, 'references': [{'title': 'ref', 'url': url, 'checked_on': '2026-10-26'}]}
        path.write_text(json.dumps({'format_version': 1, 'sources': [source]}), encoding='utf-8')
        assert load_registry(path) == ({}, 'invalid')
    path.write_text(json.dumps({'format_version': 1, 'sources': [{**base, 'references': []}]}), encoding='utf-8')
    assert load_registry(path)[1] == 'invalid'
    source = {**base, 'review_state': 'unreviewed', 'references': []}
    path.write_text(json.dumps({'format_version': 1, 'sources': [source, source]}), encoding='utf-8')
    assert load_registry(path)[1] == 'invalid'
    assert load_registry(tmp_path/'missing.json')[1] == 'missing'


def test_bad_json_missing_files_and_oversize_input_return_safe_codes(tmp_path):
    bank, registry, trees = files(tmp_path, [])
    (bank/'test.jsonl').write_text('{"private-secret":', encoding='utf-8')
    result = audit_directories(bank, trees, registry, tmp_path/'missing')
    assert {item['code'] for item in result['errors']} == {'INVALID_QUESTION_SCHEMA', 'NO_QUESTION_FILES'}
    assert 'private-secret' not in str(result)
    (bank/'test.jsonl').write_bytes(b' ' * (10*1024*1024+1))
    assert audit_directories(bank, trees, registry)['errors'][0]['code'] == 'FILE_UNREADABLE_OR_TOO_LARGE'


def test_empty_and_comments_only_files_cannot_pass_as_a_question_set(tmp_path):
    bank, registry, trees = files(tmp_path, [])
    result = audit_directories(bank, trees, registry)
    assert result['result'] == 'failed' and any(item['code'] == 'NO_QUESTION_RECORDS' for item in result['errors'])
    (bank/'test.jsonl').write_text('# only a comment\n\n', encoding='utf-8')
    assert audit_directories(bank, trees, registry)['result'] == 'failed'
    (bank/'test.jsonl').write_text(json.dumps(row()), encoding='utf-8')
    candidates = tmp_path/'drafts'; candidates.mkdir(); (candidates/'draft.jsonl').write_text(' \n', encoding='utf-8')
    result = audit_directories(bank, trees, registry, candidates)
    assert result['result'] == 'failed' and {'file': 'candidate', 'line': 0, 'code': 'NO_QUESTION_RECORDS'} in result['errors']
