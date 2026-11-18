"""Generate cloud-only settings without changing backend/.env or printing credentials."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def hostname(*, host=None, ip=None):
    if ip:
        address = ipaddress.ip_address(ip)
        if address.version != 4 or not address.is_global:
            raise ValueError('请填写可从公网访问的IPv4地址。')
        return 'qingzhan.' + str(address).replace('.', '-') + '.sslip.io'
    value = (host or '').strip().lower().rstrip('.')
    if len(value) > 253 or '.' not in value or not all(
            re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.')):
        raise ValueError('请填写纯域名，不带https、端口或路径；只有公网IPv4时使用--ip。')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError('直接IP需单独配置IP证书；使用--ip生成自动HTTPS测试域名。')


def read_env(path):
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('配置文件中存在无效行，请使用KEY=value格式。')
        key, value = line.split('=', 1)
        key = key.strip()
        if key in result:
            raise ValueError('配置文件包含重复设置，请保留每项一行。')
        result[key] = value
    return result


def write_private(path, values, *, replace=False):
    content = '# Generated cloud-only settings; do not share or commit.\n' + ''.join(
        key + '=' + value + '\n' for key, value in values.items())
    if any('\n' in value or '\r' in value or '\0' in value for value in values.values()):
        raise ValueError('配置值不能包含换行或空字符。')
    if not replace:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as target:
            target.write(content)
    else:
        handle, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as target:
                target.write(content)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def setup(root, *, host=None, ip=None):
    target = hostname(host=host, ip=ip)
    directory = root / 'deploy/cloud'
    public, private = directory / '.env', directory / 'app.env'
    for path in (public, private):
        if path.is_symlink():
            raise ValueError('不接受符号链接配置文件。')
    if public.exists() and read_env(public).get('SITE_HOST') != target:
        raise ValueError('已有不同站点配置；更换域名请按部署文档修改，现有文件未覆盖。')
    values = read_env(private if private.exists() else directory / 'app.env.example')
    if private.exists():
        if json.loads(values.get('CORS_ORIGINS', '[]')) != ['https://' + target]:
            raise ValueError('现有CORS_ORIGINS与站点不一致，请核对；文件未覆盖。')
    else:
        values.update(CORS_ORIGINS=json.dumps(['https://' + target], separators=(',', ':')),
                      AUTH_CHALLENGE_SECRET=secrets.token_urlsafe(48))
    if not public.exists():
        write_private(public, {'SITE_HOST': target})
    if not private.exists():
        write_private(private, values)
    return target


def configure_voice(root, key):
    path = root / 'deploy/cloud/app.env'
    if not path.is_file() or path.is_symlink():
        raise ValueError('请先使用--ip或--host完成初始化。')
    if not key.strip() or any(char in key for char in '\r\n\0'):
        raise ValueError('未提供有效语音密钥，配置未改动。')
    values = read_env(path)
    values.update(VOICE_ENABLED='true', VOICE_ASR_PROVIDER='doubao', VOICE_TTS_PROVIDER='doubao',
                  DOUBAO_VOICE_AUTH_MODE='api_key', DOUBAO_VOICE_API_KEY=key.strip())
    write_private(path, values, replace=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--ip', help='公网IPv4，自动生成sslip.io测试域名')
    group.add_argument('--host', help='已解析到服务器的自有域名')
    parser.add_argument('--voice', action='store_true', help='隐藏输入语音API Key，并启用实时语音')
    args = parser.parse_args()
    if not (args.ip or args.host or args.voice):
        parser.error('请使用--ip、--host或--voice。')
    try:
        if args.ip or args.host:
            target = setup(ROOT, host=args.host, ip=args.ip)
            print('配置已就绪，访问地址：https://' + target)
        if args.voice:
            configure_voice(ROOT, getpass.getpass('语音服务API Key（隐藏输入，留空取消）：'))
            print('语音配置已保存，请重新创建app容器使配置生效。')
    except (ValueError, OSError, EOFError):
        # Do not include configuration lines or credentials in error output.
        parser.exit(2, '初始化未完成。请检查参数、现有站点配置及文件权限；未输出任何密钥。\n')


if __name__ == '__main__':
    main()
