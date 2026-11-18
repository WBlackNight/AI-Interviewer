"""Assistant transport: charge uncertain calls, reject incomplete streams."""
from types import SimpleNamespace as NS

import pytest

from app.llm.budget import TokenBudget, use_budget
from app.llm.client import OpenAICompatibleLLM
from app.llm.errors import BudgetExceeded, LLMError


def model(create):
    client = OpenAICompatibleLLM(api_key='synthetic', base_url='https://example.invalid/v1', model='test')
    client._client.close()
    client._client = NS(chat=NS(completions=NS(create=create)))
    return client


@pytest.mark.parametrize('streaming', [False, True])
def test_failed_network_calls_have_unknown_usage_and_stop_budget(streaming):
    def failure(**kwargs):
        raise TimeoutError('synthetic')
    client = model(failure)
    with use_budget(TokenBudget(limit_tokens=100)):
        with pytest.raises(BudgetExceeded):
            list(client.stream_chat([])) if streaming else client.tool_call([], [])
    assert client.usage_diagnostics()['network_calls'] == 1
    assert client.usage_diagnostics()['unknown_usage_calls'] == 1


@pytest.mark.parametrize('finish', ['stop', 'length', None])
def test_stream_requires_normal_finish_and_closes_transport(finish):
    class Stream:
        closed = False
        def __iter__(self):
            yield NS(usage=None, choices=[NS(delta=NS(content='内容'), finish_reason=finish)])
            yield NS(usage=NS(prompt_tokens=8, completion_tokens=3), choices=[])
        def close(self):
            self.closed = True
    stream = Stream()
    client = model(lambda **kwargs: stream)
    budget = TokenBudget(limit_tokens=100)
    with use_budget(budget):
        if finish == 'stop':
            assert list(client.stream_chat([])) == ['内容']
        else:
            with pytest.raises(LLMError):
                list(client.stream_chat([]))
    assert stream.closed and budget.used_tokens == 11
