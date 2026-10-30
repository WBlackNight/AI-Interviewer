"""离线准备与校验成套题库资产；不读取配置、联网或切换运行资产。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from app.agent.skill_tree import load_skill_tree
from app.rag.embeddings import HashEmbedder
from app.rag.question_bank import QuestionBank
from app.rag.vector_index import VectorIndex, build_index, corpus_version
from app.services.question_audit import audit_directories


class ReleaseError(ValueError):
    """固定错误代码，CLI不输出路径、输入数据或底层异常正文。"""


def _files(directory: Path, patterns: tuple[str, ...]) -> list[Path]:
    paths = sorted(path for pattern in patterns for path in directory.glob(pattern))
    if not paths or len(paths) > 32 or any(path.is_symlink() for path in paths):
        raise ReleaseError('invalid_asset_files')
    return paths


def _copy(source: Path, target: Path, limit: int = 10 * 1024 * 1024) -> None:
    if source.is_symlink() or source.stat().st_size > limit:
        raise ReleaseError('invalid_asset_file')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def _audit(stage: Path) -> tuple[dict, QuestionBank]:
    trees = load_skill_tree(stage / 'skill_tree')
    if len(trees) != len(_files(stage / 'skill_tree', ('*.yaml', '*.yml'))):
        raise ReleaseError('duplicate_skill_position')
    result = audit_directories(stage / 'question_bank', trees, stage / 'question_bank/source_registry.json')
    if result['result'] != 'passed':
        raise ReleaseError('asset_audit_failed')
    return result, QuestionBank.load(stage / 'question_bank')


def prepare_release(bank_dir: Path, skill_tree_dir: Path, candidates_dir: Path, output: Path,
                    *, skill_overrides: Path | None = None) -> dict:
    """先在同级临时目录完成两套资产与校验，成功后发布到全新目录。"""
    output = output.resolve()
    inputs = [path.resolve() for path in (bank_dir, skill_tree_dir, candidates_dir)]
    if skill_overrides is not None:
        inputs.append(skill_overrides.resolve())
    if any(output == path or output.is_relative_to(path) or path.is_relative_to(output) for path in inputs):
        raise ReleaseError('output_overlaps_input')
    if output.exists():
        raise ReleaseError('output_already_exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.question-release-', dir=output.parent) as temporary:
        root = Path(temporary).resolve() / 'bundle'
        baseline, candidate = root / 'baseline', root / 'candidate'
        for source in _files(bank_dir, ('*.jsonl',)):
            _copy(source, baseline / 'question_bank' / source.name)
        _copy(bank_dir / 'source_registry.json', baseline / 'question_bank/source_registry.json', 256 * 1024)
        for source in _files(skill_tree_dir, ('*.yaml', '*.yml')):
            _copy(source, baseline / 'skill_tree' / source.name)
        baseline_audit, _ = _audit(baseline)
        shutil.copytree(baseline, candidate)
        if skill_overrides is not None:
            for source in _files(skill_overrides, ('*.yaml', '*.yml')):
                target = candidate / 'skill_tree' / source.name
                if not target.is_file():
                    raise ReleaseError('unknown_skill_override')
                _copy(source, target)
        draft_dir = root / 'drafts'
        for source in _files(candidates_dir, ('*.jsonl',)):
            _copy(source, draft_dir / source.name)
        review = audit_directories(baseline / 'question_bank', load_skill_tree(candidate / 'skill_tree'),
                                   candidate / 'question_bank/source_registry.json', draft_dir)
        if review['result'] != 'passed':
            raise ReleaseError('candidate_audit_failed')
        # 合并已审校的快照，按岗位生成安全文件名，不直接拼接任意岗位路径。
        rows = {}
        for directory in (baseline / 'question_bank', draft_dir):
            for source in _files(directory, ('*.jsonl',)):
                for line in source.read_text(encoding='utf-8').splitlines():
                    if not line.strip() or line.lstrip().startswith('#'):
                        continue
                    row = json.loads(line)
                    position = row['position']
                    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', position):
                        raise ReleaseError('invalid_position_filename')
                    rows.setdefault(position, []).append(row)
        for existing in (candidate / 'question_bank').glob('*.jsonl'):
            existing.unlink()
        for position, questions in rows.items():
            encoded = ''.join(json.dumps(q, ensure_ascii=False, sort_keys=True) + '\n'
                              for q in sorted(questions, key=lambda q: q['id']))
            (candidate / 'question_bank' / (position + '.jsonl')).write_bytes(encoded.encode('utf-8'))
        # 临时草稿仅为校验输入，移动至另一个同级临时路径后由上下文清理。
        draft_dir.rename(Path(temporary) / 'drafts')
        variants = {}
        for name, stage in (('baseline', baseline), ('candidate', candidate)):
            audit, bank = _audit(stage)
            index, _ = build_index(stage / 'retrieval/hash-256.json', bank.questions, HashEmbedder(256))
            variants[name] = {'question_count': len(bank), 'corpus_sha256': corpus_version(bank.questions),
                              'index_id': index.manifest['index_id'], 'warning_count': len(audit['warnings'])}
        if variants['candidate']['question_count'] != baseline_audit['active_count'] + review['candidate_count']:
            raise ReleaseError('merged_count_mismatch')
        manifest = {'format_version': 1, 'activated': False, 'semantic_model': False,
                    'expert_review_verified': False, 'variants': variants,
                    'files': {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sorted(root.rglob('*')) if path.is_file()}}
        (root / 'manifest.json').write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        verify_release(root)
        # 目标不得存在；同一父目录内重命名，避免留下可被误用的半成品目录。
        os.rename(root, output)
    return manifest


def verify_release(root: Path) -> dict:
    """先检查成员与字节摘要，再校验题库、路由、索引和域版本；摘要不是签名。"""
    root = root.resolve()
    manifest_path = root / 'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 256 * 1024:
        raise ReleaseError('invalid_manifest')
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest.get('format_version') != 1 or manifest.get('activated') is not False
            or manifest.get('semantic_model') is not False or manifest.get('expert_review_verified') is not False
            or set(manifest.get('variants', {})) != {'baseline', 'candidate'}):
        raise ReleaseError('invalid_manifest')
    members = manifest.get('files')
    if not isinstance(members, dict) or not 1 <= len(members) <= 64:
        raise ReleaseError('invalid_manifest_members')
    pattern = (r'(baseline|candidate)/(question_bank/([A-Za-z0-9_.-]+\.jsonl|source_registry\.json)'
               r'|skill_tree/[A-Za-z0-9_.-]+\.ya?ml|retrieval/hash-256\.json)')
    for relative, expected in members.items():
        if (not isinstance(relative, str) or not re.fullmatch(pattern, relative)
                or not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)):
            raise ReleaseError('invalid_manifest_member')
        path = root / relative
        if (not path.resolve().is_relative_to(root) or path.is_symlink()
                or any(parent.is_symlink() or parent.is_junction() for parent in path.parents if parent != root)):
            raise ReleaseError('unsafe_member_path')
        if path.stat().st_size > 32 * 1024 * 1024 or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ReleaseError('member_checksum_mismatch')
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
    if actual != set(members) | {'manifest.json'}:
        raise ReleaseError('member_set_mismatch')
    for name in ('baseline', 'candidate'):
        stage = root / name
        audit, bank = _audit(stage)
        index = VectorIndex.load(stage / 'retrieval/hash-256.json', bank.questions, HashEmbedder(256).spec)
        expected = {'question_count': len(bank), 'corpus_sha256': corpus_version(bank.questions),
                    'index_id': index.manifest['index_id'], 'warning_count': len(audit['warnings'])}
        if manifest['variants'][name] != expected:
            raise ReleaseError('variant_manifest_mismatch')
    return manifest
