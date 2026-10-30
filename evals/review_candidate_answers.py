"""离线对照作者参考示例，暴露规则评分误判；不作为独立人工质量验收。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.agent.scorer import HeuristicScorer
from app.rag.question_bank import QuestionBank
from app.rag.vector_index import question_version
from app.services.question_release import verify_release


class ReferenceCase(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    case_id: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,80}$')
    question_id: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    question_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: Literal['complete', 'partial', 'wrong']
    answer: str = Field(min_length=1, max_length=8000)
    expected_hits: list[str] = Field(max_length=12)


def review_cases(bank: QuestionBank, path: Path) -> dict:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('case_file_too_large')
    cases = [ReferenceCase.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if (not cases or len(cases) > 1000 or len({case.case_id for case in cases}) != len(cases)
            or any(not case.answer.strip() for case in cases)):
        raise ValueError('invalid_case_set')
    kinds, results = {}, []
    for case in cases:
        question = bank.get(case.question_id)
        if question is None or question_version(question) != case.question_sha256:
            raise ValueError('case_question_version_mismatch')
        anchors = {point.point for point in question.answer_points}
        expected = set(case.expected_hits)
        if (len(expected) != len(case.expected_hits) or not expected <= anchors
                or (case.kind == 'complete' and expected != anchors)
                or (case.kind == 'partial' and not (expected and expected < anchors))
                or (case.kind == 'wrong' and expected)):
            raise ValueError('invalid_case_reference')
        kinds.setdefault(case.question_id, []).append(case.kind)
        scored = HeuristicScorer().score(question, case.answer)
        actual = set(scored.key_points_hit)
        results.append({'case_id': case.case_id, 'question_id': case.question_id, 'kind': case.kind,
                        'score': scored.score, 'origin': scored.origin.source,
                        'scorer_version': scored.origin.scorer_version,
                        'extra_hit_count': len(actual - expected), 'missing_hit_count': len(expected - actual),
                        'anchor_set_matches_author_reference': actual == expected})
    if any(Counter(values) != Counter(['complete', 'partial', 'wrong']) for values in kinds.values()):
        raise ValueError('incomplete_case_triplet')
    return {'result': 'reviewed', 'question_count': len(kinds), 'case_count': len(cases),
            'reference_origin': 'project_author_examples', 'independent_quality_verified': False,
            'activation_recommended': False, 'external_model_calls': 0,
            'exact_anchor_set_count': sum(row['anchor_set_matches_author_reference'] for row in results),
            'extra_hit_cases': sum(row['extra_hit_count'] > 0 for row in results),
            'missing_hit_cases': sum(row['missing_hit_count'] > 0 for row in results), 'cases': results,
            'note': '仅对照作者示例观察规则基线；关键词关联不证明语义，不能替代盲标或推荐激活。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--cases', type=Path, default=ROOT / 'data/evals/candidate_answer_cases.jsonl')
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args(argv)
    if args.json_out and (args.json_out.resolve().is_relative_to(args.release.resolve())
                          or args.json_out.resolve() == args.cases.resolve()):
        print(json.dumps({'result': 'failed', 'error_code': 'report_overlaps_input'}))
        return 1
    try:
        verify_release(args.release)
        report = review_cases(QuestionBank.load(args.release / 'candidate/question_bank'), args.cases)
    except Exception:
        report = {'result': 'failed', 'error_code': 'invalid_release_or_reference_cases', 'external_model_calls': 0}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['result'] == 'reviewed' else 1


if __name__ == '__main__':
    sys.exit(main())
