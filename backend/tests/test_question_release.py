import hashlib
import json
from pathlib import Path
from dataclasses import asdict

import pytest

from app.agent.prober import SkillTreeProber
from app.agent.scorer import HeuristicScorer
from app.agent.session import AssetVersionError, InterviewSession
from app.agent.skill_tree import SkillTree, SkillNode, load_skill_tree
from app.domain import PlanItem, ScoreResult
from app.rag.question_bank import QuestionBank
from app.services.question_audit import audit_directories
from app.services.question_release import ReleaseError, prepare_release, verify_release

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def bundle(tmp_path):
    output = tmp_path / 'release'
    prepare_release(ROOT / 'data/question_bank', ROOT / 'data/skill_tree', ROOT / 'data/question_candidates',
                    output, skill_overrides=ROOT / 'data/skill_tree_candidates')
    return output


def test_preparation_preserves_sources_and_contains_two_consistent_variants(tmp_path):
    paths = [p for directory in ('question_bank', 'skill_tree', 'question_candidates', 'retrieval')
             for p in (ROOT / 'data' / directory).iterdir() if p.is_file()]
    before = {p: p.read_bytes() for p in paths}
    output = tmp_path / 'release'
    manifest = prepare_release(ROOT / 'data/question_bank', ROOT / 'data/skill_tree', ROOT / 'data/question_candidates',
                               output, skill_overrides=ROOT / 'data/skill_tree_candidates')
    assert manifest == verify_release(output)
    assert [manifest['variants'][key]['question_count'] for key in ('baseline', 'candidate')] == [120, 126]
    assert not manifest['activated'] and not manifest['semantic_model'] and not manifest['expert_review_verified']
    assert manifest['variants']['baseline']['corpus_sha256'] != manifest['variants']['candidate']['corpus_sha256']
    assert all(p.read_bytes() == content for p, content in before.items())
    with pytest.raises(ReleaseError, match='output_already_exists'):
        prepare_release(ROOT / 'data/question_bank', ROOT / 'data/skill_tree', ROOT / 'data/question_candidates', output)
    assert verify_release(output) == manifest


@pytest.mark.parametrize('question_id', ['jv-spring-di-basic-002', 'jv-spring-cycle-002',
    'jv-redis-persist-basic-002', 'jv-redis-fsync-002', 'py-copy-cycle-002', 'py-coroutine-start-002'])
def test_six_candidate_probes_follow_explicit_route_and_original_missed_points(bundle, question_id):
    stage = bundle / 'candidate'
    bank = QuestionBank.load(stage / 'question_bank')
    question = bank.get(question_id)
    tree = load_skill_tree(stage / 'skill_tree')[question.position]
    result = ScoreResult(1, key_points_missed=tuple(p.point for p in question.answer_points))
    target = SkillTreeProber(tree).propose(question, result, 1, node_id=question.theme)
    assert target.node_id == tree.question_routes[question_id] or target.node_id.startswith(tree.question_routes[question_id] + '/')
    assert target.points and all(p in question.answer_points for p in target.points)
    if question_id == 'py-copy-cycle-002':
        assert '可变默认参数' not in target.node_id + target.content
        for anchor, leaf in [(question.answer_points[1], 'memo'), (question.answer_points[2], '资源')]:
            follow = SkillTreeProber(tree).propose(question, ScoreResult(4, key_points_missed=(anchor.point,)), 1)
            assert follow.node_id.endswith('/' + leaf) and anchor in follow.points


def test_explicit_deeper_node_is_not_overridden_by_first_question_route(bundle):
    stage = bundle / 'candidate'
    question = QuestionBank.load(stage / 'question_bank').get('py-copy-cycle-002')
    tree = load_skill_tree(stage / 'skill_tree')['python_backend']
    node = 'Python基础/对象共享与拷贝/memo'
    target = SkillTreeProber(tree).propose(question, ScoreResult(3), 2, node_id=node)
    assert target.node_id == node


def test_route_only_changes_reject_active_snapshot_and_legacy_hash_is_preserved(bundle):
    stage = bundle / 'candidate'
    bank = QuestionBank.load(stage / 'question_bank')
    tree = load_skill_tree(stage / 'skill_tree')['python_backend']
    def session(selected):
        return InterviewSession(interview_id='synthetic', position='python_backend',
            plan=[PlanItem('Python基础', 1, 'hard', 1)], bank=bank,
            scorer=HeuristicScorer(), prober=SkillTreeProber(selected))
    first = session(tree); first.start(); saved = first.snapshot()
    restored = session(tree); restored.restore(saved)
    assert restored.current_question == first.current_question
    tree.question_routes['py-copy-cycle-002'] = 'Python基础/对象共享与拷贝/memo'
    with pytest.raises(AssetVersionError):
        session(tree).restore(saved)
    legacy = load_skill_tree(ROOT / 'data/skill_tree')['python_backend']
    legacy.question_routes = {}
    expected = hashlib.sha256(json.dumps({'questions': [asdict(q) for q in bank],
        'skills': sorted(legacy.all_names())}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert session(legacy).snapshot()['asset_version'] == expected


def test_unknown_or_cross_theme_question_routes_fail_audit(bundle):
    stage = bundle / 'candidate'
    trees = load_skill_tree(stage / 'skill_tree')
    trees['python_backend'].question_routes['py-copy-cycle-002'] = '异步与并发/事件循环'
    trees['python_backend'].question_routes['nonexistent-question'] = 'Python基础'
    result = audit_directories(stage / 'question_bank', trees, stage / 'question_bank/source_registry.json')
    assert {r['code'] for r in result['errors']} == {'QUESTION_ROUTE_SCOPE_MISMATCH', 'UNKNOWN_ROUTE_QUESTION'}
    question = QuestionBank.load(stage / 'question_bank').get('py-copy-cycle-002')
    with pytest.raises(ValueError, match='scope_mismatch'):
        SkillTreeProber(trees['python_backend']).propose(question, ScoreResult(3), 1)
    with pytest.raises(ValueError, match='invalid_question_route'):
        SkillTree('python_backend', 'synthetic', [SkillNode('Python基础')], question_routes={'q': 'missing'})


@pytest.mark.parametrize('mutation', ['bytes', 'extra', 'path', 'metadata', 'updated_checksum'])
def test_verifier_rejects_corruption_extra_members_and_path_escape(bundle, mutation):
    path = bundle / 'candidate/question_bank/python_backend.jsonl'
    manifest_path = bundle / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    if mutation in ('bytes', 'updated_checksum'):
        path.write_bytes(path.read_bytes().replace('一个嵌套列表'.encode(), '一个不同列表'.encode()))
        if mutation == 'updated_checksum':
            manifest['files']['candidate/question_bank/python_backend.jsonl'] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation == 'extra':
        (bundle / 'candidate/question_bank/unlisted.jsonl').write_text('{}')
    elif mutation == 'path':
        manifest['files']['../private-secret'] = '0' * 64
    else:
        manifest['variants']['candidate']['question_count'] = 25
    manifest_path.write_bytes(json.dumps(manifest).encode())
    with pytest.raises(ValueError):
        verify_release(bundle)


def test_invalid_input_cleans_only_temporary_output_and_never_overwrites_source(tmp_path):
    drafts = tmp_path / 'drafts'; drafts.mkdir()
    active = next((ROOT / 'data/question_bank').glob('*.jsonl')).read_text(encoding='utf-8').splitlines()[0]
    (drafts / 'duplicate.jsonl').write_bytes((active + '\n').encode('utf-8'))
    output = tmp_path / 'failed-output'
    with pytest.raises(ReleaseError, match='candidate_audit_failed'):
        prepare_release(ROOT / 'data/question_bank', ROOT / 'data/skill_tree', drafts, output)
    assert not output.exists() and not list(tmp_path.glob('.question-release-*'))
    with pytest.raises(ReleaseError, match='output_overlaps_input'):
        prepare_release(ROOT / 'data/question_bank', ROOT / 'data/skill_tree', drafts, drafts / 'nested')
    assert (drafts / 'duplicate.jsonl').read_text(encoding='utf-8').strip() == active


def test_cli_report_cannot_invalidate_verified_bundle(bundle, capsys):
    import sys
    sys.path.insert(0, str(ROOT))
    from evals.prepare_question_release import main
    assert main(['--verify', str(bundle), '--json-out', str(bundle / 'report.json')]) == 1
    assert 'report_overlaps_release' in capsys.readouterr().out
    assert not (bundle / 'report.json').exists()
    assert verify_release(bundle)['variants']['candidate']['question_count'] == 126


def test_author_case_review_is_explicitly_not_independent_quality(bundle):
    import sys
    sys.path.insert(0, str(ROOT))
    from evals.review_candidate_answers import review_cases
    report = review_cases(QuestionBank.load(bundle / 'candidate/question_bank'),
                          ROOT / 'data/evals/candidate_answer_cases.jsonl')
    assert report['result'] == 'reviewed' and report['case_count'] == 18 and report['question_count'] == 6
    assert not report['independent_quality_verified'] and not report['activation_recommended']
    assert report['external_model_calls'] == 0
    assert {row['origin'] for row in report['cases']} == {'heuristic'}
    assert all('answer' not in row for row in report['cases'])


@pytest.mark.parametrize('mutation', ['version', 'unknown_question', 'duplicate', 'missing_triplet', 'false_label', 'blank'])
def test_reference_cases_reject_stale_incomplete_or_inconsistent_labels(bundle, tmp_path, mutation):
    import sys
    sys.path.insert(0, str(ROOT))
    from evals.review_candidate_answers import review_cases
    rows = [json.loads(line) for line in (ROOT / 'data/evals/candidate_answer_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    if mutation == 'version': rows[0]['question_sha256'] = '0' * 64
    elif mutation == 'unknown_question': rows[0]['question_id'] = 'missing'
    elif mutation == 'duplicate': rows.append(rows[0])
    elif mutation == 'missing_triplet': rows.pop()
    elif mutation == 'false_label': rows[0]['expected_hits'] = []
    else: rows[0]['answer'] = '  '
    path = tmp_path / 'cases.jsonl'
    path.write_bytes((''.join(json.dumps(row) + '\n' for row in rows)).encode())
    with pytest.raises(ValueError):
        review_cases(QuestionBank.load(bundle / 'candidate/question_bank'), path)
