import json
import threading
import time
from contextlib import contextmanager

import httpx
import pytest

from aitown.ui.hosted import COOKIE_NAME, HostedUIService, VisitorServices
from aitown.ui.server import make_server
from aitown.ui.service import UIError


ORIGIN = 'https://118.31.247.169'


@contextmanager
def hosted_server(directory):
    visitors = VisitorServices(directory)
    server = make_server(None, 0, visitors=visitors, public_origin=ORIGIN)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield visitors, f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
        visitors.close()


def browser(url, cookie=''):
    client = httpx.Client(base_url=url, trust_env=False,
                         headers={'Host': '118.31.247.169', 'Origin': ORIGIN})
    if cookie:
        client.headers['Cookie'] = cookie
    response = client.get('/api/bootstrap')
    response.raise_for_status()
    # Tests contact the HTTP loopback backend; browsers receive this over HTTPS.
    cookie = response.headers['set-cookie'].split(';')[0]
    client.headers['Cookie'] = cookie
    return client, response, cookie


def job(client, path, payload):
    response = client.post(path, json=payload)
    response.raise_for_status()
    key = response.json()['job_id']
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        result = client.get('/api/job', params={'id': key}).json()
        if result['status'] != 'running':
            assert result['status'] == 'complete', result
            return result['result'], key
        time.sleep(.01)
    raise AssertionError('job did not finish')


def test_two_browsers_use_their_own_keys_histories_jobs_and_restart_without_keys(tmp_path, monkeypatch):
    calls = []
    responses = iter([{'intent':'chat','query':'你好'}, {'answer':'A 的回答'}, {'answer':'A 的回答'},
                      {'intent':'chat','query':'你好'}, {'answer':'B 的回答'}, {'answer':'B 的回答'}])
    original = httpx.Client
    def model_reply(request):
        calls.append(request.headers['Authorization'])
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(next(responses), ensure_ascii=False)}}]})
    def client_factory(**kwargs):
        if str(kwargs.get('base_url','')).startswith('https://api.deepseek.com'):
            kwargs['transport'] = httpx.MockTransport(model_reply)
        return original(**kwargs)
    monkeypatch.setattr(httpx, 'Client', client_factory)
    with hosted_server(tmp_path/'visitors') as (visitors, url):
        a, response, cookie_a = browser(url)
        b, _, cookie_b = browser(url)
        try:
            assert cookie_a != cookie_b
            assert all(flag in response.headers['set-cookie'] for flag in ('Secure','HttpOnly','SameSite=Strict','Path=/'))
            assert response.json()['hosted'] and response.json()['question_model'] == 'none'
            session_a = a.post('/api/session', json={'title':'A 私有会话'}).json()['id']
            session_b = b.post('/api/session', json={'title':'B 私有会话'}).json()['id']
            for client, key in ((a,'visitor-A-secret'), (b,'visitor-B-secret')):
                result, _ = job(client, '/api/model-settings', {'search_mode':'api', 'remember_keys':True,
                    'api':{'provider':'deepseek','base_url':'https://api.deepseek.com','model':'demo-model','api_key':key}})
                assert not result['remember_keys'] and result['api_key_storage'] == 'session'
                assert key not in json.dumps(result)
            result_a, job_a = job(a, '/api/chat', {'session':session_a,'question':'你好'})
            result_b, _ = job(b, '/api/chat', {'session':session_b,'question':'你好'})
            assert result_a['reply']['answer'] == 'A 的回答'
            assert result_b['reply']['answer'] == 'B 的回答'
            assert calls == ['Bearer visitor-A-secret']*3 + ['Bearer visitor-B-secret']*3
            assert b.get('/api/history', params={'session':session_a}).status_code == 404
            assert b.get('/api/job', params={'id':job_a}).status_code == 404
            assert [row['title'] for row in b.get('/api/bootstrap').json()['sessions']] == ['B 私有会话']
        finally:
            a.close(); b.close()
    for path in (tmp_path/'visitors').rglob('*'):
        if path.is_file():
            assert b'visitor-A-secret' not in path.read_bytes()
            assert b'visitor-B-secret' not in path.read_bytes()
    with hosted_server(tmp_path/'visitors') as (_, url):
        a, response, returned_cookie = browser(url, cookie_a)
        try:
            assert returned_cookie == cookie_a
            assert [row['title'] for row in response.json()['sessions']] == ['A 私有会话']
            settings = a.get('/api/model-settings').json()
            assert not settings['api']['has_key'] and settings['search_mode'] == 'none'
        finally:
            a.close()


def test_hosted_preserves_origin_checks_and_rejects_cookie_path_traversal(tmp_path):
    with hosted_server(tmp_path/'visitors') as (visitors, url):
        with httpx.Client(base_url=url, trust_env=False) as client:
            assert client.get('/api/health').json() == {'status':'ok'}
            assert not visitors.entries
            assert client.get('/api/bootstrap', headers={'Host':'attacker.invalid'}).status_code == 403
            assert client.post('/api/session', json={}, headers={'Host':'118.31.247.169','Origin':'https://attacker.invalid'}).status_code == 403
            assert client.post('/api/session', json={}, headers={'Host':'118.31.247.169','Origin':'http://118.31.247.169'}).status_code == 403
            assert not visitors.entries
        a, _, cookie = browser(url, COOKIE_NAME+'=../../outside')
        try:
            assert '..' not in cookie and len(visitors.entries) == 1
            assert a.get('/').status_code == 200
        finally:
            a.close()


@pytest.mark.parametrize('payload', [
    {'search_mode':'codex_chatgpt'},
    {'codex_path':'C:/private/codex.cmd'},
    {'api':{'base_url':'http://127.0.0.1:2019'}},
    {'api':{'base_url':'https://127.0.0.1'}},
    {'api':{'base_url':'https://internal.invalid'}},
    {'api':{'base_url':'https://api.deepseek.com:8443'}},
])
def test_visitor_cannot_use_server_login_or_reach_local_and_unapproved_services(tmp_path, payload):
    service = HostedUIService(tmp_path)
    try:
        with pytest.raises((UIError, ValueError)):
            service.call('_save_model_settings', payload)
        with pytest.raises(UIError):
            service.start_job('_local_model_operation', {}, 'test')
    finally:
        service.close()


def test_idle_eviction_preserves_files_but_not_secrets_and_does_not_close_leased_service(tmp_path):
    visitors = VisitorServices(tmp_path, idle_seconds=1)
    try:
        a, token, cookie = visitors.acquire('')
        a.call('_create_session', {'title':'保留记录'})
        visitors.entries[token].last_used -= 10
        b, token_b, _ = visitors.acquire('')
        assert token in visitors.entries  # HTTP request still holds a lease.
        visitors.release(token_b)
        visitors.release(token)
        visitors.entries[token].last_used -= 10
        c, token_c, _ = visitors.acquire('')
        assert token not in visitors.entries
        visitors.release(token_c)
        restored, restored_token, _ = visitors.acquire(cookie.split(';')[0])
        assert restored_token == token
        assert restored.call('_bootstrap')['sessions'][0]['title'] == '保留记录'
        visitors.release(restored_token)
    finally:
        visitors.close()


def test_expired_cookie_cannot_reopen_old_space_and_host_does_not_inherit_owner_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'server-owner-secret')
    monkeypatch.setenv('QUESTION_API_KEY', 'server-owner-course-secret')
    monkeypatch.setenv('QUESTION_SIMILAR_PROVIDER', 'codex_chatgpt')
    visitors = VisitorServices(tmp_path)
    try:
        a, token, cookie = visitors.acquire('')
        assert not a.model_preferences.api.api_key
        assert a.model_preferences.search_mode == 'none'
        a.call('_create_session', {'title':'旧空间'})
        visitors.release(token)
        with visitors.sessions:
            visitors.sessions.execute('UPDATE visitors SET expires=0 WHERE token=?', (token,))
        b, new_token, _ = visitors.acquire(cookie.split(';')[0])
        assert new_token != token and not b.call('_bootstrap')['sessions']
        visitors.release(new_token)
    finally:
        visitors.close()
