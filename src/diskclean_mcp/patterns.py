"""削除候補の判定パターン。"""

import re
from pathlib import Path

# 名前だけで開発キャッシュと判定できるディレクトリ
ALWAYS_DEV_CACHE = frozenset(
    {
        "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".tox", ".next", ".parcel-cache", ".turbo",
    }
)  # fmt: skip

# 兄弟にマーカーファイルがある場合のみ開発キャッシュとみなす（ソースの誤検出防止）
MARKER_DEV_CACHE: dict[str, tuple[str, ...]] = {
    "target": ("Cargo.toml", "pom.xml"),
    "build": (
        "build.gradle", "build.gradle.kts", "setup.py", "pyproject.toml",
        "CMakeLists.txt", "package.json",
    ),
    "dist": ("package.json", "pyproject.toml", "setup.py"),
}  # fmt: skip

# 中に pyvenv.cfg がある場合のみ仮想環境とみなす
VENV_NAMES = frozenset({".venv", "venv"})

# ホームからの相対パスで限定するキャッシュ（親ディレクトリには設定も含まれるため）
HOME_SUBPATH_CACHES = ((".gradle", "caches"), (".cargo", "registry"))

# 走査しても得るものがないので降りないディレクトリ
SKIP_DESCEND = frozenset({".git", ".hg", ".svn"})

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v", ".wmv"})

_LOG_RE = re.compile(r"\.log(\.\d+)?(\.gz)?$", re.IGNORECASE)


def is_dev_cache_dir(path: Path, home: Path) -> bool:
    name = path.name
    if name in ALWAYS_DEV_CACHE:
        return True
    if name in MARKER_DEV_CACHE:
        return any((path.parent / marker).is_file() for marker in MARKER_DEV_CACHE[name])
    if name in VENV_NAMES:
        return (path / "pyvenv.cfg").is_file()
    return any(path == home.joinpath(*sub) for sub in HOME_SUBPATH_CACHES)


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def is_log(name: str) -> bool:
    return _LOG_RE.search(name) is not None
