"""Build native delivery from ui/ without npm installation or runtime imports.

Run --check in validation to reject stale bundles. All output is prepared and
validated before any tracked delivery file is replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import html

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ui'
sys.path.insert(0, str(ROOT / 'backend'))
from app.practice_policy import practice_configuration


def source_fingerprint(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def public_practice():
    questions = []
    for path in sorted((ROOT / 'data/question_bank').glob('*.jsonl')):
        questions.extend(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
                         if line.strip() and not line.lstrip().startswith('#'))
    return practice_configuration(questions)


def load_manifest():
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['format'] == 1
    pages = manifest['pages']
    assert len({p['template'] for p in pages}) == len(pages)
    assert len({p['script'] for p in pages}) == len(pages)
    routes = [p['route'] for p in pages if p['route']]
    assert len(set(routes)) == len(routes)
    assert all(row['path'] in routes for row in manifest['navigation']), 'Unregistered navigation route'
    for p in pages:
        assert re.fullmatch(r'[a-z-]+\.html', p['template'])
        assert re.fullmatch(r'[a-z-]+\.js', p['script'])
    for name in manifest['styles']:
        assert re.fullmatch(r'[a-z0-9-]+\.css', name)
    for name in manifest.get('images', []):
        assert re.fullmatch(r'[a-z0-9-]+\.webp', name)
    return manifest


def workspace_navigation(manifest, route, parent=None):
    def link(row):
        return ('<a href="' + html.escape(row['path'], quote=True) + '"' +
                (' aria-current="page"' if row['path'] == route else ' aria-current="location"' if row['path'] == parent else '') +
                '>' + html.escape(row['label']) + '</a>')

    primary_rows = [row for row in manifest['navigation'] if not row.get('group')]
    primary = ''.join(link(row) for row in primary_rows)
    groups = {}
    for row in manifest['navigation']:
        if row.get('group'):
            groups.setdefault(row['group'], []).append(row)
    current = next((row['label'] for row in manifest['navigation']
                    if row['path'] in (route, parent) and row.get('group')), None)
    panel = ''.join('<div class="workspace-nav-section"><p>' + html.escape(name) + '</p>' +
                    ''.join(link(row) for row in rows) + '</div>' for name, rows in groups.items())
    short = [{'path': '/#start', 'label': '开始练习'}] + [row for row in primary_rows if row['path'] != '/']
    panel = ('<div class="workspace-nav-section mobile-nav-primary"><p>开始练习</p>' +
             ''.join(link(row) for row in short) + '</div>') + panel
    more = ('<details class="workspace-nav-more" data-navigation-menu><summary' +
            (' data-current-section' if current else '') + '>' +
            '<span class="desktop-nav-label">更多功能</span><span class="mobile-nav-label">菜单</span>'
            '</summary><div class="workspace-nav-panel">' + panel + '</div></details>')
    return '<nav class="notes-nav-links workspace-navigation" aria-label="工作区导航">' + primary + more + '</nav>'


def add_onboarding(text, page, guide, template):
    home = page == 'home'
    entry = ('<button id="tour-open" class="tour-open" type="button" aria-haspopup="dialog" '
             'aria-controls="onboarding" hidden>' + ('新手指引' if home else '本页指引') + '</button>')
    if home:
        text = text.replace('<!-- @onboarding-launcher -->', entry)
        finish = '<a id="tour-finish" class="notes-button notes-primary" href="#start" hidden>去配置练习</a>'
    else:
        hint = html.escape(guide['hint'])
        entry = ('<div class="container tour-entry"><p id="tour-hint" hidden>' + hint + '</p>' + entry + '</div>')
        text = re.sub(r'<main\b', lambda match: entry + '\n  ' + match[0], text, count=1)
        finish = '<button id="tour-finish" class="notes-button notes-primary" type="button" hidden>完成指引</button>'
    values = {'page': page, 'title': html.escape(guide['title']),
              'steps': html.escape(json.dumps(guide['steps'], ensure_ascii=False), quote=True),
              'total': str(len(guide['steps'])), 'finish': finish}
    dialog = re.sub(r'{{([a-z]+)}}', lambda match: values[match[1]], template)
    assert text.count('id="tour-open"') == 1 and text.count('</body>') == 1
    return text.replace('</body>', dialog + '</body>')


def outputs():
    manifest = load_manifest()
    practice = public_practice()
    guides = json.loads((SOURCE / 'onboarding.json').read_text(encoding='utf-8'))
    guide_template = (SOURCE / 'templates/components/onboarding.html').read_text(encoding='utf-8')
    assert set(guides) <= {page['key'] for page in manifest['pages']}
    result = {}
    images = {ROOT / 'assets' / name: (ROOT / 'assets' / name).read_bytes()
              for name in manifest.get('images', [])}
    for page in manifest['pages']:
        text = (SOURCE / 'templates' / page['template']).read_text(encoding='utf-8')
        if page['key'] == 'home':
            roles = practice['positions']
            options = ''.join('<option value="' + html.escape(key, quote=True) + '">' +
                              html.escape(item['name']) + ' · ' + str(item['count']) + ' 道练习题</option>'
                              for key, item in roles.items())
            text = text.replace('<!-- @position-options -->', options)
            text = text.replace('<!-- @duration-options -->', ''.join(
                '<option value="' + str(row['minutes']) + '">' + str(row['minutes']) +
                ' 分钟 · 最多 ' + str(row['question_count']) + ' 题</option>' for row in practice['durations']))
            text = text.replace('{{position_count}}', str(len(roles))).replace('{{question_count}}', str(practice['question_count']))
            text = text.replace('{{position_names}}', html.escape('、'.join(item['name'] for item in roles.values())))
        if page['workspace_navigation'] or page['key'] == 'home':
            text = text.replace('<!-- @workspace-navigation -->', workspace_navigation(manifest, page['route'], page.get('navigation_parent')))
        assert '<!-- @workspace-navigation -->' not in text
        # Scene-specific headers keep their focused links, with the same destination names.
        def header_labels(match):
            header = match[0]
            for row in manifest['navigation']:
                header = re.sub(r'(<a\b[^>]*href="' + re.escape(row['path']) + r'"[^>]*>)[^<]+(</a>)',
                                lambda item: item[1] + html.escape(row['label']) + item[2], header)
            return header
        text = re.sub(r'<header\b[\s\S]*?</header>', header_labels, text, count=1)
        menu = ('<details class="user-menu-group"><summary class="user-menu" aria-label="账户与登录">'
                '<span class="user-avatar" aria-hidden="true"><img data-account-image hidden alt="">'
                '<span data-user-initial>青</span></span><span data-user-name>登录 / 注册</span>'
                '<span class="mobile-account-label">账户</span></summary>'
                '<nav class="user-menu-links" aria-label="个人空间"><a href="/account" data-account-entry>登录 / 注册</a>'
                '<a href="/dashboard" data-account-only hidden>练习概览</a>'
                '<a href="/account?view=profile" data-account-only hidden>编辑资料</a>'
                '<a href="/account#security-settings" data-account-only hidden>账户与安全</a>'
                '<a href="/admin" data-admin-only hidden>管理工作台</a>'
                '<a href="/guide">使用指南</a></nav></details>')
        text=re.sub(r'(</div>\s*</header>)',lambda m:menu+m[0],text,count=1)
        scripts = [name for name in page.get('shared_scripts', manifest['shared_scripts'])
                   if name != 'onboarding.js']
        if page['key'] in guides:
            text = add_onboarding(text, page['key'], guides[page['key']], guide_template)
            scripts.append('onboarding.js')
        for shared in scripts:
            text=text.replace('</head>','<script src="'+('assets/' if page['key']=='home' else '/assets/')+shared+'" defer></script>\n</head>')
        result[ROOT / page['template']] = text.encode('utf-8')
        script = (SOURCE / 'pages' / page['script']).read_text(encoding='utf-8')
        bundle = re.fullmatch(r'/\* @bundle (assistant|studio|widget|admin) \*/', script.strip())
        if bundle:
            name = bundle[1]
            metadata = json.loads((SOURCE / ('compiled/' + name + '.json')).read_text(encoding='utf-8'))
            expected = {'tools/build_frontend.mjs', 'frontend/vite.config.mjs', 'frontend/package.json', 'frontend/package-lock.json', 'frontend/tsconfig.json', 'frontend/tsconfig.web.json'} | {
                p.relative_to(ROOT).as_posix() for directory in ('assistant', 'studio', 'shared', 'lib', 'widget', 'admin')
                for p in (ROOT / 'frontend' / directory).rglob('*') if p.suffix in ('.ts', '.tsx')}
            assert metadata.get('builder') == 'vite' and set(metadata['files']) == expected, 'Run npm run build in frontend'
            for name, digest in metadata['files'].items():
                assert source_fingerprint(name) == digest, 'Run npm run build in frontend'
            script = (SOURCE / ('compiled/' + bundle[1] + '.js')).read_text(encoding='utf-8')
            assert hashlib.sha256(script.encode('utf-8')).hexdigest() == metadata['sha256'], 'React bundle changed'
        script = script.replace('/* @practice-catalog */', json.dumps(practice['positions'], ensure_ascii=False))

        def module(match):
            # Names are source-controlled, bounded paths; modules share the page's lexical scope.
            return (SOURCE / 'modules' / (match[1] + '.js')).read_text(encoding='utf-8')

        script = re.sub(r'/\* @module ([a-z]+/[a-z]+) \*/', module, script)
        assert '@module' not in script

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
    def stylesheet(name):
        source = (SOURCE / 'styles' / name).read_text(encoding='utf-8')
        return re.sub(r'/\* @style ([a-z]+/[a-z]+) \*/', lambda match:
            (SOURCE / 'styles' / (match[1] + '.css')).read_text(encoding='utf-8'), source)

    css = '\n'.join('/* Source: ui/styles/' + name + ' */\n' + stylesheet(name)
                    for name in manifest['styles'])
    result[ROOT / 'assets/home.css'] = css.encode('utf-8')
    for page in manifest['pages']:
        if page.get('stylesheet'):
            assert re.fullmatch(r'[a-z-]+\.css', page['stylesheet'])
            result[ROOT / 'assets' / page['stylesheet']] = (css + '\n' + stylesheet(page['style_source'])).encode('utf-8')
    for name in manifest.get('shared_scripts',[]):
        script=(SOURCE/'shared'/name).read_text(encoding='utf-8')
        script=re.sub(r'/\* @include ([a-z]+) \*/', lambda match: (SOURCE/'shared'/(match[1]+'.js')).read_text(encoding='utf-8'), script)
        if name == 'qing-pet.js':
            metadata = json.loads((SOURCE / 'compiled/widget.json').read_text(encoding='utf-8'))
            for source, digest in metadata['files'].items():
                assert source_fingerprint(source) == digest, 'Run npm run build in frontend'
            data = (SOURCE / 'compiled/widget.js').read_bytes()
            assert hashlib.sha256(data).hexdigest() == metadata['sha256'] and len(data) < 190000
            result[ROOT/'assets/qing-widget.js'] = data
            script = script.replace("'@widget-asset'", json.dumps('/assets/qing-widget.js?v=' + metadata['sha256'][:12]))
        result[ROOT/'assets'/name]=script.encode('utf-8')
    def versioned_asset(match):
        path = ROOT / match[2].lstrip('/')
        digest = hashlib.sha256(images[path] if path in images else result[path]).hexdigest()[:12]
        return match[1] + match[2] + '?v=' + digest + match[3]

    for path in [path for path in result if path.suffix == '.html']:
        text = result[path].decode('utf-8')
        text = re.sub(r'((?:src|href)=")(/?assets/[a-z0-9-]+\.(?:js|css|webp))(")', versioned_asset, text)
        result[path] = text.encode('utf-8')
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
