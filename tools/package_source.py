"""Package the current full development source without Git or local runtime data."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from build_ui import build
from project import ROOT, secret_values

NAME = 'AI-Interviewer-2026-11-18-competition-source.zip'
DIRECTORIES = ('.github', 'ui', 'assets', 'backend/app', 'backend/tests',
               'frontend', 'data', 'docs', 'evals', 'tools', 'deploy')
EXCLUDED = {'node_modules', '__pycache__', '.next', '.test-build', '.pytest_cache',
            'out', 'logs', 'deliveries', 'references', 'releases'}
EXTENSIONS = {'.py', '.md', '.html', '.css', '.js', '.mjs', '.cjs', '.ts', '.tsx',
              '.json', '.jsonl', '.yaml', '.yml', '.txt', '.svg', '.webp', '.conf', '.sh'}


def collect():
    members = {'.gitattributes', '.gitignore', '.dockerignore', 'README.md', 'START_HERE.md', 'Makefile',
               'docker-compose.yml', 'compose.cloud.yml', 'backend/requirements.txt', 'backend/pip.conf',
               'backend/.env.example', 'frontend/.env.example'}
    members.update(p.name for p in ROOT.glob('*.html'))
    for directory in DIRECTORIES:
        for parent, dirs, files in os.walk(ROOT / directory, followlinks=False):
            base = Path(parent)
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith('.')
                             and (base / d) != ROOT / 'data/retrieval'
                             and not (base / d).is_symlink())
            for filename in files:
                path = base / filename
                special = filename in {'Dockerfile', 'Caddyfile'} or filename.endswith('.env.example')
                if filename.startswith('.') or (not special and path.suffix.lower() not in EXTENSIONS):
                    continue
                if filename.endswith('.tsbuildinfo') or path.is_symlink():
                    continue
                members.add(path.relative_to(ROOT).as_posix())
    return sorted(members)


def package():
    build(check=True)
    secrets = secret_values()
    contents = {}
    for member in collect():
        path = ROOT / member
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Missing source or unsafe package path')
        data = path.read_bytes()
        if any(secret in data for secret in secrets):
            raise ValueError('Package credential scan failed')
        contents[member] = data
    contents['SOURCE_MANIFEST.json'] = (json.dumps({
        'format': 1,
        'description': 'Current working files, including uncommitted source changes; no Git history.',
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in contents.items()},
    }, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    destination = ROOT / 'docs/deliveries'
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / NAME
    handle, temporary = tempfile.mkstemp(dir=destination, suffix='.tmp')
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for member, data in sorted(contents.items()):
                info = zipfile.ZipInfo('AI-Interviewer/' + member, date_time=(2026, 11, 18, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None or len(archive.namelist()) != len(contents):
                raise ValueError('Archive integrity failed')
            for member, data in contents.items():
                if archive.read('AI-Interviewer/' + member) != data:
                    raise ValueError('Archive source mismatch')
        os.replace(temporary, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n', encoding='utf-8')
        return {'file': str(target), 'members': len(contents), 'bytes': target.stat().st_size,
                'sha256': digest, 'integrity': 'passed', 'configured_credential_scan': 'passed'}
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == '__main__':
    print(json.dumps(package(), ensure_ascii=False))
