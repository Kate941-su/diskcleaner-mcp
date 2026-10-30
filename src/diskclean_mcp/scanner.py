"""ディレクトリ走査、サイズ計算、削除候補の分類。

シンボリックリンクは一切辿らない。読めない場所はスキップして件数を数える。
"""

import os
import stat
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .guard import protection_reason
from .models import ItemKind, TargetType
from .patterns import SKIP_DESCEND, is_dev_cache_dir, is_log, is_opaque_dir, is_video
from .platform_paths import ProtectionRules

DAY = 86400


@dataclass
class Candidate:
    path: Path
    kind: ItemKind
    size: int
    mtime: float
    atime: float


@dataclass
class WalkStats:
    errors: int = 0
    timed_out: bool = False


@dataclass
class ScanCriteria:
    target_type: TargetType
    min_size_bytes: int
    older_than_days: float
    unused_days: float

    def wants(self, kind: ItemKind) -> bool:
        if self.target_type == "all":
            return True
        return {"dev_cache": "dev_cache", "large_video": "large_videos", "old_log": "old_logs"}[
            kind
        ] == self.target_type


@dataclass
class _Deadline:
    at: float | None

    def passed(self) -> bool:
        return self.at is not None and time.monotonic() > self.at


def _iter_dir(path: Path, stats: WalkStats) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        stats.errors += 1
        return []


def dir_size(path: Path, stats: WalkStats, deadline: _Deadline | None = None) -> int:
    total = 0
    stack = [path]
    while stack:
        if deadline and deadline.passed():
            stats.timed_out = True
            break
        for entry in _iter_dir(stack.pop(), stats):
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                stats.errors += 1
                continue
            if stat.S_ISDIR(st.st_mode):
                stack.append(Path(entry.path))
            elif stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def scan(
    root: Path,
    criteria: ScanCriteria,
    rules: ProtectionRules,
    *,
    home: Path,
    now: float | None = None,
    timeout_sec: float | None = None,
) -> tuple[list[Candidate], WalkStats]:
    """条件に合う削除候補をサイズ降順で返す。削除は行わない。"""
    now = time.time() if now is None else now
    deadline = _Deadline(time.monotonic() + timeout_sec if timeout_sec else None)
    log_cutoff = now - criteria.older_than_days * DAY
    video_cutoff = now - criteria.unused_days * DAY
    stats = WalkStats()
    found: list[Candidate] = []
    stack = [root]

    while stack:
        if deadline.passed():
            stats.timed_out = True
            break
        for entry in _iter_dir(stack.pop(), stats):
            path = Path(entry.path)
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                stats.errors += 1
                continue

            if stat.S_ISDIR(st.st_mode):
                if entry.name in SKIP_DESCEND or protection_reason(path, "scan", rules):
                    continue
                if is_dev_cache_dir(path, home):
                    # 開発キャッシュの中身は対象外なので、対象カテゴリでなくても降りない
                    if criteria.wants("dev_cache"):
                        size = dir_size(path, stats, deadline)
                        found.append(Candidate(path, "dev_cache", size, st.st_mtime, st.st_atime))
                    continue
                if is_opaque_dir(path):
                    # アプリ管理領域の node_modules や使用中の venv。候補にしないが中身も対象外
                    continue
                stack.append(path)
            elif stat.S_ISREG(st.st_mode):
                if (
                    criteria.wants("large_video")
                    and is_video(entry.name)
                    and st.st_size >= criteria.min_size_bytes
                    # relatime/noatime 環境では atime が当てにならないため mtime も見る
                    and max(st.st_atime, st.st_mtime) < video_cutoff
                ):
                    found.append(
                        Candidate(path, "large_video", st.st_size, st.st_mtime, st.st_atime)
                    )
                elif criteria.wants("old_log") and is_log(entry.name) and st.st_mtime < log_cutoff:
                    found.append(Candidate(path, "old_log", st.st_size, st.st_mtime, st.st_atime))

    found.sort(key=lambda c: c.size, reverse=True)
    return found, stats


@dataclass
class Usage:
    total: int = 0
    by_category: Counter[str] = field(default_factory=Counter)
    children: dict[Path, int] = field(default_factory=dict)


def analyze(
    root: Path,
    rules: ProtectionRules,
    *,
    home: Path,
    max_depth: int = 1,
    timeout_sec: float | None = None,
) -> tuple[Usage, WalkStats]:
    """深さ max_depth までの各エントリのサイズと、カテゴリ別の合計を求める。

    ファイルのサイズは、深さ max_depth 以内にある祖先エントリすべてに加算する（1回の走査で済む）。
    """
    deadline = _Deadline(time.monotonic() + timeout_sec if timeout_sec else None)
    stats = WalkStats()
    usage = Usage()
    # (走査するディレクトリ, その深さ, 深さ max_depth 以内にある祖先エントリ)
    stack: list[tuple[Path, int, tuple[Path, ...]]] = [(root, 0, ())]

    while stack:
        if deadline.passed():
            stats.timed_out = True
            break
        current, depth, ancestors = stack.pop()
        for entry in _iter_dir(current, stats):
            path = Path(entry.path)
            owners = ancestors + (path,) if depth < max_depth else ancestors
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                stats.errors += 1
                continue

            if stat.S_ISDIR(st.st_mode):
                for owner in owners:
                    usage.children.setdefault(owner, 0)
                if protection_reason(path, "scan", rules):
                    continue
                if is_dev_cache_dir(path, home):
                    size, category = dir_size(path, stats, deadline), "dev_cache"
                else:
                    stack.append((path, depth + 1, owners))
                    continue
            elif stat.S_ISREG(st.st_mode):
                size = st.st_size
                if is_video(entry.name):
                    category = "video"
                elif is_log(entry.name):
                    category = "log"
                else:
                    category = "other"
            else:
                continue

            usage.total += size
            usage.by_category[category] += size
            for owner in owners:
                usage.children[owner] = usage.children.get(owner, 0) + size

    return usage, stats


class ScanCache:
    """スキャン結果として提示したパスを保持し、退避時の照合に使う。"""

    def __init__(self, ttl_sec: float = 1800, max_entries: int = 20) -> None:
        self._ttl = ttl_sec
        self._max = max_entries
        self._entries: dict[str, tuple[float, dict[str, Candidate]]] = {}

    def put(self, candidates: list[Candidate]) -> str:
        self._evict()
        scan_id = uuid.uuid4().hex[:12]
        self._entries[scan_id] = (time.monotonic(), {str(c.path): c for c in candidates})
        while len(self._entries) > self._max:
            del self._entries[next(iter(self._entries))]
        return scan_id

    def get(self, scan_id: str) -> dict[str, Candidate] | None:
        self._evict()
        entry = self._entries.get(scan_id)
        return entry[1] if entry else None

    def _evict(self) -> None:
        limit = time.monotonic() - self._ttl
        for key in [k for k, (created, _) in self._entries.items() if created < limit]:
            del self._entries[key]
