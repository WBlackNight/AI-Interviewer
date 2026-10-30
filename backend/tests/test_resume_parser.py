"""简历解析测试。"""
from __future__ import annotations

from app.rag.resume_parser import parse_resume_text

SAMPLE = """教育经历
某某大学 计算机科学与技术 本科

专业技能
Java、Spring Boot、MySQL、Redis、并发编程

项目经历
电商秒杀系统：负责库存超卖防护与缓存设计
在线评测平台：负责判题沙箱
"""


def test_skills_extracted():
    data = parse_resume_text(SAMPLE)
    assert "Java" in data.skills
    assert "MySQL" in data.skills
    assert "Redis" in data.skills


def test_projects_extracted():
    data = parse_resume_text(SAMPLE)
    assert any("秒杀" in p for p in data.projects)


def test_empty_text_is_safe():
    data = parse_resume_text("")
    assert data.skills == [] and data.projects == []
