"""Render the checked-in competition Markdown as an A4 review PDF."""
import argparse
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
PINE = colors.HexColor('#183D31')
INK = colors.HexColor('#20352E')
MUTED = colors.HexColor('#486159')
PALE = colors.HexColor('#EAF2ED')
GRID = colors.HexColor('#CEDCD4')
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 48
WIDTH = PAGE_WIDTH - MARGIN * 2


def text_style(size, leading, **options):
    return ParagraphStyle('qingzhan', fontName='QingBody', fontSize=size, leading=leading,
                          textColor=INK, wordWrap='CJK', alignment=TA_LEFT, **options)


def paragraph(text, style):
    return Paragraph(escape(text).replace('`', ''), style)


def table(rows):
    count = len(rows[0])
    assert all(len(row) == count for row in rows)
    widths = [WIDTH * .3, WIDTH * .7] if count == 2 else [WIDTH * .20, WIDTH * .42, WIDTH * .38]
    heading = text_style(10, 15)
    heading.textColor = colors.white
    body = text_style(9.8, 16)
    result = Table([[paragraph(cell, heading if i == 0 else body) for cell in row]
                    for i, row in enumerate(rows)], colWidths=widths, hAlign='LEFT', repeatRows=1)
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PINE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE]),
        ('LINEBELOW', (0, 0), (-1, -1), .4, GRID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    return result


def diagram(name):
    if name == 'architecture':
        height = 125
        boxes = [('浏览器', '原生页面与 React'),
                 ('FastAPI 网关', 'HTTP / SSE / WS'),
                 ('应用服务与存储', '规划 / 评分 / SQLite')]
        caption = '服务端按配置连接文本模型、语音和可选外部服务。'
    else:
        height = 111
        boxes = [('题库与大纲', '岗位 / 时长'),
                 ('提交与评分', '锚点 / 版本'),
                 ('追问与复练', '技能树 / 报告')]
        caption = '未覆盖锚点决定追问方向，报告记录依据与建议。'
    graph = Drawing(WIDTH, height)
    graph.add(Rect(0, 3, WIDTH, height - 6, rx=9, ry=9, fillColor=PALE, strokeColor=None))
    box_width = 136
    lefts = [12, (WIDTH - box_width) / 2, WIDTH - box_width - 12]
    y = height - 73
    for x, (title, sub) in zip(lefts, boxes):
        graph.add(Rect(x, y, box_width, 55, rx=7, ry=7, fillColor=colors.white, strokeColor=GRID))
        graph.add(String(x + box_width / 2, y + 33, title, textAnchor='middle',
                         fontName='QingBody', fontSize=11.1, fillColor=PINE))
        graph.add(String(x + box_width / 2, y + 15, sub, textAnchor='middle',
                         fontName='QingBody', fontSize=8.5, fillColor=MUTED))
    for left, right in zip(lefts, lefts[1:]):
        end = right - 4
        mid = y + 27
        graph.add(Line(left + box_width + 4, mid, end, mid, strokeColor=MUTED, strokeWidth=1.2))
        graph.add(Polygon([end, mid, end - 5, mid + 3, end - 5, mid - 3], fillColor=MUTED, strokeColor=None))
    graph.add(String(14, 15, caption, fontName='QingBody', fontSize=9, fillColor=MUTED))
    return graph


def render(source, destination, font):
    pdfmetrics.registerFont(TTFont('QingBody', str(font), subfontIndex=0))
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=MARGIN - 6,
                            rightMargin=MARGIN - 6, topMargin=65, bottomMargin=51,
                            title='青栈 AI Interviewer · 传智杯技术文档')
    styles = {
        'cover': text_style(34, 45, spaceAfter=9),
        'title': text_style(23, 31, spaceAfter=17),
        'section': text_style(13, 22, spaceBefore=12, spaceAfter=4),
        'body': text_style(10.8, 19, spaceAfter=8),
        'list': text_style(10.8, 19, spaceAfter=7, leftIndent=13, firstLineIndent=-13),
    }
    styles['title'].textColor = PINE
    styles['cover'].textColor = PINE
    styles['section'].textColor = PINE
    story = []
    rows = []

    def flush():
        if rows:
            story.extend((table(rows), Spacer(1, 12)))
            rows.clear()

    for line in source.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('|'):
            cells = [part.strip() for part in line[1:-1].split('|')]
            if not all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells):
                rows.append(cells)
            continue
        flush()
        if not line:
            continue
        if line == '<!-- page -->':
            story.append(PageBreak())
        elif line.startswith('<!-- diagram:'):
            story.extend((diagram(line.removeprefix('<!-- diagram:').removesuffix(' -->')), Spacer(1, 10)))
        elif line.startswith('# '):
            story.extend((Spacer(1, 53), paragraph(line[2:], styles['cover'])))
        elif line.startswith('## '):
            story.append(paragraph(line[3:], styles['title']))
        elif line.startswith('### '):
            story.append(paragraph(line[4:], styles['section']))
        elif re.match(r'^(?:- |[0-9]+\. )', line):
            story.append(paragraph('• ' + line[2:] if line.startswith('- ') else line, styles['list']))
        else:
            story.append(paragraph(line, styles['body']))
    flush()

    def frame(canvas, current):
        canvas.setFillColor(PINE)
        canvas.rect(0, PAGE_HEIGHT - 45, PAGE_WIDTH, 45, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('QingBody', 10)
        canvas.drawString(MARGIN, PAGE_HEIGHT - 28, '青栈  /  AI Interviewer')
        canvas.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 28, '传智杯 · Web 前端赛道')
        canvas.setStrokeColor(GRID)
        canvas.line(MARGIN, 38, PAGE_WIDTH - MARGIN, 38)
        canvas.setFillColor(MUTED)
        canvas.setFont('QingBody', 9)
        canvas.drawString(MARGIN, 23, '技术文档 · 2026.11')
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 23, f'{current.page:02}')

    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/参赛技术文档.md')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/deliveries/青栈-传智杯技术文档.pdf')
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/msyh.ttc'),
                        help='Path to a Chinese TrueType font (TTF or TTC).')
    args = parser.parse_args()
    render(args.source, args.output, args.font)
