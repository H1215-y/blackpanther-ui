"""Server-side provider credentials; public settings never include the password."""
import json
import os
import threading
from pathlib import Path
from cryptography.fernet import Fernet
from provider_browser import SITE, validate_site


class ProviderSettings:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.RLock()

    def _read(self):
        path = self.directory / 'provider-account.enc'
        if not path.exists():
            return {'site': SITE, 'email': '', 'password': ''}
        try:
            key = (self.directory / 'provider-account.key').read_bytes()
            return json.loads(Fernet(key).decrypt(path.read_bytes()))
        except Exception:
            raise RuntimeError('已保存的服务商账号无法读取，请重新保存或清除') from None

    def public(self):
        with self.lock:
            data = self._read()
            return {'site': data['site'], 'email': data['email'], 'saved': bool(data['password'])}

    def credentials(self, site):
        with self.lock:
            data = self._read()
            # Saving confirms which provider origin may receive these credentials.
            return (data['email'], data['password']) if site == data['site'] else ('', '')

    def save(self, site, email, password):
        site = validate_site(site)
        email, password = str(email).strip(), str(password)
        if not email or len(email) > 254 or len(password) > 512:
            raise ValueError('请填写有效的服务商账号和密码')
        with self.lock:
            old = self._read()
            if not password:
                if site != old['site'] or email != old['email'] or not old['password']:
                    raise ValueError('更换官网或账号时请重新填写密码并保存')
                password = old['password']
            self.directory.mkdir(parents=True, exist_ok=True)
            key_path = self.directory / 'provider-account.key'
            if not key_path.exists():
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(Fernet.generate_key())
            data = json.dumps({'site': site, 'email': email, 'password': password}).encode()
            encrypted = Fernet(key_path.read_bytes()).encrypt(data)
            temporary = self.directory / 'provider-account.enc.tmp'
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encrypted)
            os.replace(temporary, self.directory / 'provider-account.enc')
            return self.public()

    def clear(self):
        with self.lock:
            for name in ('provider-account.enc', 'provider-account.key'):
                (self.directory / name).unlink(missing_ok=True)
            return self.public()
