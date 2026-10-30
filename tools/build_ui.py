"""Build native delivery from ui/ without npm installation or runtime imports.

Run --check in validation to reject stale bundles. All output is prepared and
validated before any tracked delivery file is replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ui'


def load_manifest():
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['format'] == 1
    pages = manifest['pages']
    assert len({p['template'] for p in pages}) == len(pages)
    assert len({p['script'] for p in pages}) == len(pages)
    routes = [p['route'] for p in pages if p['route']]
    assert len(set(routes)) == len(routes)
    for p in pages:
        assert re.fullmatch(r'[a-z-]+\.html', p['template'])
        assert re.fullmatch(r'[a-z-]+\.js', p['script'])
    for name in manifest['styles']:
        assert re.fullmatch(r'[a-z0-9-]+\.css', name)
    return manifest


def outputs():
    manifest = load_manifest()
    result = {}
    for page in manifest['pages']:
        text = (SOURCE / 'templates' / page['template']).read_text(encoding='utf-8')
        if page['workspace_navigation']:
            links = ''.join('<a href="' + row['path'] + '"' +
                            (' aria-current="page"' if row['path'] == page['route'] else '') +
                            '>' + row['label'] + '</a>' for row in manifest['navigation'])
            text = text.replace('<!-- @workspace-navigation -->',
                '<nav class="notes-nav-links workspace-navigation" aria-label="工作区导航">' + links + '</nav>')
        assert '<!-- @workspace-navigation -->' not in text
        menu='<a class="user-menu" href="/account" aria-label="账户与登录"><span class="user-avatar" aria-hidden="true"><img data-account-image hidden alt=""><span data-user-initial>青</span></span><span data-user-name>登录 / 注册</span></a>'
        text=re.sub(r'(</div>\s*</header>)',lambda m:menu+m[0],text,count=1)
        for shared in manifest.get('shared_scripts',[]):
            text=text.replace('</head>','<script src="'+('assets/' if page['key']=='home' else '/assets/')+shared+'" defer></script>\n</head>')
        result[ROOT / page['template']] = text.encode('utf-8')
        script = (SOURCE / 'pages' / page['script']).read_text(encoding='utf-8')

        def include(match):
            return (SOURCE / 'shared' / (match[1] + '.js')).read_text(encoding='utf-8')

        script = re.sub(r'/\* @include ([a-z]+) \*/', include, script)
        assert '@include' not in script
        # Keep functions and statement line breaks; save indentation bytes in delivery.
        lines = [re.sub(r'^(?:  )+', lambda m: '\t' * (len(m[0]) // 2), line.rstrip())
                 for line in script.splitlines() if line.strip() and not line.lstrip().startswith('//')]
        data = ('/* Generated: tools/build_ui.py */\n' +
                '\n'.join(lines) + '\n').encode('utf-8')
        assert len(data) < page.get('javascript_budget', 15000), (page['script'], len(data))
        result[ROOT / 'assets' / page['script']] = data
    css = '\n'.join('/* Source: ui/styles/' + name + ' */\n' +
                    (SOURCE / 'styles' / name).read_text(encoding='utf-8')
                    for name in manifest['styles'])
    result[ROOT / 'assets/home.css'] = css.encode('utf-8')
    for name in manifest.get('shared_scripts',[]):
        script=(SOURCE/'shared'/name).read_text(encoding='utf-8')
        script=script.replace('/* @include session */',(SOURCE/'shared/session.js').read_text(encoding='utf-8'))
        result[ROOT/'assets'/name]=script.encode('utf-8')
    return result


def build(check=False):
    prepared = outputs()
    stale = [str(p.relative_to(ROOT)) for p, content in prepared.items()
             if not p.exists() or p.read_bytes() != content]
    if check and stale:
        raise SystemExit('Stale generated output: ' + ', '.join(stale))
    if not check:
        for path, data in prepared.items():
            if str(path.relative_to(ROOT)) in stale:
                path.write_bytes(data)
    return {'result': 'passed', 'mode': 'check' if check else 'build',
            'generated_files': len(prepared), 'changed': len(stale),
            'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(data).hexdigest()
                       for p, data in prepared.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.check), ensure_ascii=True))
