"""スキャン結果と照合したうえで、OSのゴミ箱へ退避する。"""

from send2trash import send2trash

from .guard import ProtectedPathError, check_path
from .models import PathIssue, TrashResult
from .platform_paths import ProtectionRules
from .scanner import ScanCache

MAX_PATHS_PER_CALL = 500


class UnknownScanError(LookupError):
    pass


def move_to_trash(
    cache: ScanCache, scan_id: str, paths: list[str], rules: ProtectionRules | None = None
) -> TrashResult:
    candidates = cache.get(scan_id)
    if candidates is None:
        raise UnknownScanError(
            f"scan_id {scan_id!r} が見つからないか期限切れです。"
            "scan_cleanup_targets を再実行してください"
        )
    if len(paths) > MAX_PATHS_PER_CALL:
        raise ValueError(f"一度に退避できるのは {MAX_PATHS_PER_CALL} 件までです")

    result = TrashResult(moved=[], moved_mb=0.0, skipped=[], failed=[])
    moved_bytes = 0
    for raw in dict.fromkeys(paths):
        try:
            path = check_path(raw, "trash", rules)
        except ProtectedPathError as e:
            result.skipped.append(PathIssue(path=raw, reason=str(e)))
            continue
        candidate = candidates.get(str(path))
        if candidate is None:
            result.skipped.append(PathIssue(path=raw, reason="このスキャン結果に含まれていません"))
            continue
        if not path.exists():
            result.skipped.append(PathIssue(path=raw, reason="存在しません（移動済みの可能性）"))
            continue
        try:
            send2trash(path)
        except Exception as e:  # send2trash はOSごとに異なる例外を投げる
            result.failed.append(PathIssue(path=raw, reason=f"{type(e).__name__}: {e}"))
            continue
        result.moved.append(str(path))
        moved_bytes += candidate.size

    result.moved_mb = round(moved_bytes / 1024**2, 2)
    return result
