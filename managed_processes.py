"""Persistent, non-interactive local jobs supervised outside the MCP lifetime."""

from __future__ import annotations

import fcntl
import json
import os
import re
import select
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOB_ID = re.compile(r"^[0-9a-f]{16}$")
MAX_LOG_BYTES = 5_000_000
MAX_JOBS = 16


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _proc_start_ticks(pid: int) -> int | None:
    try:
        if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
            return None
        data = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if data[0] == "Z":
            return None
        return int(data[19])
    except (OSError, IndexError, ValueError):
        return None


def _same_process(pid: int | None, ticks: int | None) -> bool:
    return bool(pid and ticks and _proc_start_ticks(int(pid)) == int(ticks))


def _append_log(jobdir: Path, chunk: bytes) -> None:
    path = jobdir / "output.log"
    if path.exists() and path.stat().st_size + len(chunk) > MAX_LOG_BYTES:
        os.replace(path, jobdir / "output.log.1")
    with path.open("ab") as out:
        out.write(chunk)


def _owned_group_exists(pgid: int) -> bool:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] != "Z" and int(fields[2]) == pgid:
                return True
        except (OSError, IndexError, ValueError):
            continue
    return False


def _terminate_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None and not _owned_group_exists(proc.pid):
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    end = time.monotonic() + 5
    while _owned_group_exists(proc.pid) and time.monotonic() < end:
        time.sleep(0.1)
    if _owned_group_exists(proc.pid):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()


def _worker(jobdir: Path) -> None:
    spec = json.loads((jobdir / "spec.json").read_text(encoding="utf-8"))
    state_path = jobdir / "status.json"
    state = {"job_id": jobdir.name, "command": Path(spec["argv"][0]).name,
             "cwd": spec["cwd"], "created_at": spec["created_at"],
             "supervisor_pid": os.getpid(), "supervisor_start_ticks": _proc_start_ticks(os.getpid()),
             "state": "starting", "exit_code": None, "finished_at": None}
    _write_json(state_path, state)
    requested_stop = False

    def on_signal(_signum, _frame):
        nonlocal requested_stop
        requested_stop = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        proc = subprocess.Popen(spec["argv"], cwd=spec["cwd"], shell=False,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True, bufsize=0)
    except Exception as exc:
        _append_log(jobdir, (f"Failed to start: {type(exc).__name__}: {exc}\n").encode())
        state.update(state="failed", finished_at=_now(), error=str(exc)[:500])
        _write_json(state_path, state)
        return
    state.update(state="running", child_pid=proc.pid,
                 child_start_ticks=_proc_start_ticks(proc.pid))
    _write_json(state_path, state)
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    try:
        while True:
            if requested_stop or (jobdir / "stop.request").exists():
                requested_stop = True
                state["state"] = "stopping"
                _write_json(state_path, state)
                _terminate_group(proc)
            readable, _, _ = select.select([fd], [], [], 0.2)
            if readable:
                chunk = os.read(fd, 65536)
                if chunk:
                    _append_log(jobdir, chunk)
                else:
                    break
        code = proc.wait()
        state.update(state="stopped" if requested_stop else "exited",
                     exit_code=code, finished_at=_now())
        _write_json(state_path, state)
    finally:
        if proc.poll() is None:
            _terminate_group(proc)
        proc.stdout.close()


class ManagedProcessManager:
    def __init__(self, state_directory: Path):
        self.directory = state_directory / "managed_processes"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)

    def _jobdir(self, job_id: str) -> Path:
        if not JOB_ID.fullmatch(job_id):
            raise ValueError("Invalid managed process ID")
        path = self.directory / job_id
        if not path.is_dir() or path.is_symlink():
            raise ValueError("Unknown managed process ID")
        return path

    def status(self, job_id: str) -> dict:
        jobdir = self._jobdir(job_id)
        path = jobdir / "status.json"
        if not path.exists():
            spec = json.loads((jobdir / "spec.json").read_text())
            return {"job_id": job_id, "command": Path(spec["argv"][0]).name,
                    "cwd": spec["cwd"], "created_at": spec["created_at"],
                    "state": "starting" if time.time() - (jobdir / "spec.json").stat().st_mtime < 10 else "lost",
                    "exit_code": None}
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["state"] in {"starting", "running", "stopping"} and not _same_process(
                state.get("supervisor_pid"), state.get("supervisor_start_ticks")):
            state["state"] = "orphaned" if _same_process(
                state.get("child_pid"), state.get("child_start_ticks")) else "lost"
        return state

    def list(self, limit: int = 50) -> list[dict]:
        jobs = sorted((p.name for p in self.directory.iterdir()
                       if p.is_dir() and not p.is_symlink() and JOB_ID.fullmatch(p.name)), reverse=True)
        results = [self.status(job_id) for job_id in jobs]
        results.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return results[:max(1, min(int(limit), 1000))]

    def start(self, argv: list[str], cwd: Path) -> dict:
        if not argv or len(argv) > 40 or any(not isinstance(x, str) or not x or len(x) > 2048 for x in argv):
            raise ValueError("Provide a short argv array of strings")
        if not cwd.is_dir():
            raise ValueError("Working directory does not exist")
        lockpath = self.directory / ".lock"
        with lockpath.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if sum(item["state"] in {"starting", "running", "stopping", "orphaned"}
                   for item in self.list(1000)) >= MAX_JOBS:
                raise ValueError(f"Maximum of {MAX_JOBS} active managed processes")
            job_id = uuid.uuid4().hex[:16]
            jobdir = self.directory / job_id
            jobdir.mkdir(mode=0o700)
            _write_json(jobdir / "spec.json", {"argv": argv, "cwd": str(cwd), "created_at": _now()})
            with (jobdir / "output.log").open("ab"):
                pass
            (jobdir / "output.log").chmod(0o600)
            try:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(jobdir)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
            except Exception:
                for path in jobdir.iterdir():
                    path.unlink()
                jobdir.rmdir()
                raise
        for _ in range(40):
            state = self.status(job_id)
            if state["state"] != "starting":
                return state
            time.sleep(0.05)
        return self.status(job_id)

    def read_log(self, job_id: str, max_chars: int = 20_000) -> dict:
        jobdir = self._jobdir(job_id)
        max_chars = max(1, min(int(max_chars), 30_000))
        chunks = []
        for name in ("output.log.1", "output.log"):
            path = jobdir / name
            if path.exists():
                with path.open("rb") as source:
                    source.seek(max(0, path.stat().st_size - max_chars * 4))
                    chunks.append(source.read())
        content = b"".join(chunks).decode("utf-8", errors="replace")
        state = self.status(job_id)
        return {"job_id": job_id, "state": state["state"],
                "exit_code": state.get("exit_code"), "output": content[-max_chars:],
                "truncated": len(content) > max_chars or (jobdir / "output.log.1").exists()}

    def stop(self, job_id: str, wait_s: float = 8) -> dict:
        jobdir = self._jobdir(job_id)
        state = self.status(job_id)
        if state["state"] in {"exited", "stopped", "failed", "lost"}:
            return state
        if state["state"] == "orphaned":
            # Supervisor died unexpectedly. Kill only the recorded process group
            # after checking PID start time and current user identity.
            pid = state["child_pid"]
            try:
                owns_group = _same_process(pid, state.get("child_start_ticks")) and os.getpgid(pid) == pid
            except ProcessLookupError:
                owns_group = False
            if owns_group:
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                end = time.monotonic() + 5
                while _same_process(pid, state.get("child_start_ticks")) and time.monotonic() < end:
                    time.sleep(0.1)
                if _same_process(pid, state.get("child_start_ticks")):
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            state.update(state="stopped", finished_at=_now(), exit_code=None)
            _write_json(jobdir / "status.json", state)
            return state
        (jobdir / "stop.request").touch(mode=0o600, exist_ok=True)
        end = time.monotonic() + max(0, min(float(wait_s), 10))
        while time.monotonic() < end:
            state = self.status(job_id)
            if state["state"] in {"exited", "stopped", "failed", "lost", "orphaned"}:
                return state
            time.sleep(0.1)
        return self.status(job_id)


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--worker":
    _worker(Path(sys.argv[2]))
