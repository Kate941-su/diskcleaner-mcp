import os
import sys
import time
from pathlib import Path

import pytest

from diskclean_mcp.scanner import ScanCache, ScanCriteria, analyze, scan
from tests.conftest import make_file, make_symlink


def criteria(target_type="all", min_mb=100, log_days=30, video_days=90):
    return ScanCriteria(target_type, int(min_mb * 1024**2), log_days, video_days)


def names(found, root: Path) -> set[str]:
    return {c.path.relative_to(root).as_posix() for c in found}


def test_dev_cache_requires_markers(tree, rules, home):
    found, stats = scan(tree, criteria("dev_cache"), rules, home=home)
    assert names(found, tree) == {
        "web/node_modules",
        "web/dist",
        "rust/target",
        "py/.venv",
        "py/src/__pycache__",
    }
    assert {c.kind for c in found} == {"dev_cache"}
    assert stats.errors == 0


def test_dev_cache_size_is_recursive(tree, rules, home):
    found, _ = scan(tree, criteria("dev_cache"), rules, home=home)
    by_name = {c.path.name: c.size for c in found}
    assert by_name["node_modules"] == 2000
    assert by_name["target"] == 3000


def test_home_subpath_caches(home, rules):
    make_file(home / ".gradle" / "caches" / "a.jar", 100)
    make_file(home / ".gradle" / "gradle.properties")
    make_file(home / ".cargo" / "registry" / "x.crate", 100)
    found, _ = scan(home, criteria("dev_cache"), rules, home=home)
    assert names(found, home) == {".gradle/caches", ".cargo/registry"}


def test_large_videos_need_size_and_age(tree, rules, home):
    found, _ = scan(tree, criteria("large_videos"), rules, home=home)
    assert names(found, tree) == {"media/old.mp4"}


def test_video_recent_atime_counts_as_used(tree, rules, home):
    video = tree / "media" / "old.mp4"
    os.utime(video, (time.time(), video.stat().st_mtime))
    found, _ = scan(tree, criteria("large_videos"), rules, home=home)
    assert found == []


def test_old_logs_by_mtime_and_pattern(tree, rules, home):
    found, _ = scan(tree, criteria("old_logs"), rules, home=home)
    assert names(found, tree) == {"logs/app.log", "logs/app.log.1.gz"}


def test_all_sorted_by_size_desc(tree, rules, home):
    found, _ = scan(tree, criteria("all"), rules, home=home)
    sizes = [c.size for c in found]
    assert sizes == sorted(sizes, reverse=True)
    assert found[0].path.name == "old.mp4"


def test_symlinks_are_not_followed(tmp_path, home, rules):
    outside = tmp_path.resolve() / "outside"
    make_file(outside / "node_modules" / "big.js", 5000)
    make_file(outside / "huge.log", 100, age_days=100)
    root = home / "p"
    root.mkdir()
    make_symlink(root / "link", outside)
    make_symlink(root / "node_modules", outside / "node_modules")
    found, _ = scan(root, criteria("all"), rules, home=home)
    assert found == []


def test_timeout_marks_result(tree, rules, home, monkeypatch):
    # Python 3.12 以前の Windows は monotonic の分解能が約15.6ms。呼ぶたびに進む時計に差し替える
    ticks = iter(range(1_000_000))
    monkeypatch.setattr("diskclean_mcp.scanner.time.monotonic", lambda: next(ticks))
    _, stats = scan(tree, criteria("all"), rules, home=home, timeout_sec=0.5)
    assert stats.timed_out


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod(0) で読めないディレクトリを作れない（Windows / root）",
)
def test_unreadable_dir_is_counted(tree, rules, home):
    locked = tree / "locked"
    make_file(locked / "a.log", 10, age_days=100)
    locked.chmod(0)
    try:
        _, stats = scan(tree, criteria("old_logs"), rules, home=home)
    finally:
        locked.chmod(0o755)
    assert stats.errors >= 1


def test_analyze_categories_and_children(tree, rules, home):
    usage, stats = analyze(tree, rules, home=home)
    # node_modules + dist + target + .venv(lib + pyvenv.cfg) + __pycache__
    assert usage.by_category["dev_cache"] == 2000 + 500 + 3000 + 410 + 50
    assert usage.by_category["video"] == 2 * 200 * 1024**2 + 1024
    assert usage.by_category["log"] == 300
    assert usage.total == sum(usage.by_category.values())
    assert usage.children[tree / "media"] == usage.by_category["video"]
    assert sum(usage.children.values()) == usage.total
    assert not stats.timed_out


def test_scan_cache_roundtrip_and_expiry(tree, rules, home):
    found, _ = scan(tree, criteria("all"), rules, home=home)
    cache = ScanCache(ttl_sec=1000)
    sid = cache.put(found)
    assert set(cache.get(sid)) == {str(c.path) for c in found}
    assert cache.get("nope") is None

    expired = ScanCache(ttl_sec=-1)
    sid = expired.put(found)
    assert expired.get(sid) is None


def test_analyze_depth_two_accumulates_into_ancestors(tree, rules, home):
    usage, _ = analyze(tree, rules, home=home, max_depth=2)
    entries = usage.children
    assert entries[tree / "web" / "node_modules"] == 2000
    assert entries[tree / "web"] == 10 + 2000 + 500  # package.json + node_modules + dist
    assert entries[tree / "py" / "src"] == 50
    # 深さ 3 以降は個別に出さない
    assert tree / "py" / "src" / "__pycache__" not in entries
    assert all(len(p.relative_to(tree).parts) <= 2 for p in entries)
    # 深さ 1 のエントリの合計は全体と一致する（親子の重複を除けば総量は変わらない）
    depth1 = sum(s for p, s in entries.items() if len(p.relative_to(tree).parts) == 1)
    assert depth1 == usage.total


def test_analyze_depth_does_not_change_totals(tree, rules, home):
    shallow, _ = analyze(tree, rules, home=home, max_depth=1)
    deep, _ = analyze(tree, rules, home=home, max_depth=3)
    assert shallow.total == deep.total
    assert shallow.by_category == deep.by_category
    assert all(deep.children[p] == s for p, s in shallow.children.items())
