import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import providers
import server


def test_private_urls_rejected_without_network():
    for url in ("http://example.com", "https://localhost/", "https://127.0.0.1/",
                "https://192.0.2.1/", "https://169.254.169.254/", "https://example.com:8443/"):
        with pytest.raises(ValueError):
            providers.public_https_url(url, resolve=False)


def test_root_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        server.within_root("../outside")
    assert server.within_root("a.txt") == tmp_path / "a.txt"


def test_command_execution_is_explicit_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setattr(server, "ALLOW_EXEC", False)
    with pytest.raises(PermissionError):
        server.limited_run(["python", "-c", "print(1)"])
    monkeypatch.setattr(server, "ALLOW_EXEC", True)
    result = server.limited_run([sys.executable, "-c", "print('ok')"], cwd=".")
    assert result["exit_code"] == 0 and result["stdout"].strip() == "ok"
    assert server.limited_run([sys.executable, "-c", "import time; time.sleep(3)"], timeout=1)["timed_out"]


def test_search_categories_and_plan_do_not_invent_results(monkeypatch):
    monkeypatch.setitem(server.SEARCHERS, "models", lambda query, limit: [
        providers.item("models", "test", "model x", "https://example.com/model-x", "model card")])
    result = server.search_topic_impl("model search", ["models"], 2)
    assert len(result["categories"]["models"]) == 1
    plan = server.plan_impl(result)
    assert "https://example.com/model-x" in plan["markdown"]
    assert "没有匹配条目" in plan["markdown"]
    with pytest.raises(ValueError):
        server.search_topic_impl("model", ["unknown"])


def test_read_file_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "ROOT", tmp_path)
    (tmp_path / "hello.txt").write_text("abcdef", encoding="utf-8")
    result = server.read_file("hello.txt", max_chars=3)
    assert result["content"] == "abc" and result["truncated"]


def test_process_session_stream_and_terminate(tmp_path):
    from processes import ProcessManager
    import time

    mgr = ProcessManager()
    info = mgr.start([sys.executable, "-u", "-c",
                      "import time; print('ready', flush=True); time.sleep(10)"], tmp_path, 15)
    session = mgr.get(info["session_id"])
    for _ in range(20):
        data = session.read()
        if "ready" in data["output"]:
            break
        time.sleep(0.05)
    assert "ready" in data["output"] and data["running"]
    assert session.read(data["next_offset"])["output"] == ""
    session.stop()
    assert not session.read()["running"]
