"""Small authenticated UI adapter; delegates proxy/profile ownership to XD."""
import concurrent.futures
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import device_manager
from provider_browser import ProviderBrowser, validate_site
from provider_settings import ProviderSettings

ROOT = Path(__file__).resolve().parent
XD = Path(os.environ.get('XD_DATA', '/xd'))
UPSTREAM = os.environ.get('XD_URL', 'http://127.0.0.1:8088')
CORE = os.environ.get('CORE_URL', 'http://127.0.0.1:9091')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SESSIONS = {}
LOCK = threading.Lock()
TEST_JOBS = {}
TEST_LOCK = threading.Lock()
TRANSFER = {'enabled': None, 'last': (0, 0), 'bytes': 0}
NOTICE = re.compile(r'^(剩余流量|套餐到期|请使用|防失联|电报群|官网|到期时间)')
STATE_DIR = Path(os.environ.get('BP_STATE', '/state'))
DEVICES = device_manager.DeviceManager(STATE_DIR)
PROVIDER_SETTINGS = ProviderSettings(STATE_DIR)


def import_provider(name, url):
    # Serialize imports with existing profile operations, without blocking polling.
    with LOCK:
        data = upstream('/profiles', agent=True)
        items = data if isinstance(data, list) else data.get('profiles', [])
        existing = next((p for p in items if p.get('type') == 'remote' and p.get('url') == url), None)
        if existing:
            operation = 'refresh-and-activate' if existing.get('active') else 'refresh'
            upstream('/profiles/' + urllib.parse.quote(existing['id'], safe='') + '/' + operation, 'POST', agent=True)
            return
        upstream('/profiles/import', 'POST', {'name': name, 'url': url}, agent=True)


PROVIDER = ProviderBrowser(os.environ.get('WEBDRIVER_URL', 'http://127.0.0.1:4445'), import_provider)


def credentials():
    env = {}
    for line in (XD / 'server.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k] = v.strip().strip('\"\'')
    return env


def upstream(path, method='GET', body=None, agent=False, timeout=100):
    env = credentials()
    key = env.get('CONTROL_TOKEN' if agent else 'CLASH_SECRET', '')
    if not key:
        raise RuntimeError('后端凭据未配置')
    url = (UPSTREAM + '/api/control' if agent else CORE) + path
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method,
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with OPENER.open(req, timeout=timeout) as res:
            data = res.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        # Do not return upstream bodies, which may contain subscription URLs.
        raise RuntimeError('后端操作失败（HTTP %s），原配置已保留；可在 XD 查看详情' % exc.code) from None


def transfer(enabled, reset=False):
    data = upstream('/connections', timeout=8)
    current = (max(0, int(data.get('uploadTotal', 0))), max(0, int(data.get('downloadTotal', 0))))
    if reset or TRANSFER['enabled'] != enabled:
        TRANSFER['bytes'] = 0
    elif enabled:
        TRANSFER['bytes'] += sum(now - old if now >= old else now for now, old in zip(current, TRANSFER['last']))
    TRANSFER.update(enabled=enabled, last=current)
    return {'enabled': enabled, 'bytes': TRANSFER['bytes']}


def profiles():
    data = upstream('/profiles', agent=True)
    items = data if isinstance(data, list) else data.get('profiles', [])
    allowed = ('id', 'name', 'type', 'active', 'updatedAt', 'updated', 'subscriptionInfo', 'subscriptionUserinfo', 'usage', 'updateInterval')
    return [{k: p[k] for k in allowed if k in p} for p in items if p.get('type') in ('remote', 'local')]


def run_test(job_id, names):
    def probe(name):
        with TEST_LOCK:
            TEST_JOBS[job_id]['results'][name] = {'status': 'testing'}
        try:
            path = '/proxies/' + urllib.parse.quote(name, safe='')
            result = upstream(path + '/delay?url=https%3A%2F%2Fwww.gstatic.com%2Fgenerate_204&timeout=5000&expected=204', timeout=12)
            delay = result.get('delay', 0)
            value = {'status': 'done', 'delay': delay} if delay else {'status': 'timeout'}
        except Exception:
            value = {'status': 'timeout'}
        with TEST_LOCK:
            TEST_JOBS[job_id]['results'][name] = value
            TEST_JOBS[job_id]['completed'] += 1
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(probe, names))
    finally:
        with TEST_LOCK:
            TEST_JOBS[job_id]['done'] = True


class Handler(BaseHTTPRequestHandler):
    server_version = 'BlackPanther'

    def log_message(self, *args):
        pass

    def send(self, code, data, cookie=None, content_type='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data: blob:; frame-ancestors " + os.environ.get('FRAME_ANCESTORS', "'self'"))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        cookie = dict(p.strip().split('=', 1) for p in self.headers.get('Cookie', '').split(';') if '=' in p)
        expires = SESSIONS.get(cookie.get('bp_session', ''), 0)
        return expires > time.time()

    def payload(self):
        size = int(self.headers.get('Content-Length', '0'))
        if size > 16384:
            raise ValueError('请求过大')
        return json.loads(self.rfile.read(size) or b'{}')

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/features.js': ('features.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in assets:
            filename, mime = assets[path]
            return self.send(200, (ROOT / filename).read_bytes(), content_type=mime)
        if path == '/health':
            return self.send(200, {'ok': True})
        if not self.authorized():
            return self.send(401, {'error': '请填写现有代理管理密钥'})
        try:
            if path == '/api/provider/settings':
                return self.send(200, PROVIDER_SETTINGS.public())
            if path == '/api/devices':
                return self.send(200, DEVICES.snapshot())
            if path in ('/api/provider', '/api/provider/screenshot'):
                job_id = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id', [''])[0]
                if not job_id:
                    raise ValueError('缺少导入任务标识')
                if path.endswith('screenshot'):
                    return self.send(200, PROVIDER.screenshot(job_id), content_type='image/png')
                return self.send(200, PROVIDER.status(job_id))
            if path == '/api/traffic':
                with LOCK:
                    enabled = upstream('/configs', timeout=8).get('mode') != 'direct'
                    data = transfer(enabled)
                return self.send(200, data)
            if path == '/api/test':
                job_id = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id', [''])[0]
                with TEST_LOCK:
                    job = TEST_JOBS.get(job_id)
                    if not job:
                        return self.send(404, {'error': '测速任务已结束，请重新测速'})
                    data = json.loads(json.dumps(job))
                return self.send(200, data)
            if path == '/api/state':
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                    fc = pool.submit(upstream, '/configs')
                    fp = pool.submit(upstream, '/proxies')
                    fs = pool.submit(profiles)
                    config, data, ps = fc.result(), fp.result(), fs.result()
                proxies = data.get('proxies', {})
                safe = {}
                for name, p in proxies.items():
                    safe[name] = {k: p[k] for k in ('type', 'now', 'all', 'history', 'alive', 'fixed') if k in p}
                return self.send(200, {'mode': config.get('mode'), 'proxies': safe, 'profiles': ps})
            return self.send(404, {'error': '页面不存在'})
        except Exception as exc:
            return self.send(502, {'error': str(exc) if isinstance(exc, RuntimeError) else '暂时无法读取后端，请稍后重试'})

    def do_POST(self):
        # JSON plus Origin validation prevents cross-site form actions.
        origin = self.headers.get('Origin')
        expected = 'http://' + self.headers.get('Host', '')
        if origin and origin != expected:
            return self.send(403, {'error': '不允许跨站操作'})
        if 'application/json' not in self.headers.get('Content-Type', ''):
            return self.send(415, {'error': '仅支持 JSON'})
        try:
            body = self.payload()
            path = urllib.parse.urlsplit(self.path).path
            if path == '/api/login':
                provided = str(body.get('secret', ''))
                expected_key = credentials().get('CLASH_SECRET', '')
                if not expected_key or not hmac.compare_digest(provided, expected_key):
                    return self.send(401, {'error': '密钥不正确'})
                token = secrets.token_urlsafe(32)
                SESSIONS[token] = time.time() + 30 * 86400
                return self.send(200, {'ok': True}, cookie='bp_session=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000' % token)
            if not self.authorized():
                return self.send(401, {'error': '请先连接'})
            if path == '/api/device':
                result = DEVICES.change(body.get('mac', ''), enabled=body.get('enabled'), name=body.get('name'))
                # End only this device's old core connections after a routing change.
                if 'enabled' in body:
                    ips = {ip for d in result['devices'] if d['mac'] == str(body.get('mac', '')).lower() for ip in d['ips']}
                    try:
                        for connection in upstream('/connections').get('connections', []):
                            if connection.get('metadata', {}).get('sourceIP') in ips:
                                upstream('/connections/' + urllib.parse.quote(connection['id'], safe=''), 'DELETE')
                    except Exception:
                        result['warning'] = '设置已生效，部分旧连接将自然结束'
                return self.send(200, result)
            if path == '/api/provider/settings':
                if body.get('clear'):
                    return self.send(200, PROVIDER_SETTINGS.clear())
                return self.send(200, PROVIDER_SETTINGS.save(body.get('site', ''), body.get('email', ''), body.get('password', '')))
            if path == '/api/provider/start':
                site = validate_site(body.get('site') or PROVIDER_SETTINGS.public()['site'])
                email, password = PROVIDER_SETTINGS.credentials(site)
                return self.send(200, PROVIDER.start(str(body.get('name', '飞鸟云'))[:80], email, password, site))
            if path == '/api/provider/input':
                PROVIDER.interact(str(body.get('id', '')), body)
                return self.send(200, {'ok': True})
            if path == '/api/provider/cancel':
                return self.send(200, PROVIDER.cancel(str(body.get('id', ''))))
            with LOCK:
                if path == '/api/mode':
                    transfer(bool(body.get('enabled')), reset=True)
                    upstream('/configs', 'PATCH', {'mode': 'rule' if body.get('enabled') else 'direct'})
                    upstream('/connections', 'DELETE')
                elif path == '/api/select':
                    group, node = body['group'], body['node']
                    p = upstream('/proxies/' + urllib.parse.quote(group, safe=''))
                    if node not in p.get('all', []):
                        raise ValueError('节点不在当前列表')
                    upstream('/proxies/' + urllib.parse.quote(group, safe=''), 'PUT', {'name': node})
                    upstream('/connections', 'DELETE')
                elif path == '/api/test':
                    group_name = str(body.get('group', ''))
                    group = upstream('/proxies/' + urllib.parse.quote(group_name, safe=''))
                    names = list(dict.fromkeys(n for n in group.get('all', []) if not NOTICE.match(n)))[:150]
                    if not names:
                        raise ValueError('这个策略组没有可测速的节点')
                    with TEST_LOCK:
                        for old_id in list(TEST_JOBS):
                            if TEST_JOBS[old_id]['created'] < time.time() - 3600:
                                del TEST_JOBS[old_id]
                        for existing_id, existing in TEST_JOBS.items():
                            if not existing['done']:
                                if existing['group'] == group_name:
                                    return self.send(200, {'id': existing_id})
                                raise ValueError('另一个策略组正在测速，请稍后再试')
                        job_id = secrets.token_urlsafe(16)
                        TEST_JOBS[job_id] = {'group': group_name, 'created': time.time(), 'done': False,
                            'completed': 0, 'total': len(names), 'results': {n: {'status': 'pending'} for n in names}}
                    threading.Thread(target=run_test, args=(job_id, names), daemon=True).start()
                    return self.send(200, {'id': job_id})
                elif path == '/api/import':
                    url = str(body.get('url', '')).strip()
                    if urllib.parse.urlsplit(url).scheme not in ('http', 'https'):
                        raise ValueError('请填写 http 或 https 订阅链接')
                    upstream('/profiles/import', 'POST', {'url': url, 'name': str(body.get('name', '')).strip() or '新订阅'}, agent=True)
                elif path in ('/api/activate', '/api/update'):
                    pid = str(body.get('id', ''))
                    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', pid):
                        raise ValueError('配置标识无效')
                    if path.endswith('activate'):
                        op = 'activate'
                    else:
                        profile = next((p for p in profiles() if p['id'] == pid), None)
                        if not profile or profile['type'] != 'remote':
                            raise ValueError('只能更新远程订阅')
                        op = 'refresh-and-activate' if profile.get('active') else 'refresh'
                    upstream('/profiles/' + pid + '/' + op, 'POST', agent=True)
                else:
                    return self.send(404, {'error': '操作不存在'})
            self.send(200, {'ok': True})
        except ValueError as exc:
            self.send(400, {'error': str(exc)})
        except Exception as exc:
            self.send(502, {'error': str(exc) if isinstance(exc, RuntimeError) else '操作未完成，请稍后重试'})


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8099'))), Handler).serve_forever()
