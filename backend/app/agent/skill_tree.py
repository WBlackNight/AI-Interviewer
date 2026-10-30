"""技能树（知识图谱 MVP 形态）。

从 YAML 加载岗位技能树，使用完整路径在内存中索引；当前没有数据库存储链路。
追问引擎沿树下钻，报告服务用子节点生成复习建议。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import yaml


@dataclass
class SkillNode:
    name: str
    parent: "SkillNode | None" = None
    children: list["SkillNode"] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.parent.id}/{self.name}" if self.parent else self.name

    @property
    def depth(self) -> int:
        d = 0
        node: SkillNode | None = self
        while node and node.parent:
            d += 1
            node = node.parent
        return d

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class SkillTree:
    position: str
    display_name: str
    roots: list[SkillNode]
    _index: dict[str, SkillNode] = field(default_factory=dict, repr=False)
    question_routes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for root in self.roots:
            for node in root.walk():
                if node.id in self._index:
                    raise ValueError(f"重复技能路径: {node.id}")
                self._index[node.id] = node
        if not isinstance(self.question_routes, dict) or len(self.question_routes) > 10000:
            raise ValueError("invalid_question_routes")
        for question_id, path in self.question_routes.items():
            if (not isinstance(question_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', question_id)
                    or not isinstance(path, str) or path not in self._index):
                raise ValueError("invalid_question_route")

    def find(self, name: str) -> SkillNode | None:
        if name in self._index:
            return self._index[name]
        matches = [n for n in self._index.values() if n.name == name]
        return matches[0] if len(matches) == 1 else None

    def children_of(self, name: str) -> list[SkillNode]:
        node = self.find(name)
        return list(node.children) if node else []

    def root_names(self) -> list[str]:
        return [r.name for r in self.roots]

    def all_names(self) -> list[str]:
        return list(self._index.keys())


def load_skill_tree(skill_tree_dir: Path) -> dict[str, SkillTree]:
    """加载目录下全部 <position>.yaml，返回 {position: SkillTree}。"""
    trees: dict[str, SkillTree] = {}
    for path in sorted(skill_tree_dir.glob("*.yaml")) + sorted(
        skill_tree_dir.glob("*.yml")
    ):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        def build(name: str, parent: SkillNode | None, children_raw: list) -> SkillNode:
            node = SkillNode(name=name, parent=parent)
            for child in children_raw or []:
                if isinstance(child, str):
                    node.children.append(SkillNode(name=child, parent=node))
                elif isinstance(child, dict) and child.get("name"):
                    node.children.append(
                        build(str(child["name"]), node, child.get("children"))
                    )
            return node

        roots = [
            build(item["name"], None, item.get("children"))
            for item in raw.get("roots", [])
        ]
        trees[str(raw.get("position", path.stem))] = SkillTree(
            position=str(raw.get("position", path.stem)),
            display_name=str(raw.get("display_name", path.stem)),
            roots=roots,
            question_routes=raw.get("question_routes", {}),
        )
    return trees
