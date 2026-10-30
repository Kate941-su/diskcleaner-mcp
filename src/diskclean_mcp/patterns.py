"""削除候補の判定パターン。"""

import re
import sys
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

# 中に pyvenv.cfg があり、兄弟にプロジェクト定義がある場合のみ仮想環境とみなす
VENV_NAMES = frozenset({".venv", "venv"})
VENV_PROJECT_MARKERS = (
    "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile",
    "poetry.lock", "uv.lock",
)  # fmt: skip

# ホームからの相対パスで限定するキャッシュ（親ディレクトリには設定も含まれるため）
HOME_SUBPATH_CACHES = ((".gradle", "caches"), (".cargo", "registry"))

# ホーム直下のアプリ管理領域（隠しディレクトリもこれに含める）。中の node_modules や venv は
# pnpm ストア・nvm の npm 本体・VS Code 拡張・SDK などアプリ本体の一部なので、候補にしない
HOME_APP_DATA_DIRS = frozenset({"Library", "AppData", "fvm"})

# このサーバー自身が動いている Python 環境
ACTIVE_PREFIX = Path(sys.prefix).resolve()

# 走査しても得るものがないので降りないディレクトリ
SKIP_DESCEND = frozenset({".git", ".hg", ".svn"})

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v", ".wmv"})

_LOG_RE = re.compile(r"\.log(\.\d+)?(\.gz)?$", re.IGNORECASE)


def _in_app_data(path: Path, home: Path) -> bool:
    try:
        top = path.relative_to(home).parts[0]
    except (ValueError, IndexError):
        return False
    return top.startswith(".") or top in HOME_APP_DATA_DIRS


def is_dev_cache_dir(path: Path, home: Path) -> bool:
    if any(path == home.joinpath(*sub) for sub in HOME_SUBPATH_CACHES):
        return True
    if path == ACTIVE_PREFIX or _in_app_data(path, home):
        return False
    name = path.name
    if name in ALWAYS_DEV_CACHE:
        return True
    if name in MARKER_DEV_CACHE:
        return any((path.parent / marker).is_file() for marker in MARKER_DEV_CACHE[name])
    if name in VENV_NAMES:
        return (path / "pyvenv.cfg").is_file() and any(
            (path.parent / marker).is_file() for marker in VENV_PROJECT_MARKERS
        )
    return False


def is_opaque_dir(path: Path) -> bool:
    """候補でなくても中身を走査する意味がないディレクトリ（node_modules や venv の中身など）。"""
    return path.name in ALWAYS_DEV_CACHE or path.name in VENV_NAMES or path == ACTIVE_PREFIX


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def is_log(name: str) -> bool:
    return _LOG_RE.search(name) is not None
