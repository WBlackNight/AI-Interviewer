"""仅接收一个 PDF 和可选 name 字段的有界 multipart 解析。

不用 UploadFile 的磁盘暂存：文件内容仅存在受限 bytearray 中。
无论是否声明 Content-Length，均对实际接收字节、表单字段、头部设上限。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header


@dataclass
class Upload:
    max_bytes: int
    data: bytearray = field(default_factory=bytearray)
    name: bytearray = field(default_factory=bytearray)
    seen: set[bytes] = field(default_factory=set)
    headers: dict[bytes, bytes] = field(default_factory=dict)
    header_key: bytearray = field(default_factory=bytearray)
    header_value: bytearray = field(default_factory=bytearray)
    header_bytes: int = 0
    current: bytes = b""
    ended: bool = False

    def on_part_begin(self):
        self.headers.clear()
        self.header_bytes = 0
        self.current = b""

    def _header(self, target, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 4096:
            raise HTTPException(413, "上传表单头部过大")
        target.extend(data[start:end])

    def on_header_field(self, data, start, end):
        self._header(self.header_key, data, start, end)

    def on_header_value(self, data, start, end):
        self._header(self.header_value, data, start, end)

    def on_header_end(self):
        key = bytes(self.header_key).lower()
        if key in self.headers:
            raise HTTPException(422, "上传表单包含重复头部")
        self.headers[key] = bytes(self.header_value)
        self.header_key.clear()
        self.header_value.clear()

    def on_headers_finished(self):
        disposition, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        name = options.get(b"name", b"")
        if disposition != b"form-data" or name not in (b"file", b"name") or name in self.seen:
            raise HTTPException(422, "请上传一个 file 文件和可选的 name 字段")
        if name == b"file":
            filename = options.get(b"filename", b"")
            media_type, _ = parse_options_header(self.headers.get(b"content-type", b""))
            if not filename.lower().endswith(b".pdf") or media_type != b"application/pdf":
                raise HTTPException(415, "仅支持 application/pdf 类型的 .pdf 文件，请粘贴其他格式的文本")
        elif b"filename" in options:
            raise HTTPException(422, "name 必须为文本字段")
        self.seen.add(name)
        self.current = name

    def on_part_data(self, data, start, end):
        target = self.data if self.current == b"file" else self.name
        limit = self.max_bytes if self.current == b"file" else 256
        if len(target) + end - start > limit:
            raise HTTPException(413, "PDF 文件或姓名字段超过大小限制")
        target.extend(data[start:end])

    def on_end(self):
        self.ended = True


async def read_pdf_upload(request: Request, *, max_bytes: int, timeout_seconds: float) -> Upload:
    media_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary", b"")
    if media_type != b"multipart/form-data" or not boundary or len(boundary) > 200:
        raise HTTPException(415, "请使用 multipart/form-data 上传 PDF")
    # 额外预算只供边界、头部、name 使用；实际文件另行严格限制。
    max_body = max_bytes + 16384
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError:
        raise HTTPException(422, "无效的上传长度") from None
    if declared < 0 or declared > max_body:
        raise HTTPException(413, "上传内容超过大小限制")
    upload = Upload(max_bytes)
    callbacks = {key: getattr(upload, key) for key in (
        "on_part_begin", "on_header_field", "on_header_value", "on_header_end",
        "on_headers_finished", "on_part_data", "on_end",
    )}
    parser = MultipartParser(boundary, callbacks)
    total = 0
    try:
        async with asyncio.timeout(timeout_seconds):
            async for chunk in request.stream():
                total += len(chunk)
                if total > max_body:
                    raise HTTPException(413, "上传内容超过大小限制")
                parser.write(chunk)
            parser.finalize()
    except TimeoutError:
        raise HTTPException(408, "上传超时，请重试或粘贴简历文本") from None
    except HTTPException:
        raise
    except MultipartParseError as exc:
        # 固定依赖版本的内置头部限制可能早于回调触发；只匹配常量，
        # 不把第三方异常正文（可能含上传内容）返给客户端。
        if str(exc) in ("Maximum header size exceeded", "Maximum header count exceeded"):
            raise HTTPException(413, "上传表单头部过大或过多") from None
        raise HTTPException(422, "上传表单损坏，请重新选择 PDF") from None
    except Exception:
        raise HTTPException(422, "上传表单损坏，请重新选择 PDF") from None
    if not upload.ended or b"file" not in upload.seen or not upload.data:
        raise HTTPException(422, "缺少完整的 PDF 文件，请重新上传或粘贴简历文本")
    return upload
