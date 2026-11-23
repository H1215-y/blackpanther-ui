"""Device policy store. A narrow host agent applies only MAC allow-list changes."""
import ipaddress
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

MAC = re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')


class DeviceManager:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.Lock()

    def read(self, name, default):
        try:
            return json.loads((self.root / name).read_text())
        except FileNotFoundError:
            return default

    def write(self, name, data):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / (name + '.tmp-' + secrets.token_hex(4))
        temporary.write_text(json.dumps(data, ensure_ascii=False))
        os.chmod(temporary, 0o600)
        temporary.replace(self.root / name)

    def snapshot(self):
        data = self.read('devices-observed.json', {'devices': [], 'updated': 0})
        names = self.read('device-names.json', {})
        policy = self.read('device-policy.json', {'enabled': []})
        applied = self.read('device-applied.json', {})
        allowed = set(applied.get('enabled', []))
        desired = set(policy.get('enabled', []))
        devices = {d['mac']: d for d in data.get('devices', []) if MAC.fullmatch(d.get('mac', ''))}
        for mac in allowed | desired | set(names):
            devices.setdefault(mac, {'mac': mac, 'ips': [], 'seen': 0})
        router = self.read('router-devices.json', {'devices': []})
        for record in router.get('devices', []):
            mac = record.get('mac', '')
            if not MAC.fullmatch(mac):
                continue
            device = devices.setdefault(mac, {'mac': mac, 'ips': [], 'seen': 0})
            device['router_name'] = record.get('name', '')
            device['router_hostname'] = record.get('hostname', '')
            if not device.get('ips'):
                device['ips'] = record.get('ips', [])
        for mac, device in devices.items():
            device.update(name=names.get(mac) or device.get('router_name') or device.get('hostname') or '未命名设备',
                          enabled=mac in allowed, requested=mac in desired)
        return {'devices': sorted(devices.values(), key=lambda d: (not d['enabled'], d['name'], d['mac'])),
                'updated': data.get('updated', 0), 'ready': time.time() - data.get('updated', 0) < 20,
                'pending': policy.get('revision') != applied.get('revision'),
                'error': applied.get('error', '')}

    def change(self, mac, enabled=None, name=None):
        mac = str(mac).lower()
        if not MAC.fullmatch(mac) or int(mac[:2], 16) & 1 or mac == '00:00:00:00:00:00':
            raise ValueError('设备标识无效')
        with self.lock:
            snapshot = self.snapshot()
            if not snapshot['ready']:
                raise RuntimeError('设备控制服务暂未连接，请稍后重试')
            if mac not in {d['mac'] for d in snapshot['devices']}:
                raise ValueError('尚未发现这个设备，请先连接家庭网络')
            if name is not None:
                name = str(name).strip()
                if len(name) > 50:
                    raise ValueError('名称最多 50 字')
                names = self.read('device-names.json', {})
                names[mac] = name
                self.write('device-names.json', names)
            if enabled is not None:
                if not isinstance(enabled, bool):
                    raise ValueError('开关状态无效')
                if snapshot['pending']:
                    raise RuntimeError('上一次设置正在应用，请稍后重试')
                names = self.read('device-names.json', {})
                names.setdefault(mac, '')
                self.write('device-names.json', names)
                policy = self.read('device-policy.json', {'enabled': []})
                allowed = set(policy['enabled'])
                if enabled:
                    allowed.add(mac)
                else:
                    allowed.discard(mac)
                revision = secrets.token_hex(12)
                self.write('device-policy.json', {'enabled': sorted(allowed), 'revision': revision})
                for _ in range(60):
                    applied = self.read('device-applied.json', {})
                    if applied.get('revision') == revision:
                        if applied.get('error'):
                            raise RuntimeError('设备设置未生效，原规则已保留')
                        return self.snapshot()
                    time.sleep(.15)
                raise RuntimeError('设置仍在应用，请刷新查看实际状态')
            return self.snapshot()
