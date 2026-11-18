import re
from types import SimpleNamespace

from app.services.web_origin import allowed_origin
from tests.test_ws_recovery import api


def test_native_pages_and_assets_are_same_origin(api):
    client, _ = api
    home = client.get('/')
    assert home.status_code == 200
    assert 'data-api="/api" data-workspace-base=""' in home.text
    assert home.headers['cache-control'] == 'no-store'
    assert home.headers['referrer-policy'] == 'no-referrer'
    assert home.headers['x-frame-options'] == 'DENY'
    assert client.head('/account').status_code == 200
    guide = client.get('/guide')
    assert guide.status_code == 200
    assert 'id="guide-title"' in guide.text
    assert client.get('/guide.html', follow_redirects=False).headers['location'] == '/guide'
    assert client.get('/assets/guide.js').status_code == 200
    assert client.get('/assets/home.css').status_code == 200
    assert client.get('/account').status_code == 200
    assert client.get('/account.html?next=%2Fcatalog', follow_redirects=False).headers['location'] == '/account?next=%2Fcatalog'
    interview_id = 'a' * 32
    detail = '/interview/' + interview_id
    assert client.get(detail + '/?mode=voice', follow_redirects=False).headers['location'] == detail + '?mode=voice'
    assert '实时语音陪练' in client.get('/interview/' + interview_id + '?mode=realtime').text
    assert '语音练习室' in client.get('/interview/' + interview_id + '?mode=voice').text
    assert client.get('/interview/not-an-id').status_code == 404
    assert client.get('/backend/.env').status_code == 404
    assert client.get('/missing-page').status_code == 404


def test_forum_entry_loads_generated_assets_and_api(api):
    client, _ = api
    assert 'href="/forum"' in client.get('/').text
    page = client.get('/forum')
    assert page.status_code == 200
    assert 'id="forum-content"' in page.text
    for asset in ('forum.js', 'forum.css'):
        match = re.search(r'"(/assets/' + re.escape(asset) + r'(?:\?[^"]*)?)"', page.text)
        assert match and client.get(match[1]).status_code == 200
    assert client.head('/forum').status_code == 200
    for alias in ('/forum.html', '/forum/'):
        response = client.get(alias + '?view=new', follow_redirects=False)
        assert response.status_code == 308 and response.headers['location'] == '/forum?view=new'
    assert client.get('/api/forum/posts').json() == {'items': [], 'next_offset': None}


def test_account_backdrop_and_guide_are_served_same_origin(api):
    client, _ = api
    account = client.get('/account')
    asset_path = re.search(r'src="(/assets/login-bamboo\.webp\?v=[0-9a-f]{12})"', account.text)
    assert asset_path is not None
    image = client.get(asset_path[1])
    assert image.status_code == 200 and image.headers['content-type'] == 'image/webp'
    assert image.content.startswith(b'RIFF') and len(image.content) < 250_000
    assert 'id="onboarding"' in client.get('/?tour=1').text
    assert 'href="/?tour=1"' in client.get('/guide').text


def test_page_guides_load_one_shared_script_and_use_route_specific_steps(api):
    client, _ = api
    interview_id = 'a' * 32
    pages = [('/catalog', 'catalog'), ('/account', 'account'), ('/forum', 'forum'),
             ('/assistant', 'assistant'), ('/report/' + interview_id, 'report'),
             ('/interview/' + interview_id + '?mode=voice', 'voice'),
             ('/interview/' + interview_id + '?mode=realtime', 'realtime')]
    assets = set()
    for url, guide in pages:
        page = client.get(url)
        assert page.status_code == 200
        assert page.text.count('id="onboarding"') == 1
        assert 'data-tour-page="' + guide + '"' in page.text
        paths = re.findall(r'src="(/assets/onboarding\.js\?v=[0-9a-f]{12})"', page.text)
        assert len(paths) == 1
        assets.update(paths)
    assert len(assets) == 1 and client.get(assets.pop()).status_code == 200
    assert 'href="/forum?tour=1"' in client.get('/guide').text


def test_validation_does_not_echo_private_payload(api):
    client, _ = api
    response = client.post('/api/interview', json={'position': {'secret': 'private-interview-input'}})
    assert response.status_code == 422
    assert 'private-interview-input' not in response.text
    assert response.headers['cache-control'] == 'no-store'


def test_origin_validation_requires_exact_host_and_scheme():
    def ws(origin, host='localhost:8000', scheme='ws'):
        return SimpleNamespace(headers={'origin': origin, 'host': host}, scope={'scheme': scheme})
    assert allowed_origin(ws('http://localhost:8000'), [])
    assert allowed_origin(ws('https://example.org', host='example.org', scheme='wss'), [])
    assert allowed_origin(ws('https://client.example'), ['https://client.example'])
    for origin in ('http://evil.example', 'http://localhost:8000.evil.example',
                   'https://localhost:8000', 'http://localhost:8000/path', 'http://[invalid'):
        assert not allowed_origin(ws(origin), [])
