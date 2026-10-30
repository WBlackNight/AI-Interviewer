"""Judge0 提交/轮询客户端；基础设施故障不转换为考生零分。"""
from __future__ import annotations

import base64
import json
import time
import httpx
from app.domain import SandboxResult, TestCase
from app.sandbox.admission import admission, AdmissionError
from app.security import sanitize_pii

MAX_CODE_LENGTH = 16 * 1024


class SandboxUnavailable(RuntimeError):
    def __init__(self, code="unavailable", *, retryable=True):
        self.code, self.retryable = code, retryable
        super().__init__(code)


class Judge0Sandbox:
    def __init__(self, base_url: str, *, api_key: str | None = None,
                 language_id: int = 71, timeout: float = 15.0, poll_interval: float = 0.1,
                 queue_timeout: float = 2, max_response_bytes: int = 262144, max_testcases: int = 12):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Auth-Token": api_key} if api_key else {}
        self._language_id = language_id
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._queue_timeout = queue_timeout
        self._max_response_bytes = max_response_bytes
        self._max_testcases = max_testcases

    def request_json(self, client, method, url, *, deadline=None, **kwargs):
        with client.stream(method, url, headers=self._headers, **kwargs) as response:
            if response.status_code == 429:
                raise SandboxUnavailable("rate_limited")
            if 400 <= response.status_code < 500:
                raise SandboxUnavailable("configuration", retryable=False)
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                if deadline is not None and time.monotonic() >= deadline:
                    raise SandboxUnavailable("timeout")
                if len(data) + len(chunk) > self._max_response_bytes:
                    raise SandboxUnavailable("response_too_large")
                data.extend(chunk)
            return json.loads(data)

    def judge(self, code: str, testcases: list[TestCase]) -> SandboxResult:
        if len(code.encode("utf-8")) > MAX_CODE_LENGTH:
            raise ValueError("代码超过16KiB")
        if not testcases:
            raise ValueError("缺少判题用例")
        if len(testcases) > self._max_testcases or any(
                len(c.input.encode()) > 65536 or len(c.expected.encode()) > 65536 for c in testcases):
            raise ValueError("判题用例数量或大小超限")
        if not code.strip():
            return SandboxResult(0, len(testcases), [])
        deadline = time.monotonic() + self._timeout  # 准入等待也消耗总截止时间。
        detail = []
        try:
            with admission.slot(min(self._queue_timeout, self._timeout)), httpx.Client(timeout=self._timeout, trust_env=False) as client:
                for index, case in enumerate(testcases):
                    ok, info = self._run_case(client, code, case, deadline)
                    detail.append({"case": index + 1, "passed": ok, **info})
        except AdmissionError as exc:
            raise SandboxUnavailable(str(exc)) from None
        except httpx.TimeoutException:
            raise SandboxUnavailable("timeout") from None
        except httpx.HTTPError:
            raise SandboxUnavailable("transport") from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SandboxUnavailable("invalid_response") from None
        return SandboxResult(sum(d["passed"] for d in detail), len(testcases), detail)

    def _run_case(self, client, code: str, case: TestCase, deadline: float):
        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise SandboxUnavailable("timeout")
            return seconds

        def encoded(text):
            return base64.b64encode(text.encode()).decode("ascii")

        data = self.request_json(client, "POST", f"{self._base_url}/submissions",
            deadline=deadline,
            params={"wait": "false", "base64_encoded": "true"},
            timeout=remaining(), json={
                "source_code": encoded(code), "language_id": self._language_id,
                "stdin": encoded(case.input), "expected_output": encoded(case.expected),
                "cpu_time_limit": 2, "wall_time_limit": 5, "memory_limit": 256000,
                "max_file_size": 1024, "max_processes_and_or_threads": 20,
                "enable_network": False,
            })
        token = data["token"]
        if not isinstance(token, str) or not 1 <= len(token) <= 128 or not token.isascii() or not token.replace("-", "").isalnum():
            raise SandboxUnavailable("invalid_token")
        while True:
            data = self.request_json(client, "GET", f"{self._base_url}/submissions/{token}",
                deadline=deadline,
                params={"base64_encoded": "true", "fields":"status,stdout"}, timeout=remaining())
            status_id = data["status"]["id"]
            if type(status_id) is not int or status_id not in range(1, 15):
                raise SandboxUnavailable("invalid_status")
            if status_id in (1, 2):
                time.sleep(min(self._poll_interval, remaining()))
                continue
            if status_id in (13, 14):
                raise SandboxUnavailable("internal_error" if status_id == 13 else "execution_format")
            stdout = base64.b64decode(data.get("stdout") or "", validate=True).decode("utf-8", errors="replace")
            return status_id == 3, {"status_id":status_id,
                "status": sanitize_pii(str(data["status"].get("description", status_id)))[:80],
                "stdout": sanitize_pii(stdout)[:200]}
