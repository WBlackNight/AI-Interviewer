"""有界 PDF 文本提取。原文件仅在内存/进程管道中传递，不写入文件系统。

解析放在可终止的 spawn 进程中；超时不会留下继续解析的线程。
大小、页数和输出限制不是操作系统级内存隔离，生产部署仍需容器配额。
"""
from __future__ import annotations

import io
import multiprocessing
import threading
import time


class PDFError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


ERRORS = {
    "invalid_pdf": (422, "文件不是有效的 PDF 或已损坏，请粘贴简历文本"),
    "encrypted_pdf": (422, "不支持加密 PDF，请使用未加密文件或粘贴简历文本"),
    "empty_pdf": (422, "PDF 没有可提取文本（可能为扫描件），请粘贴简历文本；暂不支持 OCR"),
    "too_many_pages": (413, "PDF 页数超过限制，请精简文件或粘贴简历文本"),
    "text_too_long": (413, "PDF 提取文本超过限制，请精简文件或粘贴简历文本"),
    "pdf_timeout": (408, "PDF 解析超时，请使用更简单的文件或粘贴简历文本"),
    "pdf_busy": (429, "PDF 解析繁忙，请稍后重试或粘贴简历文本"),
    "pdf_unavailable": (503, "PDF 解析暂不可用，请粘贴简历文本"),
}

# 每个应用进程最多两个解析子进程。无排队，避免请求堆积。
_slots = threading.BoundedSemaphore(2)


def _extract(data: bytes, max_pages: int, max_chars: int) -> str:
    from pypdf import PdfReader

    if not data.startswith(b"%PDF-"):
        raise PDFError("invalid_pdf")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        raise PDFError("encrypted_pdf")
    if len(reader.pages) > max_pages:
        raise PDFError("too_many_pages")
    parts: list[str] = []
    length = 0
    for page in reader.pages:
        text = (page.extract_text() or "").replace("\x00", "")
        length += len(text) + (1 if parts else 0)
        if length > max_chars:
            raise PDFError("text_too_long")
        parts.append(text)
    result = "\n".join(parts).strip()
    if not result:
        raise PDFError("empty_pdf")
    return result


def _worker(connection, data: bytes, max_pages: int, max_chars: int) -> None:
    # pypdf 的警告可能含文档内容/对象名，不能进入应用日志或继承的 stderr。
    import logging
    logging.disable(logging.CRITICAL)
    try:
        connection.send(("ok", _extract(data, max_pages, max_chars)))
    except PDFError as exc:
        connection.send(("error", exc.code))
    except Exception:
        connection.send(("error", "invalid_pdf"))
    finally:
        connection.close()


def extract_pdf_text(data: bytes, *, max_pages: int, max_chars: int,
                     timeout_seconds: float) -> str:
    if not data.startswith(b"%PDF-"):
        raise PDFError("invalid_pdf")
    if not _slots.acquire(blocking=False):
        raise PDFError("pdf_busy")
    parent = child = process = None
    started = False
    deadline = time.monotonic() + timeout_seconds
    try:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_worker, args=(child, data, max_pages, max_chars),
                                  daemon=True, name="resume-pdf-parser")
        process.start()
        started = True
        child.close()
        if not parent.poll(max(0, deadline - time.monotonic())):
            raise PDFError("pdf_timeout")
        try:
            status, payload = parent.recv()
        except (EOFError, OSError):
            raise PDFError("pdf_unavailable") from None
        if status != "ok":
            raise PDFError(payload if payload in ERRORS else "invalid_pdf")
        return payload
    except PDFError:
        raise
    except Exception:
        raise PDFError("pdf_unavailable") from None
    finally:
        if parent is not None:
            parent.close()
        if child is not None:
            child.close()
        if started:
            process.join(timeout=0.2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        _slots.release()
