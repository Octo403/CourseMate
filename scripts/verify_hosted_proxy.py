"""Exercise a real local Caddy HTTPS proxy, auth and two browser cookie jars."""
import argparse
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time

import httpx

from aitown.ui.hosted import COOKIE_NAME, VisitorServices
from aitown.ui.server import make_server


def unused_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--caddy', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    checks = []
    password = 'synthetic-only-test-password'
    caddy = args.caddy.resolve()
    with tempfile.TemporaryDirectory(prefix='anotherme-proxy-') as temporary:
        directory = Path(temporary)
        tls_port, redirect_port, admin_port = unused_port(), unused_port(), unused_port()
        origin = f'https://127.0.0.1:{tls_port}'
        visitors = VisitorServices(directory/'visitors')
        backend = make_server(None, 0, visitors=visitors, public_origin=origin)
        worker = threading.Thread(target=backend.serve_forever, daemon=True)
        worker.start()
        hashed = subprocess.run([str(caddy),'hash-password','--plaintext',password], check=True, capture_output=True, text=True).stdout.strip()
        storage = (directory/'caddy-data').as_posix()
        config = directory/'Caddyfile'
        config.write_text(f'''{{
    skip_install_trust
    http_port {redirect_port}
    admin localhost:{admin_port}
    default_sni 127.0.0.1
    storage file_system {{
        root "{storage}"
    }}
}}
{origin} {{
    tls internal
    basic_auth {{
        class {hashed}
    }}
    reverse_proxy 127.0.0.1:{backend.server_port}
}}
''', encoding='utf-8')
        process = None
        try:
            with (directory/'caddy.log').open('wb') as log:
                process = subprocess.Popen([str(caddy),'run','--config',str(config),'--adapter','caddyfile'],
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                root = directory/'caddy-data/pki/authorities/local/root.crt'
                deadline = time.monotonic()+30
                while not root.exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Caddy exited: '+(directory/'caddy.log').read_text(errors='replace'))
                    time.sleep(.1)
                context = ssl.create_default_context(cafile=str(root))
                with httpx.Client(base_url=origin, verify=context, trust_env=False) as anonymous:
                    for _ in range(50):
                        try:
                            response = anonymous.get('/api/health')
                            break
                        except httpx.ConnectError:
                            time.sleep(.1)
                    else:
                        raise RuntimeError('HTTPS listener did not start')
                    assert response.status_code == 401
                    checks.extend(['real TLS handshake with verified test CA','anonymous HTTPS request rejected'])
                with httpx.Client(base_url=origin, verify=context, trust_env=False, auth=('class',password)) as a, \
                     httpx.Client(base_url=origin, verify=context, trust_env=False, auth=('class',password)) as b:
                    assert a.get('/api/health').json() == {'status':'ok'}
                    assert a.get('/api/bootstrap').json()['hosted']
                    assert b.get('/api/bootstrap').json()['hosted']
                    assert a.cookies.get(COOKIE_NAME) != b.cookies.get(COOKIE_NAME)
                    checks.append('independent Secure cookie jars over real HTTPS')
                    session_a = a.post('/api/session', json={'title':'A private session'}, headers={'Origin':origin}).json()['id']
                    b.post('/api/session', json={'title':'B private session'}, headers={'Origin':origin}).raise_for_status()
                    assert b.get('/api/history',params={'session':session_a}).status_code == 404
                    assert a.post('/api/session',json={},headers={'Origin':'https://attacker.invalid'}).status_code == 403
                    checks.extend(['cross-browser session access rejected','cross-origin POST rejected through proxy'])
                    for client, key in ((a,'synthetic-A-key'),(b,'synthetic-B-key')):
                        response = client.post('/api/model-settings',json={'search_mode':'api','remember_keys':True,
                            'api':{'provider':'deepseek','base_url':'https://api.deepseek.com','model':'synthetic-model','api_key':key}},headers={'Origin':origin})
                        response.raise_for_status()
                        job_id = response.json()['job_id']
                        deadline = time.monotonic()+10
                        while time.monotonic() < deadline:
                            result = client.get('/api/job',params={'id':job_id}).json()
                            if result['status'] != 'running':
                                assert result['status'] == 'complete', result
                                assert result['result']['api_key_storage'] == 'session'
                                assert key not in json.dumps(result)
                                break
                            time.sleep(.01)
                        else:
                            raise RuntimeError('Model settings job did not finish')
                    checks.append('each browser can submit its own in-memory API settings')
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            backend.shutdown()
            backend.server_close()
            worker.join()
            visitors.close()
    result = {'status':'passed','checks':checks,'scope':'local Windows, real Caddy TLS with test CA; no ECS, public ACME issuance or real provider calls'}
    if args.report:
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
