"""Bounded in-process sessions for explicit long-running local commands."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path


class ProcessSession:
    def __init__(self, argv: list[str], cwd: Path, max_duration_s: int):
        self.id = uuid.uuid4().hex[:12]
        self.started = time.monotonic()
        self.max_duration_s = max_duration_s
        self.output: deque[tuple[int, str]] = deque()
        self.next_offset = 0
        self.first_offset = 0
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(argv, cwd=cwd, shell=False, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     start_new_session=True, bufsize=0)
        threading.Thread(target=self._drain, daemon=True).start()
        expiry = threading.Timer(max_duration_s, self.stop)
        expiry.daemon = True
        expiry.start()

    def _drain(self):
        assert self.proc.stdout is not None
        while True:
            chunk = os.read(self.proc.stdout.fileno(), 4096)
            if not chunk:
                return
            decoded = chunk.decode("utf-8", errors="replace")
            with self.lock:
                self.output.append((self.next_offset, decoded))
                self.next_offset += len(decoded)
                while self.output and self.next_offset - self.output[0][0] > 100_000:
                    old_start, old_text = self.output.popleft()
                    self.first_offset = old_start + len(old_text)

    def check_expiry(self):
        if self.proc.poll() is None and time.monotonic() - self.started > self.max_duration_s:
            self.stop()

    def read(self, offset: int = 0, max_chars: int = 20_000) -> dict:
        self.check_expiry()
        max_chars = max(1, min(int(max_chars), 30_000))
        with self.lock:
            offset = max(int(offset), self.first_offset)
            text = "".join(s[max(0, offset - start):] for start, s in self.output
                           if start + len(s) > offset)
            text = text[:max_chars]
            next_offset = offset + len(text)
            available_until = self.next_offset
        return {"session_id": self.id, "output": text, "next_offset": next_offset,
                "first_available_offset": self.first_offset, "truncated": next_offset < available_until,
                "running": self.proc.poll() is None, "exit_code": self.proc.poll()}

    def send(self, text: str):
        self.check_expiry()
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise ValueError("Process is not running")
        if len(text) > 4096:
            raise ValueError("Input exceeds 4 KB")
        self.proc.stdin.write(text.encode("utf-8"))
        self.proc.stdin.flush()

    def stop(self):
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except OSError:
                    pass
        return {"session_id": self.id, "exit_code": self.proc.poll()}


class ProcessManager:
    def __init__(self):
        self.sessions: dict[str, ProcessSession] = {}
        self.lock = threading.Lock()
        atexit.register(self.stop_all)

    def start(self, argv: list[str], cwd: Path, max_duration_s: int = 300) -> dict:
        if not argv or len(argv) > 40 or any(not isinstance(x, str) or len(x) > 2048 for x in argv):
            raise ValueError("Provide a short argv array of strings")
        max_duration_s = max(1, min(int(max_duration_s), 600))
        with self.lock:
            for sid, session in list(self.sessions.items()):
                session.check_expiry()
                if session.proc.poll() is not None and time.monotonic() - session.started > 600:
                    del self.sessions[sid]
            if len(self.sessions) >= 8:
                raise ValueError("Maximum of 8 retained process sessions")
            session = ProcessSession(argv, cwd, max_duration_s)
            self.sessions[session.id] = session
        return {"session_id": session.id, "pid": session.proc.pid, "cwd": str(cwd),
                "max_duration_s": max_duration_s}

    def get(self, session_id: str) -> ProcessSession:
        with self.lock:
            if session_id not in self.sessions:
                raise ValueError("Unknown process session")
            return self.sessions[session_id]

    def stop_all(self):
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            session.stop()


manager = ProcessManager()
