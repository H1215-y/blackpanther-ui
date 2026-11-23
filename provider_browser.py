"""A real, resumable provider browser. CAPTCHA solving is always manual."""
import base64
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Entry verified against the provider's GitHub publication on 2026-11-20.
SITE = 'https://basbax.934676.xyz'
ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'


def validate_site(value):
    parsed = urllib.parse.urlsplit(str(value).strip())
    host = (parsed.hostname or '').lower()
    trusted = host in ('feiniaoyun.xyz', 'feiniaoyun.top') or any(host.endswith('.' + root) for root in ('934676.xyz', '459236.xyz'))
    if parsed.scheme != 'https' or not trusted or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('请使用 GitHub 发布页列出的飞鸟云 HTTPS 官网；新域名范围需要更新验证')
    return 'https://' + host


def subscription_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme in ('clash', 'clashmeta', 'clashmi'):
        query = urllib.parse.parse_qs(parsed.query)
        value = (query.get('url') or query.get('config') or [''])[0]
        parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        return None
    if not parsed.path or parsed.path == '/':
        return None
    # A dashboard or a login URL is not a subscription.
    if parsed.fragment or parsed.path.rstrip('/').endswith(('/login', '/dashboard')):
        return None
    return value


INSPECT = r"""
const visible=e=>!!(e&&e.getClientRects().length);
const body=document.body?.innerText||'';
const title=document.title;
const challenge=/Just a moment|请稍候|Checking your browser|正在进行安全验证|Verify you are human|验证您是真人/i.test(title+' '+body.slice(0,1500));
const invalid=/您的连接不是私密连接|Your connection is not private|NET::ERR_CERT/i.test(body);
const password=[...document.querySelectorAll('input[type=password]')].find(visible);
const email=[...document.querySelectorAll('input[type=email],input[name=email],input[autocomplete=username],input[type=text]')].find(visible);
if(!window.__bpSubscription){
 window.__bpSubscription={url:'',clicked:{}};
 const capture=value=>{if(typeof value==='string'&&/^(https?:\/\/|clash(?:meta|mi)?:)/i.test(value.trim()))window.__bpSubscription.url=value.trim()};
 if(navigator.clipboard?.writeText){const write=navigator.clipboard.writeText.bind(navigator.clipboard);try{navigator.clipboard.writeText=value=>{capture(value);return write(value).catch(()=>{})}}catch{}}
 document.addEventListener('copy',event=>capture(event.clipboardData?.getData('text/plain')),true);
 const exec=document.execCommand.bind(document);document.execCommand=function(command,...args){if(command==='copy'){const e=document.activeElement;capture(e?.value?e.value.slice(e.selectionStart||0,e.selectionEnd||e.value.length):String(window.getSelection()))}return exec(command,...args)};
}
const candidates=[window.__bpSubscription.url,...[...document.querySelectorAll('a[href], [data-clipboard-text]')].map(e=>e.getAttribute('data-clipboard-text')||e.getAttribute('href'))].filter(Boolean);
return {url:location.href,title,challenge,invalid,login:!!password,email:!!email,candidates};
"""

CLICK_SUBSCRIPTION = r"""
const visible=e=>!!e.getClientRects().length;
const elements=[...document.querySelectorAll('button,a,[role=button],.dropdown-item,.list-group-item,div,span')].filter(visible);
for(const label of ['复制订阅地址','复制订阅链接','一键订阅']){
 const e=elements.find(e=>e.textContent.trim()===label);
 if(e&&!window.__bpSubscription.clicked[label]){window.__bpSubscription.clicked[label]=true;e.click();return label}
}
return '';
"""


class WebDriver:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.session = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, data=None):
        request = urllib.request.Request(self.url + path, method=method,
            data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=40) as response:
                result = json.loads(response.read())['value']
        except Exception:
            raise RuntimeError('服务商登录窗口暂时不可用，请稍后重试') from None
        if isinstance(result, dict) and result.get('error'):
            raise RuntimeError('登录窗口操作未完成，请重试')
        return result

    def start(self, site=SITE):
        result = self.request('POST', '/session', {'capabilities': {'alwaysMatch': {
            'browserName': 'chrome', 'pageLoadStrategy': 'eager',
            'goog:chromeOptions': {'args': ['--window-size=1000,900', '--lang=zh-CN', '--no-sandbox']}}}})
        self.session = result['sessionId']
        self.call('POST', '/timeouts', {'pageLoad': 30000, 'script': 10000, 'implicit': 0})
        self.call('POST', '/window/rect', {'width': 1000, 'height': 900})
        self.call('POST', '/url', {'url': site + '/#/dashboard'})

    def call(self, method, path, data=None):
        return self.request(method, '/session/' + self.session + path, data)

    def script(self, script, *args):
        return self.call('POST', '/execute/sync', {'script': script, 'args': list(args)})

    def fill(self, selector, value):
        found = self.call('POST', '/elements', {'using': 'css selector', 'value': selector})
        for item in found:
            eid = item[ELEMENT]
            # A genuine WebDriver typing event updates Vue/React forms too.
            if self.call('GET', '/element/' + eid + '/displayed'):
                self.call('POST', '/element/' + eid + '/clear', {})
                self.call('POST', '/element/' + eid + '/value', {'text': value})
                return eid
        raise RuntimeError('没有找到登录输入框，请在登录窗口内操作')


class ProviderBrowser:
    def __init__(self, webdriver_url, importer):
        self.site = SITE
        self.webdriver_url = webdriver_url
        self.importer = importer
        self.lock = threading.RLock()
        self.wd_lock = threading.RLock()
        self.job = None
        self.wd = None
        self.cancel_event = threading.Event()
        self.worker = None
        self.pending_credentials = None

    def status(self, job_id=None):
        with self.lock:
            if not self.job or job_id and job_id != self.job['id']:
                raise ValueError('导入任务不存在')
            return {key: self.job[key] for key in ('id', 'status', 'message', 'created')}

    def update(self, status, message):
        with self.lock:
            if self.cancel_event.is_set() and status != 'cancelled':
                return
            self.job.update(status=status, message=message)

    def start(self, name, email='', password='', site=SITE):
        site = validate_site(site)
        with self.lock:
            if self.worker and self.worker.is_alive() and self.job['status'] in ('done', 'error', 'cancelled'):
                raise RuntimeError('上次任务正在结束，请稍后重试')
            if self.job and self.job['status'] not in ('done', 'error', 'cancelled'):
                return self.status()
            if site != self.site and self.wd and self.wd.session:
                with self.wd_lock:
                    self.wd.call('DELETE', '')
                    self.wd = None
            self.site = site
            self.job = {'id': secrets.token_urlsafe(20), 'status': 'starting',
                        'message': '正在打开飞鸟云…', 'created': time.time()}
            self.cancel_event.clear()
            self.worker = threading.Thread(target=self.run, args=(name, email, password), daemon=True)
            self.worker.start()
            return self.status()

    def cancel(self, job_id):
        with self.lock:
            status = self.status(job_id)
            if status['status'] == 'importing':
                raise RuntimeError('订阅正在加入列表，请等待完成')
            self.cancel_event.set()
            self.update('cancelled', '已取消导入')
            return self.status()

    def run(self, name, email, password):
        try:
            with self.wd_lock:
                if self.wd and self.wd.session:
                    try:
                        self.wd.request('GET', '/session/' + self.wd.session + '/url')
                    except RuntimeError:
                        self.wd = None
                if not self.wd:
                    self.wd = WebDriver(self.webdriver_url)
                    self.wd.start(self.site)
            submitted = False
            for _ in range(900):
                if self.cancel_event.is_set():
                    return
                with self.lock:
                    if self.pending_credentials:
                        email, password = self.pending_credentials
                        self.pending_credentials = None
                        submitted = False
                with self.wd_lock:
                    view = self.wd.script(INSPECT)
                # Never type credentials after an unexpected navigation.
                target = urllib.parse.urlsplit(view['url'])
                if target.scheme != 'https' or target.netloc != urllib.parse.urlsplit(self.site).netloc:
                    self.update('manual', '页面跳转到了其他网站，请检查登录窗口')
                elif view['invalid']:
                    raise RuntimeError('服务商网站证书异常，请稍后再试')
                elif view['challenge']:
                    self.update('verification', '请在下方登录窗口完成人机验证，完成后自动继续')
                elif view['login']:
                    if email and password and not submitted:
                        self.update('working', '正在登录飞鸟云…')
                        with self.wd_lock:
                            self.wd.fill('input[type=email],input[name=email],input[autocomplete=username],input[type=text]', email)
                            eid = self.wd.fill('input[type=password]', password)
                            self.wd.call('POST', '/element/' + eid + '/value', {'text': '\ue007'})
                        submitted = True
                        password = email = ''
                    else:
                        self.update('manual', '请在下方窗口登录，登录后自动获取订阅')
                else:
                    self.update('working', '正在获取订阅地址…')
                    candidate = next((subscription_url(v) for v in view['candidates']
                                      if subscription_url(v) and (
                                          'subscribe' in v.lower() or 'token=' in v.lower() or v.startswith('clash'))), None)
                    if candidate:
                        # An ordinary website link must never be mistaken for a subscription.
                        parsed = urllib.parse.urlsplit(candidate)
                        if 'token=' in parsed.query or 'subscribe' in parsed.path.lower() or 'sub' in parsed.path.lower():
                            with self.lock:
                                if self.cancel_event.is_set():
                                    return
                                self.update('importing', '正在加入订阅列表…')
                            self.importer(name or '飞鸟云', candidate)
                            self.update('done', '已加入订阅列表，点卡片即可使用')
                            return
                    with self.wd_lock:
                        clicked = self.wd.script(CLICK_SUBSCRIPTION)
                    if not clicked:
                        self.update('manual', '请在下方窗口点“一键订阅”，获取后会自动加入列表')
                time.sleep(1)
            raise RuntimeError('登录等待已超时，请重新开始')
        except Exception as exc:
            if not self.cancel_event.is_set():
                self.update('error', str(exc) if isinstance(exc, RuntimeError) else '服务商导入失败，请重新尝试')
        finally:
            password = email = ''
            with self.lock:
                self.pending_credentials = None
            with self.wd_lock:
                if self.status()['status'] != 'done' and self.wd and self.wd.session:
                    try:
                        self.wd.call('DELETE', '')
                    except Exception:
                        pass
                    self.wd = None

    def screenshot(self, job_id):
        if self.status(job_id)['status'] not in ('manual', 'verification'):
            raise ValueError('当前不需要手动操作登录窗口')
        with self.wd_lock:
            if not self.wd or not self.wd.session:
                raise RuntimeError('正在准备登录窗口')
            return base64.b64decode(self.wd.call('GET', '/screenshot'))

    def interact(self, job_id, body):
        status = self.status(job_id)
        if status['status'] not in ('manual', 'verification'):
            raise ValueError('登录窗口尚未准备好')
        if body.get('kind') == 'login':
            email, password = str(body.get('email', '')).strip(), str(body.get('password', ''))
            if not email or not password or len(email) > 254 or len(password) > 512:
                raise ValueError('请填写账号和密码')
            with self.lock:
                self.pending_credentials = (email, password)
            return
        with self.wd_lock:
            if body.get('kind') in ('click', 'drag'):
                x, y = int(body['x']), int(body['y'])
                if not 0 <= x <= 2000 or not 0 <= y <= 2000:
                    raise ValueError('点击位置无效')
                actions = [
                    {'type': 'pointerMove', 'origin': 'viewport', 'x': x, 'y': y},
                    {'type': 'pointerDown', 'button': 0}]
                if body['kind'] == 'drag':
                    to_x, to_y = int(body['toX']), int(body['toY'])
                    if not 0 <= to_x <= 2000 or not 0 <= to_y <= 2000:
                        raise ValueError('拖动位置无效')
                    actions.append({'type': 'pointerMove', 'origin': 'viewport', 'x': to_x, 'y': to_y, 'duration': 700})
                actions.append({'type': 'pointerUp', 'button': 0})
                self.wd.call('POST', '/actions', {'actions': [{'type': 'pointer', 'id': 'user',
                    'parameters': {'pointerType': 'mouse'}, 'actions': actions}]})
            elif body.get('kind') == 'text':
                value = str(body.get('text', ''))
                if len(value) > 512:
                    raise ValueError('输入过长')
                active = self.wd.call('GET', '/element/active')[ELEMENT]
                self.wd.call('POST', '/element/' + active + '/value', {'text': value})
            elif body.get('kind') == 'enter':
                active = self.wd.call('GET', '/element/active')[ELEMENT]
                self.wd.call('POST', '/element/' + active + '/value', {'text': '\ue007'})
            elif body.get('kind') == 'scroll':
                amount = max(-600, min(600, int(body.get('amount', 400))))
                self.wd.call('POST', '/actions', {'actions': [{'type': 'wheel', 'id': 'user-scroll', 'actions': [
                    {'type': 'scroll', 'x': 500, 'y': 400, 'deltaX': 0, 'deltaY': amount, 'duration': 200}]}]})
            else:
                raise ValueError('操作无效')

