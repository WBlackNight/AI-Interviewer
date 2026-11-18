import json
from pathlib import Path

import pytest

from app.services.assistant_grounding import grounding_issues
from tests.test_assistant import FakeModel, create, frames, send, users, offline_assistant, api

CASES = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / 'data/evals/assistant_grounding.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case_id'])
def test_authored_index_regressions(case):
    sources = [{'id': 'G1', 'title': '联合索引：列顺序、查询条件与优化器'}]
    assert bool(grounding_issues(sources, case['answer'])) == case['reject']
    assert not grounding_issues([], case['answer'])


def test_failed_grounding_replaces_visible_and_persisted_answer(users, monkeypatch):
    from app.services import assistant
    from tests.test_assistant import auth
    class WrongModel(FakeModel):
        def stream_chat(self, messages):
            yield '维护一个联合索引的成本与维护多个单独索引的总成本相当。'
    monkeypatch.setattr(assistant, 'build_llm', lambda _: WrongModel())
    client, _, account, _ = users
    row = create(client, account)
    events = frames(send(client, account, row, text='请解释MySQL联合索引'))
    revision = next(item for item in events if item['type'] == 'revision')
    assert '不能直接声称' in revision['text']
    assert next(item for item in events if item['type'] == 'mode')['value'] == 'fallback'
    assert events[-1]['type'] == 'done'
    saved = client.get('/api/assistant/conversations/' + row['id'], headers=auth(account)).json()
    assert saved['messages'][-1]['content'] == revision['text']
