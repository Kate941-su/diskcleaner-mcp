"""ツールの戻り値モデル。"""

from typing import Literal

from pydantic import BaseModel

TargetType = Literal["dev_cache", "large_videos", "old_logs", "all"]
ItemKind = Literal["dev_cache", "large_video", "old_log"]


class EnvPaths(BaseModel):
    os: str
    home: str
    cache_paths: dict[str, str]


class UsageEntry(BaseModel):
    path: str
    depth: int
    size_mb: float


class UsageSummary(BaseModel):
    target_path: str
    total_mb: float
    by_category_mb: dict[str, float]
    largest_children: list[UsageEntry]
    entry_count: int
    skipped_errors: int
    timed_out: bool


class CleanupItem(BaseModel):
    path: str
    kind: ItemKind
    size_mb: float
    last_modified: str
    last_accessed: str


class ScanResult(BaseModel):
    scan_id: str
    target_path: str
    target_type: TargetType
    found_count: int
    total_reclaimable_mb: float
    returned_count: int
    truncated: bool
    timed_out: bool
    skipped_errors: int
    items: list[CleanupItem]


class PathIssue(BaseModel):
    path: str
    reason: str


class TrashResult(BaseModel):
    moved: list[str]
    moved_mb: float
    skipped: list[PathIssue]
    failed: list[PathIssue]
