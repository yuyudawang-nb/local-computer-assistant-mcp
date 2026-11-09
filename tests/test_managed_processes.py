import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from managed_processes import ManagedProcessManager


def _wait_for(manager, job_id, predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = manager.status(job_id)
        if predicate(state):
            return state
        time.sleep(0.05)
    raise AssertionError(f"Timed out: {manager.status(job_id)}")


def test_job_survives_manager_restart_and_can_be_stopped(tmp_path):
    manager = ManagedProcessManager(tmp_path)
    job = manager.start([sys.executable, "-u", "-c",
                         "import time; print('ready', flush=True); time.sleep(60)"], tmp_path)
    job_id = job["job_id"]
    try:
        fresh_manager = ManagedProcessManager(tmp_path)
        _wait_for(fresh_manager, job_id, lambda s: s["state"] == "running")
        assert any(s["job_id"] == job_id for s in fresh_manager.list())
        end = time.monotonic() + 5
        while "ready" not in fresh_manager.read_log(job_id)["output"] and time.monotonic() < end:
            time.sleep(0.05)
        assert "ready" in fresh_manager.read_log(job_id)["output"]
        stopped = fresh_manager.stop(job_id)
        assert stopped["state"] == "stopped"
        assert stopped["exit_code"] is not None
        assert "ready" in manager.read_log(job_id)["output"]
    finally:
        manager.stop(job_id)


def test_natural_exit_persists_and_unknown_job_rejected(tmp_path):
    manager = ManagedProcessManager(tmp_path)
    job = manager.start([sys.executable, "-u", "-c", "print('done')"], tmp_path)
    state = _wait_for(ManagedProcessManager(tmp_path), job["job_id"],
                      lambda s: s["state"] == "exited")
    assert state["exit_code"] == 0
    assert "done" in manager.read_log(job["job_id"])["output"]
    with pytest.raises(ValueError):
        manager.stop("../../etc/passwd")
    with pytest.raises(ValueError):
        manager.status("0" * 16)


def test_stop_kills_descendant_after_launcher_exits(tmp_path):
    manager = ManagedProcessManager(tmp_path)
    script = ("import subprocess,sys; "
              "subprocess.Popen([sys.executable,'-u','-c',"
              "'import time; print(\"descendant_ready\",flush=True); time.sleep(60)'],"
              "stdout=sys.stdout,stderr=sys.stderr); print('launcher_exited',flush=True)")
    job = manager.start([sys.executable, "-u", "-c", script], tmp_path)
    job_id = job["job_id"]
    try:
        end = time.monotonic() + 5
        while "descendant_ready" not in manager.read_log(job_id)["output"] and time.monotonic() < end:
            time.sleep(0.05)
        assert "descendant_ready" in manager.read_log(job_id)["output"]
        assert manager.status(job_id)["state"] == "running"
        stopped = manager.stop(job_id)
        assert stopped["state"] == "stopped"
    finally:
        manager.stop(job_id)
