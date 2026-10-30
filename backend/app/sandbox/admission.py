"""跨客户端共享、FIFO有界等待的进程级判题准入。不是跨worker配额。"""
import threading
import time
from collections import deque
from contextlib import contextmanager


class AdmissionError(RuntimeError):
    pass


class Admission:
    def __init__(self, limit=2, max_waiters=8):
        self.condition = threading.Condition()
        self.limit, self.max_waiters = limit, max_waiters
        self.active, self.waiters = 0, deque()

    def configure(self, limit, max_waiters):
        if limit < 1 or max_waiters < 0:
            raise ValueError("invalid_admission_limits")
        with self.condition:
            self.limit, self.max_waiters = limit, max_waiters
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return dict(scope="process", limit=self.limit, active=self.active,
                        max_waiters=self.max_waiters, waiting=len(self.waiters))

    @contextmanager
    def slot(self, timeout):
        deadline = time.monotonic() + timeout
        ticket = object()
        with self.condition:
            if self.active >= self.limit or self.waiters:
                if len(self.waiters) >= self.max_waiters:
                    raise AdmissionError("queue_full")
                self.waiters.append(ticket)
                try:
                    while self.active >= self.limit or self.waiters[0] is not ticket:
                        remaining = deadline-time.monotonic()
                        if remaining <= 0:
                            raise AdmissionError("queue_timeout")
                        self.condition.wait(remaining)
                    self.waiters.popleft()
                except BaseException:
                    self.waiters.remove(ticket)
                    self.condition.notify_all()
                    raise
            self.active += 1
        try:
            yield
        finally:
            with self.condition:
                self.active -= 1
                self.condition.notify_all()


admission = Admission()
