"""diskclean MCP サーバー本体。"""

import logging
import os
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import scanner, trash
from .guard import ProtectedPathError, check_path
from .models import (
    CleanupItem,
    EnvPaths,
    ScanResult,
    TargetType,
    TrashResult,
    UsageEntry,
    UsageSummary,
)
from .platform_paths import current_os, current_rules, default_cache_paths

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SEC = 60
MAX_CHILDREN = 30
MAX_ANALYZE_DEPTH = 3
MB = 1024**2

WORKFLOW = """\
1. 対象パスが未指定なら get_os_env_paths で標準のキャッシュ・ログの場所を確認する。
2. analyze_disk_usage で容量の内訳を把握する。
3. scan_cleanup_targets で削除候補を作る（Dry-Run。削除はされない）。
4. 結果を表（パス・種別・サイズ・最終更新）でユーザーに提示し、どれを移動するか明示的な同意を得る。
5. 同意された項目だけを scan_id と共に move_to_trash に渡す。
6. moved / skipped / failed を報告し、ゴミ箱から復元できることを伝える。
同意なしに move_to_trash を呼ばないこと。保護パスのエラーは迂回しないこと。"""

INSTRUCTIONS = (
    "開発キャッシュ・大容量動画・古いログを検出し、OSのゴミ箱へ退避するサーバー。"
    "完全削除は行わない。必ず次の手順に従うこと:\n" + WORKFLOW
)

mcp = MCPServer("diskclean-mcp", version=version("diskclean-mcp-server"), instructions=INSTRUCTIONS)
_cache = scanner.ScanCache()

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _mb(size: int) -> float:
    return round(size / MB, 2)


def _date(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _resolve_dir(target_path: str) -> Path:
    try:
        path = check_path(target_path, "scan")
    except ProtectedPathError as e:
        raise ToolError(str(e)) from e
    if not path.is_dir():
        raise ToolError(f"ディレクトリが存在しません: {path}")
    return path


@mcp.tool(annotations=_READ_ONLY)
def get_os_env_paths() -> EnvPaths:
    """OSに応じた代表的なキャッシュ・ログディレクトリのうち、実在するものを返す。
    掃除対象の場所をユーザーが指定していないときの候補探しに使う。"""
    home = Path.home()
    paths = default_cache_paths(current_os(), home, os.environ)
    return EnvPaths(
        os=current_os(),
        home=str(home),
        cache_paths={k: str(v) for k, v in paths.items() if v.is_dir()},
    )


@mcp.tool(annotations=_READ_ONLY)
async def analyze_disk_usage(
    target_path: Annotated[str, Field(description="調査するディレクトリの絶対パス（~ 可）")],
    max_depth: Annotated[
        int,
        Field(ge=1, le=MAX_ANALYZE_DEPTH, description="内訳を出す階層の深さ（1=直下の子のみ）"),
    ] = 1,
) -> UsageSummary:
    """指定ディレクトリ配下の容量内訳を返す（読み取りのみ）。
    カテゴリ別合計（dev_cache/video/log/other）と、深さ max_depth までのエントリのうち
    大きい順の上位を含む。各エントリのサイズは配下の合計なので、親子のサイズは重複する。
    どこが大きいか分かったら、そのパスを指定して再度呼ぶと効率よく掘り下げられる。"""
    root = _resolve_dir(target_path)
    usage, stats = await anyio.to_thread.run_sync(
        lambda: scanner.analyze(
            root,
            current_rules(),
            home=Path.home(),
            max_depth=max_depth,
            timeout_sec=SCAN_TIMEOUT_SEC,
        )
    )
    entries = sorted(usage.children.items(), key=lambda kv: kv[1], reverse=True)
    return UsageSummary(
        target_path=str(root),
        total_mb=_mb(usage.total),
        by_category_mb={k: _mb(v) for k, v in usage.by_category.items()},
        largest_children=[
            UsageEntry(path=str(p), depth=len(p.relative_to(root).parts), size_mb=_mb(s))
            for p, s in entries[:MAX_CHILDREN]
        ],
        entry_count=len(entries),
        skipped_errors=stats.errors,
        timed_out=stats.timed_out,
    )


@mcp.tool(annotations=_READ_ONLY)
async def scan_cleanup_targets(
    target_path: Annotated[str, Field(description="スキャンを開始するディレクトリの絶対パス")],
    target_type: Annotated[
        TargetType,
        Field(
            description="dev_cache=node_modules等の開発キャッシュ, "
            "large_videos=大容量で未使用の動画, old_logs=更新のない古いログ, all=すべて"
        ),
    ],
    min_size_mb: Annotated[float, Field(ge=0, description="動画の最小サイズ(MB)")] = 100,
    older_than_days: Annotated[float, Field(ge=0, description="ログの未更新日数の閾値")] = 30,
    unused_days: Annotated[
        float, Field(ge=0, description="動画の未アクセス・未更新日数の閾値")
    ] = 90,
    max_results: Annotated[int, Field(ge=1, le=1000, description="返す候補の最大件数")] = 200,
) -> ScanResult:
    """条件に一致する削除候補をサイズの大きい順に列挙する（Dry-Run。何も削除しない）。
    返された scan_id は move_to_trash に必要。結果はユーザーに提示して同意を得ること。"""
    root = _resolve_dir(target_path)
    criteria = scanner.ScanCriteria(
        target_type=target_type,
        min_size_bytes=int(min_size_mb * MB),
        older_than_days=older_than_days,
        unused_days=unused_days,
    )
    found, stats = await anyio.to_thread.run_sync(
        lambda: scanner.scan(
            root, criteria, current_rules(), home=Path.home(), timeout_sec=SCAN_TIMEOUT_SEC
        )
    )
    shown = found[:max_results]
    return ScanResult(
        scan_id=_cache.put(shown),
        target_path=str(root),
        target_type=target_type,
        found_count=len(found),
        total_reclaimable_mb=_mb(sum(c.size for c in found)),
        returned_count=len(shown),
        truncated=len(found) > len(shown),
        timed_out=stats.timed_out,
        skipped_errors=stats.errors,
        items=[
            CleanupItem(
                path=str(c.path),
                kind=c.kind,
                size_mb=_mb(c.size),
                last_modified=_date(c.mtime),
                last_accessed=_date(c.atime),
            )
            for c in shown
        ],
    )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
    )
)
def move_to_trash(
    scan_id: Annotated[str, Field(description="scan_cleanup_targets が返した scan_id")],
    paths: Annotated[
        list[str], Field(description="ゴミ箱へ移動するパス。そのスキャン結果に含まれるもののみ")
    ],
) -> TrashResult:
    """指定パスをOSのゴミ箱（Trash/Recycle Bin）へ移動する。完全削除はしない。
    必ずユーザーの明示的な同意を得てから実行すること。
    スキャン結果にないパスや保護パスは skip される。"""
    try:
        return trash.move_to_trash(_cache, scan_id, paths)
    except (trash.UnknownScanError, ValueError) as e:
        raise ToolError(str(e)) from e


@mcp.prompt()
def cleanup_workflow(target_path: str = "") -> str:
    """ディスククリーンアップを安全な手順で進めるためのプロンプト。"""
    target = f"対象: {target_path}\n" if target_path else ""
    return f"diskclean ツールでディスク容量を空けてください。\n{target}手順:\n{WORKFLOW}"


def main() -> None:
    # stdout は stdio トランスポートが使うため、ログは stderr へ
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run()
