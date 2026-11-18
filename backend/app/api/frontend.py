"""Serve the built native UI from the same origin as the API and WebSockets."""
import json
from mimetypes import add_type
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[3]
router = APIRouter(include_in_schema=False)
add_type('image/webp', '.webp')


def page_registry():
    manifest = json.loads((ROOT / 'ui/manifest.json').read_text(encoding='utf-8'))
    return {item['route']: item['template'] for item in manifest['pages'] if item['route']}


def render_page(name):
    if not re.fullmatch(r'[a-z-]+\.html', name):
        raise HTTPException(404, '页面不存在')
    path = ROOT / name
    if not path.is_file():
        raise HTTPException(503, '页面尚未生成，请先运行前端构建')
    content = path.read_text(encoding='utf-8')
    if name == 'index.html':
        marker = '<body data-api="" data-workspace-base="http://localhost:3000">'
        if content.count(marker) != 1:
            raise HTTPException(503, '首页接入标记无效，请重新构建')
        content = content.replace(marker, '<body data-api="/api" data-workspace-base="">')
    return HTMLResponse(content, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.api_route('/interview/{interview_id}', methods=['GET', 'HEAD'])
def interview_page(interview_id: str, mode: str = 'text'):
    if not re.fullmatch(r'[a-f0-9]{32}', interview_id):
        raise HTTPException(404, '页面不存在')
    return render_page({'voice': 'voice.html', 'realtime': 'realtime.html'}.get(mode, 'interview.html'))


@router.api_route('/report/{interview_id}', methods=['GET', 'HEAD'])
def report_page(interview_id: str):
    if not re.fullmatch(r'[a-f0-9]{32}', interview_id):
        raise HTTPException(404, '页面不存在')
    return render_page('report.html')


@router.api_route('/', methods=['GET', 'HEAD'])
def home_page():
    return render_page('index.html')


@router.api_route('/{page}', methods=['GET', 'HEAD'])
def named_page(page: str, request: Request):
    registry = page_registry()
    route = '/' + page
    if route in registry:
        return render_page(registry[route])
    aliases = {item: route for route, item in registry.items()}
    if page in aliases:
        target = aliases[page]
        if request.url.query:
            target += '?' + request.url.query
        return RedirectResponse(target, status_code=308)
    raise HTTPException(404, '页面不存在')


def attach_frontend(app):
    @app.middleware('http')
    async def canonical_page(request, call_next):
        path = request.url.path
        if request.method in ('GET', 'HEAD') and path != '/' and path.endswith('/'):
            canonical = path.rstrip('/')
            if canonical in page_registry() or re.fullmatch(r'/(interview|report)/[a-f0-9]{32}', canonical):
                query = request.url.query
                return RedirectResponse(canonical + ('?' + query if query else ''), status_code=308)
        return await call_next(request)

    app.mount('/assets', StaticFiles(directory=ROOT / 'assets', check_dir=False), name='native-assets')
    app.include_router(router)
