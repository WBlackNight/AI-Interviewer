import asyncio
import pytest
from app.config import Settings
from app.factories import load_assets
from app.agent.prober import SkillTreeProber
from app.domain import ScoreResult
from app.voice import realtime
from app.voice.doubao import DoubaoVoiceOptions
from tests.test_realtime_voice import Session
from tests.test_ws_recovery import api, connect

@pytest.mark.parametrize('position',['marketing','operations','education','english_interview'])
def test_domain_question_answer_and_report(api,position,monkeypatch):
    from app.api import realtime as realtime_route
    client,factory=api
    monkeypatch.setattr(realtime_route,'SessionLocal',factory)
    created=client.post('/api/interview',json={'position':position,'difficulty':'easy'}).json()
    with connect(client,created) as (_,snapshot):
        assert snapshot['current_question']['content']
    if position == 'english_interview':
        context=client.get('/api/interview/'+created['interview_id']+'/realtime-context',headers={'X-Interview-Token':created['access_token']})
        assert context.status_code == 200 and context.json()['question']['language'] == 'en'
    trees,bank=load_assets(Settings(_env_file=None))
    questions=[q for q in bank if q.position==position]
    assert len(questions)>=20
    target=SkillTreeProber(trees[position]).propose(questions[0],ScoreResult(1,key_points_missed=tuple(p.point for p in questions[0].answer_points)),1)
    assert target.points and all(p in questions[0].answer_points for p in target.points)
    if position=='english_interview':assert target.content.startswith('Please')

def test_english_voice_instruction(monkeypatch):
    monkeypatch.setattr(realtime,'DuplexSession',Session)
    async def run():
        dialogue=realtime.RealtimeDialogue(DoubaoVoiceOptions('test'))
        # This double checks production instructions without assuming Chinese wording.
        async def start(**kwargs):dialogue.session.instructions=kwargs['instructions']
        dialogue.session.start=start
        await dialogue.start({'content':'Introduce yourself.','language':'en'})
        assert 'Respond in English' in dialogue.session.instructions
        await dialogue.close()
    asyncio.run(run())
