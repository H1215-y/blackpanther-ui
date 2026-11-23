"""Sanitize a one-time router device snapshot; no credentials are retained."""
import ipaddress
import os
import time

from device_manager import MAC


def friendly_name(hostname):
    models = (
        ('yeelink-light-bslamp2', '米家床头灯'),
        ('yeelink-light-lamp', '米家台灯'),
        ('chuangmi_camera_', '小米摄像头'),
        ('dmaker-fan-', '米家风扇'),
        ('xiaomi-blanket-', '米家水暖毯'),
        ('miaisoundbox-', '小爱音箱'),
    )
    for prefix, label in models:
        if hostname.lower().startswith(prefix):
            return label
    return hostname


def sanitize(data):
    if data.get('code') != 0 or not isinstance(data.get('list'), list):
        raise ValueError('路由器未返回有效设备名单')
    devices = []
    for item in data['list'][:256]:
        mac = str(item.get('mac', '')).lower()
        if not MAC.fullmatch(mac) or int(mac[:2], 16) & 1 or mac == '00:00:00:00:00:00':
            continue
        ips = []
        for entry in item.get('ip', []):
            try:
                ip = ipaddress.ip_address(entry.get('ip', ''))
                if ip in ipaddress.ip_network(os.environ.get('BP_LAN_CIDR', '192.168.1.0/24')):
                    ips.append(str(ip))
            except (ValueError, AttributeError):
                continue
        if os.environ.get('BP_GATEWAY_IP', '192.168.1.1') in ips or os.environ.get('BP_HOST_IP', '192.168.1.2') in ips:
            continue
        hostname = str(item.get('name') or item.get('oname') or '').strip()[:80]
        if hostname.lower() == mac or MAC.fullmatch(hostname.lower()):
            hostname = ''
        devices.append({'mac': mac, 'ips': list(dict.fromkeys(ips)),
                        'hostname': hostname, 'name': friendly_name(hostname)})
    return {'updated': time.time(), 'devices': devices}
