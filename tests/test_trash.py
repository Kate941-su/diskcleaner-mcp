from pathlib import Path

import pytest

from diskclean_mcp import trash
from diskclean_mcp.scanner import ScanCache, ScanCriteria, scan


@pytest.fixture
def trashed(monkeypatch) -> list[Path]:
    moved: list[Path] = []
    monkeypatch.setattr(trash, "send2trash", moved.append)
    return moved


@pytest.fixture
def scanned(tree, rules, home):
    found, _ = scan(tree, ScanCriteria("all", 100 * 1024**2, 30, 90), rules, home=home)
    cache = ScanCache()
    return cache, cache.put(found), found


def test_moves_scanned_paths(scanned, trashed, rules):
    cache, sid, found = scanned
    target = next(c for c in found if c.path.name == "node_modules")
    result = trash.move_to_trash(cache, sid, [str(target.path)], rules)
    assert result.moved == [str(target.path)]
    assert trashed == [target.path]
    assert result.skipped == [] and result.failed == []


def test_skips_paths_not_in_scan(scanned, trashed, rules, tree):
    cache, sid, _ = scanned
    result = trash.move_to_trash(cache, sid, [str(tree / "docs" / "build")], rules)
    assert result.moved == []
    assert "含まれていません" in result.skipped[0].reason
    assert trashed == []


def test_skips_protected_even_if_requested(scanned, trashed, rules, home):
    cache, sid, _ = scanned
    result = trash.move_to_trash(cache, sid, ["/", str(home)], rules)
    assert len(result.skipped) == 2
    assert trashed == []


def test_unknown_scan_id(trashed, rules):
    with pytest.raises(trash.UnknownScanError):
        trash.move_to_trash(ScanCache(), "missing", ["/tmp/x"], rules)


def test_failure_is_reported(scanned, monkeypatch, rules):
    cache, sid, found = scanned

    def boom(path):
        raise OSError("disk busy")

    monkeypatch.setattr(trash, "send2trash", boom)
    result = trash.move_to_trash(cache, sid, [str(found[0].path)], rules)
    assert result.moved == []
    assert "disk busy" in result.failed[0].reason


def test_duplicates_and_missing(scanned, trashed, rules):
    cache, sid, found = scanned
    p = found[0].path
    result = trash.move_to_trash(cache, sid, [str(p), str(p)], rules)
    assert trashed == [p]
    assert len(result.moved) == 1
