import json
from contextlib import closing

import pytest
import httpx

from aitown.config import Settings
from aitown.errors import AgentError
from aitown.models import AnswerPayload, Decision
from aitown.online import ChatGPTModel
from aitown.question_bank.chatgpt import ChatGPTSimilarity
from aitown.retrieval.rerank import OnlineReranker, RerankResult
from aitown.ui.demo import settings_for_ui
from aitown.ui.service import UIService


def envelope_data(prompt):
    return json.JSONDecoder().raw_decode(prompt[prompt.index('{"target_schema":'):])[0]


def online_backend(monkeypatch):
    calls = []
    def structured(self, prompt, schema, paths=(), **kwargs):
        data = envelope_data(prompt)
        target = data['target_schema']['title']
        messages = data['messages']
        calls.append(target)
        question = messages[-1]['content']
        if target == 'Decision':
            payload = {'intent': 'chat' if question == '你好' else 'knowledge', 'query': question}
        elif target == 'RerankResult':
            passages = json.loads(question)['passages']
            payload = {'scores': [{'index': p['index'], 'relevance': .95 if '7人' in p['text'] else .1} for p in reversed(passages)]}
        elif target == 'AnswerPayload':
            context = next((json.loads(m['content'])['context_data'] for m in messages
                            if m['role']=='user' and m['content'].startswith('{"context_data":')), {})
            refs = [s['ref'] for s in context.get('sources', [])]
            payload = {'answer': '活动室容量9人。' if refs else '你好！可以一起讨论课程知识。', 'source_refs': refs}
        else:
            data = json.loads(question)
            refs = [s['ref'] for s in data['evidence']['sources']]
            payload = {'answer': '活动室容量7人。' if refs else data['draft']['answer'], 'source_refs': refs,
                       'corrections': ['依据原文将9人修正为7人'] if refs else []}
        return schema(payload=json.dumps(payload, ensure_ascii=False)), {'status':'ok', 'input_tokens':10, 'output_tokens':5}
    monkeypatch.setattr(ChatGPTSimilarity, 'structured', structured)
    return calls


def test_study_chat_and_faiss_rerank_review_use_main_online_model(tmp_path, monkeypatch):
    calls = online_backend(monkeypatch)
    settings = settings_for_ui(Settings(question_bank_dir=tmp_path/'bank'), tmp_path/'ui', data='study')
    with closing(UIService(settings, tmp_path/'ui/ui.sqlite3', data='study')) as service:
        session = service.call('_create_session', {})['id']
        greeting = service.call('_chat', {'session':session, 'question':'你好'})['reply']
        assert greeting['answer'].startswith('你好')
        assert [c['phase'] for c in greeting['debug']['model_calls']]==['intent','draft','review']
        service.call('_import', {'name':'library.md', 'content':'图书馆活动室容量7人。'})
        service.call('_import', {'name':'garden.txt', 'content':'公园活动室设有花卉展览，开放时间另行通知。'})
        reply = service.call('_chat', {'session':session, 'question':'活动室容量多少'})['reply']
        assert reply['answer']=='活动室容量7人。'
        assert [c['phase'] for c in reply['debug']['model_calls']]==['intent','rerank','draft','review']
        assert all(c['provider_request'] for c in reply['debug']['model_calls'])
        assert reply['debug']['trace']==['context','intent','rag','reflect']
        assert reply['debug']['reviews'][0]['changed']
        assert len(reply['sources'])==1
        assert list((tmp_path/'ui/learning-retrieval').rglob('*.faiss'))
        # Pinning a course must not turn a greeting or explanation into a search.
        service.call('_question_scope', {'session':session, 'course':'fdu-set-graph-theory'})
        greeting = service.call('_chat', {'session':session, 'question':'你好'})['reply']
        assert greeting['debug']['decision']['intent']=='chat' and not greeting['questions']
    assert calls.count('RerankResult')==1


def test_chatgpt_adapter_repairs_once_and_never_retries_transport(monkeypatch):
    responses = iter(['{bad', '{"answer":"你好"}'])
    calls = []
    def structured(self, prompt, schema, paths=(), **kwargs):
        calls.append(prompt)
        return schema(payload=next(responses)), {}
    monkeypatch.setattr(ChatGPTSimilarity, 'structured', structured)
    model = ChatGPTModel(Settings(mode='live', llm_provider='codex_chatgpt'))
    assert model.structured([{'role':'user','content':'你好'}], AnswerPayload).answer=='你好'
    assert [c.status for c in model.events]==['repair','ok'] and len(calls)==2
    def failed(*args, **kwargs):
        calls.append('failed')
        raise ValueError('private token must not escape')
    monkeypatch.setattr(ChatGPTSimilarity, 'structured', failed)
    with pytest.raises(AgentError) as exc:
        model.structured([{'role':'user','content':'你好'}], AnswerPayload)
    assert len(calls)==3 and 'private token' not in str(exc.value)


@pytest.mark.parametrize('scores', [[{'index':0,'relevance':.9},{'index':0,'relevance':.8}],
                                  [{'index':0,'relevance':.9}], [{'index':2,'relevance':.9}]])
def test_online_reranker_rejects_duplicate_missing_and_unknown_candidates(scores):
    class Model:
        def structured(self,*args):return RerankResult(scores=scores)
    with pytest.raises(ValueError):OnlineReranker(Model()).score('问题',['第一段','第二段'])


def test_study_model_settings_update_main_and_reranker_without_changing_private_settings(tmp_path):
    installed = Settings(question_bank_dir=tmp_path/'bank', retrieval_database=tmp_path/'private.sqlite3',
                         style_database=tmp_path/'private-style.sqlite3', style_profile=tmp_path/'private.json')
    settings = settings_for_ui(installed, tmp_path/'ui', data='study')
    with closing(UIService(settings, tmp_path/'ui/ui.sqlite3', data='study')) as service:
        service.call('_save_model_settings', {'search_mode':'api', 'api':{'provider':'custom',
            'base_url':'https://example.org/v1', 'model':'chosen-api', 'api_key':'synthetic-secret'}, 'remember_keys':False})
        assert service.agent.model.settings.model=='chosen-api'
        assert service.agent.retriever.reranker.model is service.agent.model
        assert service.agent.settings.llm_provider=='compatible'
        assert 'synthetic-secret' not in json.dumps(service.call('_bootstrap'))
        service.call('_save_model_settings', {'search_mode':'codex_chatgpt','codex_model':'chosen-chatgpt'})
        assert service.agent.model.settings.model=='chosen-chatgpt'
        assert service.agent.retriever.reranker.model is service.agent.model
    assert not installed.retrieval_database.exists() and not installed.style_database.exists()


def test_compatible_api_runs_main_intent_draft_review_and_preserves_history(tmp_path, monkeypatch):
    requests = []
    responses = iter([{'intent':'chat','query':'你好'}, {'answer':'你好！'}, {'answer':'你好！'}])
    original = httpx.Client
    def handle(request):
        assert request.url.host=='model.example.org' and request.url.path=='/v1/chat/completions'
        assert request.headers['Authorization']=='Bearer synthetic-key'
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(next(responses))}}]})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    settings = settings_for_ui(Settings(question_bank_dir=tmp_path/'bank'),tmp_path/'ui',data='study')
    with closing(UIService(settings,tmp_path/'ui/ui.sqlite3',data='study')) as service:
        session = service.call('_create_session',{})['id']
        service.call('_save_model_settings',{'search_mode':'api','api':{'provider':'custom',
            'base_url':'https://model.example.org/v1','model':'selected-model','api_key':'synthetic-key'},'remember_keys':False})
        reply = service.call('_chat',{'session':session,'question':'你好'})['reply']
        assert reply['answer']=='你好！' and reply['output_kind']=='generated'
        assert [c['phase'] for c in reply['debug']['model_calls']]==['intent','draft','review']
        service.call('_save_model_settings',{'search_mode':'codex_chatgpt'})
        assert len(service.call('_history',session)['turns'])==1
    assert len(requests)==3 and all(r['model']=='selected-model' for r in requests)
