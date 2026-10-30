"""离线题库审校：严格结构、题号/题干重复与来源登记检查，不执行题目或访问网络。"""
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.domain import Question
from app.rag.vector_index import corpus_version

Text64 = Annotated[str, Field(strict=True, min_length=1, max_length=64)]


class SourceReference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(strict=True, min_length=1, max_length=200)
    url: str = Field(strict=True, max_length=2048)
    checked_on: date

    @field_validator('url')
    @classmethod
    def safe_link(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
            raise ValueError('只接受无凭据的HTTPS资料链接')
        return value


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Text64
    label: str = Field(strict=True, min_length=1, max_length=200)
    origin: Literal['self_authored', 'licensed']
    review_state: Literal['unreviewed', 'reference_checked']
    references: list[SourceReference] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def reference_evidence(self):
        if self.review_state == 'reference_checked' and not self.references:
            raise ValueError('资料核对状态须附参考资料')
        return self


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format_version: Literal[1]
    sources: list[SourceRecord] = Field(max_length=1000)

    @model_validator(mode='after')
    def unique_sources(self):
        if len({row.id for row in self.sources}) != len(self.sources):
            raise ValueError('来源ID重复')
        return self


def load_registry(path: Path):
    try:
        if path.stat().st_size > 256 * 1024:
            return {}, 'invalid'
        registry = SourceRegistry.model_validate_json(path.read_bytes())
        return {row.id: row.model_dump(mode='json') for row in registry.sources}, 'available'
    except FileNotFoundError:
        return {}, 'missing'
    except (OSError, ValueError):
        return {}, 'invalid'


class Anchor(BaseModel):
    model_config = ConfigDict(extra='forbid')
    point: str = Field(strict=True, min_length=1, max_length=500)
    keywords: list[Annotated[str, Field(strict=True, min_length=1, max_length=128)]] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.point.strip() or any(not word.strip() for word in self.keywords):
            raise ValueError('锚点及关键词不能为空白')
        return self


class ExampleCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input: str = Field(strict=True, max_length=65536)
    expected: str = Field(strict=True, max_length=65536)

    @model_validator(mode='after')
    def byte_limit(self):
        if len(self.input.encode('utf-8')) > 65536 or len(self.expected.encode('utf-8')) > 65536:
            raise ValueError('用例最多64KiB UTF-8')
        return self


class AuditedQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(strict=True, min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    position: Text64
    theme: Text64
    difficulty: Literal['easy', 'mid', 'hard']
    content: str = Field(strict=True, min_length=1, max_length=20000)
    answer_points: list[Anchor] = Field(min_length=1, max_length=12)
    is_coding: bool = Field(default=False, strict=True)
    testcases: list[ExampleCase] = Field(default_factory=list, max_length=12)
    source: Text64 = 'builtin'

    @model_validator(mode='after')
    def consistent(self):
        if any(not value.strip() for value in (self.position, self.theme, self.content, self.source)):
            raise ValueError('字段不能为空白')
        if self.is_coding != bool(self.testcases):
            raise ValueError('编码题必须有用例，知识题不可携带用例')
        if len({point.point.strip().casefold() for point in self.answer_points}) != len(self.answer_points):
            raise ValueError('评分锚点重复')
        return self


def audit_directories(bank_dir, trees, registry_path, candidates_dir=None):
    registry, registry_state = load_registry(Path(registry_path))
    errors, warnings, fingerprints, accepted = [], [], [], {'active': [], 'candidate': []}
    seen_ids, seen_text, records = set(), set(), 0
    if registry_state != 'available':
        errors.append({'file': 'source_registry.json', 'line': 0, 'code': 'SOURCE_REGISTRY_UNAVAILABLE'})
    for group, directory in [('active', bank_dir), ('candidate', candidates_dir)]:
        if records > 10000:
            break
        if directory is None:
            continue
        paths = sorted(Path(directory).glob('*.jsonl'))
        group_start = records
        if not paths:
            errors.append({'file': group, 'line': 0, 'code': 'NO_QUESTION_FILES'})
        for path in paths:
            if records > 10000:
                break
            name = group + '/' + path.name
            try:
                if path.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError('size')
                raw = path.read_bytes()
                lines = raw.decode('utf-8').splitlines()
            except (OSError, ValueError):
                errors.append({'file': name, 'line': 0, 'code': 'FILE_UNREADABLE_OR_TOO_LARGE'})
                continue
            fingerprints.append({'file': name, 'sha256': hashlib.sha256(raw).hexdigest()})
            for number, line in enumerate(lines, 1):
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                records += 1
                if records > 10000:
                    errors.append({'file': name, 'line': number, 'code': 'RECORD_LIMIT'})
                    break
                try:
                    row = AuditedQuestion.model_validate_json(line)
                except (ValidationError, ValueError):
                    errors.append({'file': name, 'line': number, 'code': 'INVALID_QUESTION_SCHEMA'})
                    continue
                codes = []
                if row.id in seen_ids: codes.append('DUPLICATE_ID')
                seen_ids.add(row.id)
                key = (row.position, ''.join(row.content.split()).casefold())
                if key in seen_text: codes.append('DUPLICATE_CONTENT')
                seen_text.add(key)
                if row.position not in trees: codes.append('UNKNOWN_POSITION')
                elif row.theme not in trees[row.position].root_names(): codes.append('UNKNOWN_ROOT_THEME')
                if row.source not in registry: codes.append('UNREGISTERED_SOURCE')
                if codes:
                    errors.extend({'file': name, 'line': number, 'code': code} for code in codes)
                    continue
                if registry[row.source]['review_state'] == 'unreviewed':
                    warnings.append({'file': name, 'line': number, 'code': 'SOURCE_NOT_REFERENCE_CHECKED'})
                accepted[group].append(Question.from_dict(row.model_dump()))
        if paths and records == group_start:
            errors.append({'file': group, 'line': 0, 'code': 'NO_QUESTION_RECORDS'})
    by_id = {q.id: q for group in accepted.values() for q in group}
    for position, tree in trees.items():
        for question_id, path in tree.question_routes.items():
            question = by_id.get(question_id)
            code = ('UNKNOWN_ROUTE_QUESTION' if question is None else
                    'QUESTION_ROUTE_SCOPE_MISMATCH' if question.position != position or not (
                        path == question.theme or path.startswith(question.theme + '/')) else None)
            if code:
                errors.append({'file': 'skill_tree/' + position, 'line': 0, 'code': code})
    return {'result': 'passed' if not errors else 'failed', 'scope': 'structure_and_source_registration_only',
            'expert_review_verified': False, 'activated': False, 'external_model_calls': 0,
            'active_count': len(accepted['active']), 'candidate_count': len(accepted['candidate']),
            'active_corpus_sha256': corpus_version(accepted['active']),
            'combined_corpus_sha256': corpus_version(accepted['active'] + accepted['candidate']),
            'files': fingerprints, 'errors': errors, 'warnings': warnings}
