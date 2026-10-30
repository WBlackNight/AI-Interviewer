"""The live catalog and every new question must agree with the expanded assets."""
import json
from pathlib import Path
import pytest
from app.config import Settings
from app.factories import load_assets
from app.agent.prober import SkillTreeProber
from app.domain import ScoreResult
from tests.test_ws_recovery import api

ROOT=Path(__file__).resolve().parents[2]
ADDED=[json.loads(line)['id'] for line in (ROOT/'data/question_bank/expanded_20261030_v4.jsonl').read_text(encoding='utf-8').splitlines()]

def test_live_catalog_has_twenty_questions_in_each_direction(api):
    client,_=api
    response=client.get('/api/catalog')
    assert response.status_code==200
    roles=response.json()['positions']
    assert len(roles)==6 and all(role['total']==20 for role in roles)
    for role in roles:
        response=client.get('/api/catalog',params={'position':role['id'],'limit':20})
        assert response.status_code==200
        rows=response.json()
        assert rows['total']==20 and len(rows['items'])==20
        assert {q['difficulty'] for q in rows['items']}=={'easy','mid','hard'}

@pytest.mark.parametrize('question_id',ADDED)
def test_every_addition_has_valid_route_and_original_followup_points(question_id):
    trees,bank=load_assets(Settings(_env_file=None))
    question=bank.get(question_id)
    tree=trees[question.position]
    assert tree.question_routes[question.id]==question.theme
    follow=SkillTreeProber(tree).propose(question,ScoreResult(1,key_points_missed=tuple(p.point for p in question.answer_points)),1)
    assert follow.points and all(point in question.answer_points for point in follow.points)
    if question.position=='english_interview':assert follow.content.startswith('Please')
