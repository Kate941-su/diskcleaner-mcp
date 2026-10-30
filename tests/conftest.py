import os
import time
from pathlib import Path

import pytest

from diskclean_mcp.platform_paths import ProtectionRules, current_os, protection_rules

DAY = 86400


def make_symlink(link: Path, target: Path) -> None:
    """Windows では開発者モードか管理者権限がないとリンクを作れないため、その場合はスキップする。"""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as e:
        pytest.skip(f"symlink を作成できない環境: {e}")


def make_file(path: Path, size: int = 10, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)  # スパースファイルなので大きくてもディスクを消費しない
    if age_days:
        ts = time.time() - age_days * DAY
        os.utime(path, (ts, ts))
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path.resolve() / "home" / "user"
    h.mkdir(parents=True)
    return h


@pytest.fixture
def rules(home: Path) -> ProtectionRules:
    return protection_rules(current_os(), home, {})


@pytest.fixture
def tree(home: Path) -> Path:
    """dev キャッシュ・動画・ログが混在するダミーツリー。"""
    root = home / "projects"
    make_file(root / "web" / "package.json")
    make_file(root / "web" / "node_modules" / "lib" / "index.js", 2000)
    make_file(root / "web" / "dist" / "bundle.js", 500)
    make_file(root / "rust" / "Cargo.toml")
    make_file(root / "rust" / "target" / "debug" / "app", 3000)
    make_file(root / "docs" / "build" / "keep.txt", 100)  # マーカーなし → 対象外
    make_file(root / "docs" / "target" / "keep.txt", 100)  # マーカーなし → 対象外
    make_file(root / "py" / "pyproject.toml")
    make_file(root / "py" / ".venv" / "pyvenv.cfg")
    make_file(root / "py" / ".venv" / "lib" / "x.py", 400)
    make_file(root / "py" / "venv" / "notavenv.txt")  # pyvenv.cfg なし → 対象外
    make_file(root / "py" / "src" / "__pycache__" / "m.pyc", 50)
    make_file(root / "media" / "old.mp4", 200 * 1024**2, age_days=200)
    make_file(root / "media" / "recent.mp4", 200 * 1024**2, age_days=1)
    make_file(root / "media" / "small.mov", 1024, age_days=200)
    make_file(root / "logs" / "app.log", 100, age_days=60)
    make_file(root / "logs" / "app.log.1.gz", 100, age_days=60)
    make_file(root / "logs" / "new.log", 100, age_days=1)
    make_file(root / "logs" / "archive.zip", 100, age_days=60)  # ログではない
    make_file(root / "logs" / "catalog.txt", 100, age_days=60)
    return root
