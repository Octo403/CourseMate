"""Browser-isolated study services behind a loopback HTTPS reverse proxy."""
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import urlparse

from ..config import Settings
from .demo import settings_for_ui
from .service import UIError, UIService


COOKIE_NAME = '__Host-anotherme-visitor'
COOKIE_SECONDS = 30*24*60*60
DEFAULT_API_HOSTS = frozenset({
    'api.deepseek.com', 'api.openai.com', 'dashscope.aliyuncs.com',
    'dashscope-intl.aliyuncs.com', 'api.moonshot.cn', 'api.moonshot.ai',
    'open.bigmodel.cn', 'api.siliconflow.cn', 'api.siliconflow.com',
    'ark.cn-beijing.volces.com', 'generativelanguage.googleapis.com',
})


class HostedUIService(UIService):
    """Never borrow the server owner's CLI login, model secrets or private data."""
    def __init__(self, directory, *, allowed_api_hosts=DEFAULT_API_HOSTS):
        self.allowed_api_hosts = frozenset(allowed_api_hosts)
        directory = Path(directory)
        installed = Settings(question_bank_dir=directory/'question_bank')
        settings = settings_for_ui(installed, directory/'runtime', data='study')
        settings = settings.model_copy(update={
            'mode': 'demo', 'llm_provider': 'compatible', 'question_similar_provider': 'none',
        })
        super().__init__(settings, directory/'runtime/ui.sqlite3', data='study')

    def _apply_model_preferences(self):
        self.model_preferences.remember_keys = False
        if self.model_preferences.search_mode == 'codex_chatgpt':
            self.model_preferences.search_mode = 'none'
        super()._apply_model_preferences()

    def _resolve_model_settings(self, payload):
        candidate = super()._resolve_model_settings(payload)
        if candidate.search_mode == 'codex_chatgpt' or candidate.codex_path:
            raise UIError('云端空间请使用自己的模型 API，不共享服务器账户登录。')
        if candidate.extractor == 'mineru':
            raise UIError('云端空间支持基础解析或在线解析。')
        endpoint = urlparse(candidate.api.base_url)
        # Visitors must not use model requests to reach loopback or VPC services.
        # Operators can explicitly add a trusted provider hostname at startup.
        if endpoint.scheme != 'https' or endpoint.hostname not in self.allowed_api_hosts or endpoint.port not in (None, 443):
            raise UIError('该模型地址尚未由管理员开放，请使用设置中列出的服务商地址。')
        candidate.remember_keys = False
        return candidate

    def _bootstrap(self):
        result = super()._bootstrap()
        result.update(hosted=True, data_label='云端学习 · 当前浏览器独立空间',
                      question_bank_directory='当前浏览器独立空间',
                      setup_required=not bool(self.meta.execute("SELECT 1 FROM ui_settings WHERE key='setup_complete'").fetchone()))
        return result

    def _model_settings(self):
        result = super()._model_settings()
        result.update(hosted=True, remember_keys=False, allowed_api_hosts=sorted(self.allowed_api_hosts))
        result['data_scope'] = '仅当前浏览器的学习资料与对话，使用你填写的模型 API'
        if 'documents' in result:
            result['documents']['directory'] = '当前浏览器独立空间'
        return result

    def call(self, method, *args):
        self._allow_method(method)
        return super().call(method, *args)

    def start_job(self, method, *args):
        self._allow_method(method)
        return super().start_job(method, *args)

    @staticmethod
    def _allow_method(method):
        if method.startswith('_local_model') or method in ('_save_local_model', '_mode'):
            raise UIError('云端空间不访问服务器上的本机模型。', 403)


@dataclass
class Visitor:
    service: HostedUIService
    last_used: float
    requests: int = 0


class VisitorServices:
    def __init__(self, directory, *, allowed_api_hosts=DEFAULT_API_HOSTS, idle_seconds=1800):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.allowed_api_hosts = allowed_api_hosts
        self.idle_seconds = idle_seconds
        self.entries = {}
        self.lock = threading.RLock()
        self.sessions = sqlite3.connect(self.directory/'visitors.sqlite3', check_same_thread=False)
        self.sessions.execute('CREATE TABLE IF NOT EXISTS visitors(token TEXT PRIMARY KEY, expires REAL NOT NULL)')
        self.sessions.commit()
        self.stopped = threading.Event()
        self.reaper = threading.Thread(target=self._reap, name='anotherme-visitors', daemon=True)
        self.reaper.start()

    def acquire(self, cookie_header):
        token = ''
        try:
            cookies = SimpleCookie(cookie_header)
            if COOKIE_NAME in cookies:
                token = cookies[COOKIE_NAME].value
        except CookieError:
            pass
        with self.lock:
            if self.stopped.is_set():
                raise UIError('服务正在停止，请稍后重试。', 503)
            self._expire()
            row = self.sessions.execute('SELECT expires FROM visitors WHERE token=?', (token,)).fetchone() if re.fullmatch(r'[A-Za-z0-9_-]{43}', token) else None
            if not row or row[0] <= time.time() or not (self.directory/token).is_dir():
                token = secrets.token_urlsafe(32)
                (self.directory/token).mkdir()
            with self.sessions:
                self.sessions.execute('INSERT INTO visitors VALUES(?,?) ON CONFLICT(token) DO UPDATE SET expires=excluded.expires', (token,time.time()+COOKIE_SECONDS))
            if token not in self.entries:
                service = HostedUIService(self.directory/token, allowed_api_hosts=self.allowed_api_hosts)
                self.entries[token] = Visitor(service, time.monotonic())
            entry = self.entries[token]
            entry.requests += 1
            cookie = f'{COOKIE_NAME}={token}; Path=/; Max-Age={COOKIE_SECONDS}; Secure; HttpOnly; SameSite=Strict'
            return entry.service, token, cookie

    def release(self, token):
        with self.lock:
            entry = self.entries.get(token)
            if entry is None:
                return
            entry.requests -= 1
            entry.last_used = time.monotonic()

    def _expire(self):
        now = time.monotonic()
        for token, entry in list(self.entries.items()):
            if not entry.requests and not entry.service.active and now-entry.last_used > self.idle_seconds:
                entry.service.close()
                del self.entries[token]

    def _reap(self):
        while not self.stopped.wait(30):
            with self.lock:
                self._expire()

    def close(self):
        self.stopped.set()
        self.reaper.join()
        with self.lock:
            for entry in self.entries.values():
                entry.service.close()
            self.entries.clear()
            self.sessions.close()


def serve_hosted(*, public_origin, port=8501, directory=Path('data/hosted'), allowed_api_hosts=DEFAULT_API_HOSTS):
    from .server import make_server
    visitors = VisitorServices(directory, allowed_api_hosts=allowed_api_hosts)
    try:
        server = make_server(None, port, visitors=visitors, public_origin=public_origin)
    except Exception:
        visitors.close()
        raise
    print(f'AnotherMe hosted backend: http://127.0.0.1:{server.server_port}; HTTPS entry: {public_origin}', flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        visitors.close()
