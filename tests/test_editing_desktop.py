"""Behavioral checks for patch boundaries, Git review, and safe desktop validation."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop
import editing


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "module.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "module.py"], check=True)
    return tmp_path


def test_patch_changes_workspace_file_and_git_review_reports_diff(tmp_path):
    root = _repo(tmp_path)
    patch = ("diff --git a/module.py b/module.py\n"
             "--- a/module.py\n+++ b/module.py\n"
             "@@ -1 +1 @@\n-value = 1\n+value = 2\n")
    result = editing.apply_patch(root, patch)
    assert result["applied"] and result["paths"] == ["module.py"]
    assert (root / "module.py").read_text() == "value = 2\n"
    review = editing.git_review(root)
    assert "+value = 2" in review["unstaged_diff"]
    assert "module.py" in review["status"]
    assert not editing.apply_patch(root, patch)["applied"]


def test_patch_rejects_escape_symlink_and_binary(tmp_path):
    root = _repo(tmp_path / "repo")
    (root / "escape.py").symlink_to(tmp_path / "outside.py")
    for path in ("../outside.py", "/tmp/outside.py", ".git/config", "escape.py"):
        patch = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
        with pytest.raises(ValueError):
            editing.apply_patch(root, patch)
    with pytest.raises(ValueError):
        editing.apply_patch(root, "diff --git a/module.py b/module.py\nGIT binary patch\n")
    with pytest.raises(ValueError):
        editing.git_review(root, "../outside.py")


def test_desktop_validates_before_input(monkeypatch):
    class FakeScreen:
        width_in_pixels = 100
        height_in_pixels = 50

    class FakeDisplay:
        def screen(self):
            return FakeScreen()

        def close(self):
            pass

    monkeypatch.setattr(desktop, "_display", FakeDisplay)
    with pytest.raises(ValueError):
        desktop.move_mouse(100, 0)
    with pytest.raises(ValueError):
        desktop.click_mouse(0, 0, button="unknown")
    with pytest.raises(ValueError):
        desktop.scroll_mouse(0, 0, steps=21)
    with pytest.raises(ValueError):
        desktop.type_text("x" * 4001)


def test_hotkey_releases_keys_in_reverse_order(monkeypatch):
    events = []

    class FakeDisplay:
        def keysym_to_keycode(self, sym):
            return sym % 200 + 1

        def sync(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(desktop, "_display", FakeDisplay)
    monkeypatch.setattr(desktop.xtest, "fake_input",
                        lambda conn, event, code, **kwargs: events.append((event, code)))
    result = desktop.hotkey(["ctrl", "s"])
    assert result["keys"] == ["ctrl", "s"]
    assert [event for event, _ in events] == [desktop.X.KeyPress, desktop.X.KeyPress,
                                               desktop.X.KeyRelease, desktop.X.KeyRelease]
    assert events[0][1] == events[-1][1] and events[1][1] == events[2][1]


def test_type_text_uses_clipboard_and_paste(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stderr = b""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs["input"]))
        return Result()

    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    monkeypatch.setattr(desktop, "hotkey", lambda keys: calls.append(keys))
    assert desktop.type_text("中文") == {"characters": 2, "clipboard_replaced": True}
    assert calls == [(["xclip", "-selection", "clipboard", "-i"], "中文".encode()),
                     ["ctrl", "v"]]
