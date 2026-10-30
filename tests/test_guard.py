from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from diskclean_mcp.guard import ProtectedPathError, check_path, protection_reason
from diskclean_mcp.platform_paths import protection_rules
from tests.conftest import make_symlink

P = PurePosixPath
W = PureWindowsPath

LINUX = protection_rules("linux", P("/home/u"), {})
DARWIN = protection_rules("darwin", P("/Users/u"), {})
WINDOWS = protection_rules("windows", W(r"C:\Users\u"), {})


@pytest.mark.parametrize(
    ("rules", "path"),
    [
        (LINUX, P("/")),
        (LINUX, P("/usr")),
        (LINUX, P("/usr/bin/x")),
        (LINUX, P("/etc/passwd")),
        (LINUX, P("/var/lib/docker")),
        (DARWIN, P("/")),
        (DARWIN, P("/System/Library")),
        (DARWIN, P("/system/library")),  # APFS は大文字小文字を区別しない
        (DARWIN, P("/Applications/Foo.app")),
        (DARWIN, P("/Users/u/Library/Keychains/login.keychain")),
        (WINDOWS, W("C:\\")),
        (WINDOWS, W(r"C:\Windows\System32")),
        (WINDOWS, W(r"c:\windows\system32")),
        (WINDOWS, W(r"C:\Program Files\App")),
        (WINDOWS, W(r"C:\Program Files (x86)\App")),
        (WINDOWS, W(r"C:\ProgramData\x")),
    ],
)
def test_rejected_for_scan_and_trash(rules, path):
    assert protection_reason(path, "scan", rules)
    assert protection_reason(path, "trash", rules)


@pytest.mark.parametrize(
    ("rules", "path"),
    [
        (LINUX, P("/home")),
        (LINUX, P("/home/u")),  # ホーム自体
        (LINUX, P("/home/other")),
        (LINUX, P("/var")),
        (DARWIN, P("/Users/u")),
        (DARWIN, P("/Users/u/Library")),
        (DARWIN, P("/Users/u/Library/Caches")),
        (DARWIN, P("/Volumes/External")),
        (WINDOWS, W(r"C:\Users")),
        (WINDOWS, W(r"C:\Users\u")),
        (WINDOWS, W(r"D:\data")),
    ],
)
def test_scan_allowed_but_trash_rejected(rules, path):
    assert protection_reason(path, "scan", rules) is None
    assert protection_reason(path, "trash", rules)


@pytest.mark.parametrize(
    ("rules", "path"),
    [
        (LINUX, P("/home/u/projects/a/node_modules")),
        (LINUX, P("/var/log/old.log")),
        (DARWIN, P("/Users/u/Library/Caches/foo")),
        (DARWIN, P("/Users/u/dev/a/node_modules")),
        (DARWIN, P("/private/var/folders/xx/T/tmp")),
        (WINDOWS, W(r"C:\Users\u\AppData\Local\Temp\x")),
        (WINDOWS, W(r"D:\data\videos\a.mp4")),
    ],
)
def test_allowed(rules, path):
    assert protection_reason(path, "scan", rules) is None
    assert protection_reason(path, "trash", rules) is None


def test_windows_rules_follow_env():
    rules = protection_rules("windows", W(r"C:\Users\u"), {"SystemRoot": r"D:\Win"})
    assert protection_reason(W(r"D:\Win\System32"), "scan", rules)
    assert protection_reason(W(r"C:\Windows\x"), "scan", rules) is None


def test_check_path_requires_absolute(rules):
    with pytest.raises(ProtectedPathError, match="絶対パス"):
        check_path("relative/dir", "scan", rules)


def test_check_path_rejects_symlink_for_trash(home: Path, rules):
    target = home / "real"
    target.mkdir()
    link = home / "projects" / "link"
    link.parent.mkdir()
    make_symlink(link, target)
    with pytest.raises(ProtectedPathError, match="シンボリックリンク"):
        check_path(str(link), "trash", rules)


def test_check_path_resolves_dotdot(home: Path, rules):
    # home から .. でルートまで遡り、保護領域（Linux/macOS: /usr など、Windows: C:\Windows）に入る
    protected = Path(rules.subtree[0])
    escape = Path(home, *[".."] * (len(home.parts) - 1), protected.relative_to(protected.anchor))
    with pytest.raises(ProtectedPathError):
        check_path(str(escape), "scan", rules)
