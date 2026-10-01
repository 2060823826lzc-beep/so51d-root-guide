"""Shared paths and immutable artifact checks. No device access on import."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = (Path(sys._MEIPASS) / 'resources' if getattr(sys, 'frozen', False)
        else Path(__file__).resolve().parents[1])
MANIFEST = json.loads((ROOT / 'tools-manifest.json').read_text(encoding='utf-8'))
KERNEL = MANIFEST['kernel']
DOWNLOADS = ROOT / 'downloads'
PROFILE = ROOT / MANIFEST.get('profile', 'profiles/so51d-12915929.glk')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(path, expected):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f'缺少文件：{path.name}。先运行 scripts/fetch_tools.py。')
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f'SHA-256 不匹配：{path.name}\n预期 {expected}\n实际 {actual}')


def verify_payloads():
    from registry import load_catalog
    for profile in load_catalog(ROOT)['profiles']:
        verify(ROOT / profile['file'], profile['sha256'])
    for package in MANIFEST['packages']:
        verify(DOWNLOADS / package['name'], package['sha256'])
        item = package['extract']
        verify(DOWNLOADS / item['name'], item['sha256'])
