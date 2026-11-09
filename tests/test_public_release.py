from pathlib import Path
import subprocess
import sys


def test_release_allowlist_and_secrets():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_public_release.py")],
        cwd=root, text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
