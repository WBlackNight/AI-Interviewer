"""原生首页交付约束与本地数据检查；不启动浏览器、不访问网络、不读取.env。"""
from collections import Counter
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.ids = []
        self.references = []
        self.answer = []
        self.in_answer = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for key in ("aria-labelledby", "aria-describedby", "aria-controls", "for"):
            self.references.extend(attrs.get(key, "").split())
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.references.append(attrs["href"][1:])
        if tag == "blockquote":
            self.in_answer = True

    def handle_endtag(self, tag):
        if tag == "blockquote":
            self.in_answer = False

    def handle_data(self, value):
        if self.in_answer:
            self.answer.append(value)


# 体积按交付文件原始字节计算，避免Windows文本读取归一化CRLF后少计。
def javascript_size(name):
    size = len((ROOT / 'assets' / name).read_bytes())
    manifest = json.loads((ROOT / 'ui/manifest.json').read_text(encoding='utf-8'))
    budget = next((p.get('javascript_budget', 15000) for p in manifest['pages'] if p['script'] == name),10000)
    assert size < budget, (name, size)
    return size


def check():
    sys.path.insert(0, str(ROOT))
    from tools.build_ui import build
    build(check=True)
    for name in ("index.html", "assets/home.css", "assets/home.js", "assets/README.md"):
        assert (ROOT / name).is_file(), name
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "assets/home.css").read_text(encoding="utf-8")
    script = (ROOT / "assets/home.js").read_text(encoding="utf-8")
    page = Page()
    page.feed(html)
    assert len(page.elements) < 900
    assert all(count == 1 for count in Counter(page.ids).values()), "重复ID"
    assert set(page.references) <= set(page.ids), "锚点或无障碍引用缺失"
    assert not any("style" in attrs or any(key.startswith("on") for key in attrs) for _, attrs in page.elements)
    assert not any(tag in ("iframe", "style") or (tag == "img" and "data-account-image" not in attrs and attrs.get("id") not in ("account-captcha-image", "profile-avatar")) for tag, attrs in page.elements)
    resources = [attrs.get("src") for tag, attrs in page.elements if tag == "script"]
    resources += [attrs.get("href") for tag, attrs in page.elements if tag == "link" and attrs.get("rel") == "stylesheet"]
    assert sorted(resources) == sorted(["assets/home.css", "assets/home.js", "assets/account-menu.js"]), resources
    assert not re.search(r"@import|url\s*\(|position\s*:\s*fixed", css, re.I)
    assert not re.search(r"\b(?:import|require)\s*\(", script)
    assert not re.search(r"[\U0001f300-\U0001faff]", html), "未使用emoji图标"
    script_bytes = javascript_size("home.js")
    notes_page = Page()
    notes_page.feed((ROOT / "revision-notes.html").read_text(encoding="utf-8"))
    notes_script = (ROOT / "assets/revision-notes.js").read_text(encoding="utf-8")
    notes_bytes = javascript_size("revision-notes.js")
    assert all(count == 1 for count in Counter(notes_page.ids).values())
    assert set(notes_page.references) <= set(notes_page.ids)
    assert not any("style" in attrs or any(key.startswith("on") for key in attrs) for _, attrs in notes_page.elements)
    assert not any(tag in ("iframe", "style") or (tag == "img" and "data-account-image" not in attrs and attrs.get("id") not in ("account-captcha-image", "profile-avatar")) for tag, attrs in notes_page.elements)
    notes_resources = [attrs.get("src") for tag, attrs in notes_page.elements if tag == "script"]
    notes_resources += [attrs.get("href") for tag, attrs in notes_page.elements if tag == "link" and attrs.get("rel") == "stylesheet"]
    assert sorted(notes_resources) == sorted(["/assets/home.css", "/assets/revision-notes.js", "/assets/account-menu.js"])
    assert not re.search(r"innerHTML|\b(?:import|require)\s*\(", notes_script)
    board_page = Page()
    board_page.feed((ROOT / "revision.html").read_text(encoding="utf-8"))
    board_script = (ROOT / "assets/revision-board.js").read_text(encoding="utf-8")
    board_bytes = javascript_size("revision-board.js")
    assert all(count == 1 for count in Counter(board_page.ids).values())
    assert set(board_page.references) <= set(board_page.ids)
    assert not any("style" in attrs or any(key.startswith("on") for key in attrs) for _, attrs in board_page.elements)
    assert not any(tag in ("iframe", "style") or (tag == "img" and "data-account-image" not in attrs and attrs.get("id") not in ("account-captcha-image", "profile-avatar")) for tag, attrs in board_page.elements)
    board_resources = [attrs.get("src") for tag, attrs in board_page.elements if tag == "script"]
    board_resources += [attrs.get("href") for tag, attrs in board_page.elements if tag == "link" and attrs.get("rel") == "stylesheet"]
    assert sorted(board_resources) == sorted(["/assets/home.css", "/assets/revision-board.js", "/assets/account-menu.js"])
    assert not re.search(r"innerHTML|\b(?:import|require)\s*\(", board_script)
    workspace_pages = {}
    for name in ('account', 'history', 'report', 'review', 'interview', 'dashboard', 'catalog', 'library', 'coverage', 'plans', 'plan-history', 'voice', 'realtime'):
        native_page = Page()
        native_page.feed((ROOT / (name + '.html')).read_text(encoding='utf-8'))
        native_script = (ROOT / 'assets' / (name + '.js')).read_text(encoding='utf-8')
        native_bytes = javascript_size(name + '.js')
        assert all(count == 1 for count in Counter(native_page.ids).values())
        assert set(native_page.references) <= set(native_page.ids)
        assert not any('style' in attrs or any(key.startswith('on') for key in attrs) for _, attrs in native_page.elements)
        assert not any(tag in ('iframe', 'style') or (tag == 'img' and 'data-account-image' not in attrs and attrs.get('id') not in ('account-captcha-image', 'profile-avatar')) for tag, attrs in native_page.elements)
        native_resources = [attrs.get('src') for tag, attrs in native_page.elements if tag == 'script']
        native_resources += [attrs.get('href') for tag, attrs in native_page.elements if tag == 'link' and attrs.get('rel') == 'stylesheet']
        assert sorted(native_resources) == sorted(['/assets/' + name + '.js', '/assets/home.css', '/assets/account-menu.js'])
        assert not re.search(r'innerHTML|\b(?:import|require)\s*\(', native_script)
        workspace_pages[name] = {'javascript_bytes': native_bytes, 'html_element_count': len(native_page.elements)}
    data, grouped = {}, {}
    for path in (ROOT / "data/question_bank").glob("*.jsonl"):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            grouped.setdefault(row['position'], []).append(row)
    for position, rows in grouped.items():
        themes = sorted({row["theme"] for row in rows if not row.get("is_coding")})
        assert all(theme in script for theme in themes)
        assert f'"count": {len(rows)}' in script or f"count: {len(rows)}" in script
        data[position] = {"count": len(rows), "themes": themes}
    assert sum(item["count"] for item in data.values()) == 120
    sys.path.insert(0, str(ROOT / "backend"))
    from app.domain import Question
    from app.agent.scorer import HeuristicScorer
    rows = [json.loads(line) for line in (ROOT / "data/question_bank/java_backend.jsonl").read_text(encoding="utf-8").splitlines()]
    question = Question.from_dict(next(row for row in rows if row["id"] == "jv-mysql-index-001"))
    answer = "".join(page.answer)
    result = HeuristicScorer().score(question, answer)
    assert len(answer) == 51
    assert result.score == 6.3 and result.dimensions == {"技术深度": 7.5, "表达逻辑": 2.5, "岗位匹配": 6.3}
    assert len(result.key_points_hit) == 3 and len(result.key_points_missed) == 1
    return {"result": "passed", "javascript_size_basis": "raw_file_bytes", "javascript_bytes": script_bytes, "html_element_count": len(page.elements),
            "initial_document_requests": 4, "external_resources": 0, "inline_style_attributes": 0,
            "inline_event_handlers": 0, "fixed_position_rules": 0, "catalog": data,
            "example_score": result.score, "example_dimensions": result.dimensions, "example_answer_chars": len(answer),
            "runtime_dependencies": 0, "notes_javascript_bytes": notes_bytes,
            "notes_html_element_count": len(notes_page.elements), "notes_static_document_requests": 4,
            "board_javascript_bytes": board_bytes, "board_html_element_count": len(board_page.elements),
            "workspace_pages": workspace_pages}


if __name__ == "__main__":
    result = check()
    log_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    output = ROOT / "docs/logs" / log_date / "native-home/static-check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
