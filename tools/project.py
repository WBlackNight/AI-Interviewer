"""Project entry point. Run with backend/.venv Python; no extra dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_ui import build, outputs


def secret_values():
    """Read only for leak detection. Never print configuration values."""
    path = ROOT / 'backend/.env'
    values = []
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip().strip('"').strip("'")
            if re.search(r'KEY|TOKEN|SECRET|APP_ID|PASSWORD', key.upper()) and len(value) >= 8:
                values.append(value.encode())
    return values


def validate_members(members, secrets=()):
    checked = {}
    for name in sorted(members):
        relative = Path(name)
        path = ROOT / relative
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('Unsafe package member')
        if any(part.startswith('.') or part in ('backend', 'node_modules', '__pycache__') for part in relative.parts):
            raise ValueError('Private or generated directory in package')
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink() or not path.is_file():
            raise ValueError('Package source missing or outside workspace')
        data = path.read_bytes()
        if any(value and value in data for value in secrets):
            raise ValueError('Package credential scan failed')
        checked[name] = data
    return checked


def package():
    build(check=True)
    generated = {p.relative_to(ROOT).as_posix() for p in outputs()}
    source = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'ui').rglob('*')
              if p.is_file() and p.suffix in ('.md', '.html', '.js', '.css', '.json')}
    source.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'tools').glob('*.py'))
    source.update({'README.md', 'Makefile', 'tools/README.md', 'evals/README.md', 'assets/README.md'})
    # Include every validation script used by verify_ui, plus its gateway checks.
    source.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'evals').glob('*_check.mjs'))
    source.update({'evals/native_home_check.py', 'evals/native_home_gateway.py',
                   'evals/native_interview_test.cjs', 'evals/test_native_home_gateway.py'})
    bundles = {
        'qingzhan-native-home.zip': {'index.html', 'assets/home.css', 'assets/home.js', 'assets/account-menu.js', 'assets/README.md'},
        'qingzhan-native-workspace.zip': generated | {'assets/README.md'},
        'qingzhan-native-source.zip': source,
    }
    secrets = secret_values()
    # Validate all inputs before replacing any deliverable.
    prepared = {name: validate_members(members, secrets) for name, members in bundles.items()}
    destination = ROOT / 'docs/deliveries'
    destination.mkdir(parents=True, exist_ok=True)
    report = []
    for name, members in prepared.items():
        handle, temporary = tempfile.mkstemp(suffix='.tmp', dir=destination)
        os.close(handle)
        try:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for member, data in members.items():
                    info = zipfile.ZipInfo(member, date_time=(2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    archive.writestr(info, data)
            with zipfile.ZipFile(temporary) as archive:
                assert set(archive.namelist()) == set(members)
                assert all(archive.read(member) == data for member, data in members.items())
            target = destination / name
            os.replace(temporary, target)
            report.append({'name': name, 'members': len(members), 'byte_match': True,
                           'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {'result': 'passed', 'credential_scan': 'passed', 'packages': report}


def status():
    return {'workspace': str(ROOT), 'python': sys.version.split()[0],
            'node_available': shutil.which('node') is not None,
            'backend_environment': (ROOT / 'backend/.venv').is_dir(),
            'local_config_exists': (ROOT / 'backend/.env').is_file(),
            'next_build_exists': (ROOT / 'frontend/.next/BUILD_ID').is_file(),
            'native_pages': len(list((ROOT / 'ui/templates').glob('*.html'))),
            'note': 'Local file readiness only; not a service health or credential check.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'build', 'check', 'preview', 'package'))
    args, extra = parser.parse_known_args()
    if extra and args.command not in ('preview', 'check'):
        parser.error('Extra arguments are only accepted for preview/check')
    if args.command in ('preview', 'check'):
        script = 'evals/native_home_preview.py' if args.command == 'preview' else 'tools/verify_ui.py'
        raise SystemExit(subprocess.call([sys.executable, str(ROOT / script), *extra], cwd=ROOT))
    result = status() if args.command == 'status' else build() if args.command == 'build' else package()
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
