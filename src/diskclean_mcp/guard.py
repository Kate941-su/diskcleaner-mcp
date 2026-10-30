"""パスの正規化と保護判定。"""

from pathlib import Path, PurePath
from typing import Literal

from .platform_paths import OsName, ProtectionRules, current_rules

Operation = Literal["scan", "trash"]


class ProtectedPathError(ValueError):
    pass


def _key(path: PurePath, os_name: OsName) -> tuple[str, ...]:
    # Windows と macOS(APFS既定) は大文字小文字を区別しない
    if os_name == "linux":
        return path.parts
    return tuple(part.casefold() for part in path.parts)


def _within(path: tuple[str, ...], base: tuple[str, ...]) -> bool:
    return path[: len(base)] == base


def protection_reason(path: PurePath, op: Operation, rules: ProtectionRules) -> str | None:
    """保護対象なら理由を、そうでなければ None を返す。path は絶対パスであること。"""
    key = _key(path, rules.os_name)

    for blocked in rules.subtree:
        if _within(key, _key(blocked, rules.os_name)):
            return f"システム保護領域 {blocked} の配下です"

    if len(key) == 1:
        return "ルートディレクトリは対象にできません"
    if op == "scan":
        return None

    if len(key) == 2:
        return "ルート直下のディレクトリは退避できません"
    for base in rules.shallow:
        base_key = _key(base, rules.os_name)
        if _within(key, base_key) and len(key) <= len(base_key) + 1:
            return f"{base} 自身およびその直下は退避できません"
    return None


def check_path(raw: str, op: Operation, rules: ProtectionRules | None = None) -> Path:
    """入力パスを正規化し、保護対象なら ProtectedPathError を送出する。"""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ProtectedPathError(f"絶対パスを指定してください: {raw}")
    if op == "trash" and path.is_symlink():
        raise ProtectedPathError(f"シンボリックリンクは退避できません: {raw}")
    resolved = path.resolve(strict=False)

    reason = protection_reason(resolved, op, rules or current_rules())
    if reason:
        raise ProtectedPathError(f"{resolved}: {reason}")
    return resolved
