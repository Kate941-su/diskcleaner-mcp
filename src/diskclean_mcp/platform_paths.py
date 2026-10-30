"""OS判定、保護パス定義、標準キャッシュパス。

保護の判定はOSを問わず純粋関数で行えるよう、パスは PurePath として扱う。
"""

import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Literal

OsName = Literal["linux", "windows", "darwin"]


def current_os() -> OsName:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "darwin"
    return "linux"


def pure_path_cls(os_name: OsName) -> type[PurePath]:
    return PureWindowsPath if os_name == "windows" else PurePosixPath


@dataclass(frozen=True)
class ProtectionRules:
    os_name: OsName
    # このパス自身と配下すべてを保護（走査・退避とも拒否）
    subtree: tuple[PurePath, ...]
    # このパス自身と直下の子を退避対象にしない（配下の走査は可）
    shallow: tuple[PurePath, ...]


_LINUX_SUBTREE = (
    "/bin", "/sbin", "/usr", "/etc", "/boot", "/dev", "/proc", "/sys",
    "/lib", "/lib32", "/lib64", "/run", "/var/lib", "/root", "/snap",
)  # fmt: skip
_DARWIN_SUBTREE = (
    "/System", "/Library", "/Applications", "/bin", "/sbin", "/usr", "/etc",
    "/dev", "/cores", "/opt", "/private/etc", "/private/var/db",
    "/private/var/root", "/private/var/vm",
)  # fmt: skip


def protection_rules(os_name: OsName, home: PurePath, env: Mapping[str, str]) -> ProtectionRules:
    cls = pure_path_cls(os_name)
    home = cls(home)
    # ホームの親（/home, /Users, C:\Users）とその直下＝各ユーザーのホームは丸ごと退避させない
    shallow: list[PurePath] = [home.parent]

    if os_name == "windows":
        subtree = [
            cls(env.get("SystemRoot", r"C:\Windows")),
            cls(env.get("ProgramFiles", r"C:\Program Files")),
            cls(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            cls(env.get("ProgramData", r"C:\ProgramData")),
        ]
    elif os_name == "darwin":
        subtree = [cls(p) for p in _DARWIN_SUBTREE] + [home / "Library" / "Keychains"]
        shallow += [cls("/Volumes"), home / "Library"]
    else:
        subtree = [cls(p) for p in _LINUX_SUBTREE]

    return ProtectionRules(os_name=os_name, subtree=tuple(subtree), shallow=tuple(shallow))


def current_rules() -> ProtectionRules:
    return protection_rules(current_os(), Path.home(), os.environ)


def default_cache_paths(os_name: OsName, home: Path, env: Mapping[str, str]) -> dict[str, Path]:
    """OSごとの代表的なキャッシュ・ログの場所（存在チェック前）。"""
    if os_name == "windows":
        local = env.get("LOCALAPPDATA", "")
        paths = {
            "local_appdata": local,
            "temp": env.get("TEMP", ""),
            "npm_cache": str(Path(local) / "npm-cache") if local else "",
            "pip_cache": str(Path(local) / "pip" / "Cache") if local else "",
        }
        result = {k: Path(v) for k, v in paths.items() if v}
    elif os_name == "darwin":
        result = {
            "caches": home / "Library" / "Caches",
            "logs": home / "Library" / "Logs",
            "npm_cache": home / ".npm",
        }
    else:
        result = {
            "cache": home / ".cache",
            "var_log": Path("/var/log"),
            "tmp": Path("/tmp"),
            "npm_cache": home / ".npm",
        }
    result["gradle_caches"] = home / ".gradle" / "caches"
    result["cargo_registry"] = home / ".cargo" / "registry"
    return result
