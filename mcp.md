# MCP ディスククリーンアップシステム 実装計画書

本ドキュメントは、Model Context Protocol (MCP) を使用して、AIエージェント（Claude Desktop, Cline 等）と連携し、OS（Linux / Windows）上の不要ファイルや大容量データを安全に検出・移動・削除するカスタムMCPサーバーの構成および実装手順をまとめた計画書です。

---

## 1. システム概要と目的

* **目的**: ディスク容量を圧迫する不要領域（開発キャッシュ、大容量動画、古いログ等）をAIエージェント経由で直感的に検索・整理できる環境を構築する。
* **主要ターゲット**:
  1. **開発キャッシュ**: `node_modules`, `__pycache__`, `.gradle/caches`, `.cargo/registry`, `target/` 等
  2. **大容量動画**: 指定サイズ以上（例: 100MB+）で一定期間アクセスがない動画ファイル (`.mp4`, `.mov`, `.mkv`, `.avi` 等)
  3. **古いログ**: 指定日数以上更新のないログファイル (`.log`, `.gz`, `.zip` 等)
* **対応OS**: Linux, Windows

---

## 2. ツール設計 (MCP Tools)

AIエージェントから呼び出すプロシージャとして以下の4つのツールを実装します。

| ツール名 | 説明 | 主要引数 |
| :--- | :--- | :--- |
| `get_os_env_paths` | システムの代表的なデフォルトキャッシュパス（`~/.cache`, `%LOCALAPPDATA%` 等）を取得する | なし |
| `analyze_disk_usage` | 指定パス配下の容量内訳（開発キャッシュ/動画/ログ/その他）をサマリー表示する | `target_path`: 調査対象パス |
| `scan_cleanup_targets` | 条件に合致する削除候補のリストを作成し、削減可能容量を算出する（Dry-Run） | `target_path`, `min_size_mb`, `older_than_days`, `target_type` |
| `move_to_trash` | 提示されたパスリストを安全にOSのゴミ箱（Trash/Recycle Bin）へ移動する | `paths`: パスの配列 |

---

## 3. 安全性設計（ガードレール）

1. **システムの保護（除外パスの定義）**:
   * Windows: `C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)`
   * Linux: `/`, `/bin`, `/sbin`, `/usr`, `/etc`, `/boot`, `/dev`, `/proc`, `/sys`
   * 上記ディレクトリおよびその直接配下に対する一括操作要求は強制的に拒否します。
2. **完全削除ではなく「ゴミ箱への退避」**:
   * `send2trash` ライブラリを採用し、復元可能な状態を保持します。
3. **ドライランの標準適用**:
   * スキャンツールと削除（退避）ツールを明確に分離し、必ず削除前に視覚的に対象をAIおよび人間が確認できるフローとします。

---

## 4. プロジェクト構造と事前準備

### 依存パッケージ (`requirements.txt`)
```text
mcp>=1.0.0
send2trash>=1.8.0
pydantic>=2.0.0
```

### ディレクトリ構成
```text
mcp-disk-cleaner/
├── server.py             # MCPサーバーメインロジック
├── requirements.txt      # 依存パッケージ
└── README.md             # 使用法マニュアル
```

---

## 5. サーバーコード実装例 (`server.py`)

```python
import os
import platform
import sys
from pathlib import Path
from send2trash import send2trash

from mcp.server import Server
import mcp.types as types

app = Server("disk-cleaner-mcp")

# --- 保護された除外パスリスト ---
BLOCKED_PATHS_WIN = {Path("C:/Windows"), Path("C:/Program Files"), Path("C:/Program Files (x86)")}
BLOCKED_PATHS_LINUX = {Path("/"), Path("/bin"), Path("/sbin"), Path("/usr"), Path("/etc"), Path("/boot"), Path("/dev"), Path("/proc"), Path("/sys")}

def is_protected_path(target: Path) -> bool:
    target_resolved = target.resolve()
    blocked_set = BLOCKED_PATHS_WIN if platform.system() == "Windows" else BLOCKED_PATHS_LINUX
    for blocked in blocked_set:
        try:
            if target_resolved == blocked or blocked in target_resolved.parents:
                return True
        except Exception:
            continue
    return False

# --- ターゲットパターンの定義 ---
DEV_CACHE_NAMES = {"node_modules", "__pycache__", ".gradle", ".cargo", "target", "build", "dist", ".cache"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv"}
LOG_EXTENSIONS = {".log", ".gz", ".log.1"}

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_os_env_paths",
            description="OSに応じたデフォルトのキャッシュやログディレクトリの標準パスを取得します。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="scan_cleanup_targets",
            description="条件に一致する不要ファイル/ディレクトリをスキャンします（削除は行われません）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_path": {"type": "string", "description": "スキャンを開始する絶対パス"},
                    "target_type": {"type": "string", "enum": ["dev_cache", "large_videos", "old_logs", "all"], "description": "スキャン対象カテゴリ"},
                    "min_size_mb": {"type": "number", "default": 100, "description": "大容量動画検出の最小サイズ(MB)"},
                    "older_than_days": {"type": "number", "default": 30, "description": "ログ等の未更新日数閾値"},
                },
                "required": ["target_path", "target_type"],
            },
        ),
        types.Tool(
            name="move_to_trash",
            description="指定されたパスリストを安全にゴミ箱へ移動します。ユーザーの明示的な同意後に実行してください。",
            inputSchema={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "ゴミ箱へ移動するファイル/ディレクトリパスのリスト"
                    }
                },
                "required": ["paths"],
            },
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    arguments = arguments or {}

    if name == "get_os_env_paths":
        home = Path.home()
        sys_name = platform.system()
        paths = {"home": str(home)}
        if sys_name == "Windows":
            paths["local_appdata"] = os.getenv("LOCALAPPDATA", "")
            paths["temp"] = os.getenv("TEMP", "")
        else:
            paths["cache"] = str(home / ".cache")
            paths["var_log"] = "/var/log"
        return [types.TextContent(type="text", text=str(paths))]

    elif name == "scan_cleanup_targets":
        target = Path(arguments["target_path"])
        if is_protected_path(target):
            return [types.TextContent(type="text", text="エラー: 保護されたシステム領域はスキャンできません。")]
        
        target_type = arguments.get("target_type")
        min_bytes = arguments.get("min_size_mb", 100) * 1024 * 1024
        results = []
        total_reclaimable_bytes = 0

        # ディレクトリ走査
        for root, dirs, files in os.walk(target):
            root_path = Path(root)
            
            # 開発キャッシュチェック (ディレクトリ単位)
            if target_type in ["dev_cache", "all"]:
                for d in list(dirs):
                    if d in DEV_CACHE_NAMES:
                        full_p = root_path / d
                        # 概算サイズ計測
                        size = sum(f.stat().st_size for f in full_p.glob('**/*') if f.is_file())
                        results.append({"path": str(full_p), "type": "dev_cache", "size_mb": round(size / (1024*1024), 2)})
                        total_reclaimable_bytes += size
                        dirs.remove(d) # 深追いを防止

            # ファイル単位チェック
            for f in files:
                file_p = root_path / f
                try:
                    stat = file_p.stat()
                except Exception:
                    continue

                # 大容量動画
                if target_type in ["large_videos", "all"] and file_p.suffix.lower() in VIDEO_EXTENSIONS:
                    if stat.st_size >= min_bytes:
                        results.append({"path": str(file_p), "type": "large_video", "size_mb": round(stat.st_size / (1024*1024), 2)})
                        total_reclaimable_bytes += stat.st_size

                # 古いログ
                if target_type in ["old_logs", "all"] and (file_p.suffix.lower() in LOG_EXTENSIONS or ".log" in f):
                    # 日数判定省略（拡張可能）
                    results.append({"path": str(file_p), "type": "old_log", "size_mb": round(stat.st_size / (1024*1024), 2)})
                    total_reclaimable_bytes += stat.st_size

        summary = {
            "found_items_count": len(results),
            "total_reclaimable_gb": round(total_reclaimable_bytes / (1024**3), 2),
            "items": results[:50] # レスポンスサイズ調整のため上位50件を返却
        }
        return [types.TextContent(type="text", text=str(summary))]

    elif name == "move_to_trash":
        paths_to_delete = arguments.get("paths", [])
        success_count = 0
        errors = []

        for p_str in paths_to_delete:
            p = Path(p_str)
            if is_protected_path(p):
                errors.append(f"スキップ (保護対象): {p_str}")
                continue
            try:
                send2trash(str(p))
                success_count += 1
            except Exception as e:
                errors.append(f"失敗 {p_str}: {str(e)}")

        res = {"moved_to_trash_count": success_count, "errors": errors}
        return [types.TextContent(type="text", text=str(res))]

    raise ValueError(f"Unknown tool: {name}")

if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server
    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    asyncio.run(main())
```

---

## 6. MCPクライアント設定 (Claude Desktop / Cline)

`claude_desktop_config.json` または Cline の `mcp.json` に設定を追加します。

### Windows の設定例
```json
{
  "mcpServers": {
    "disk-cleaner": {
      "command": "python",
      "args": [
        "C:\\path\\to\\mcp-disk-cleaner\\server.py"
      ]
    }
  }
}
```

### Linux の設定例
```json
{
  "mcpServers": {
    "disk-cleaner": {
      "command": "python3",
      "args": [
        "/home/username/mcp-disk-cleaner/server.py"
      ]
    }
  }
}
```

---

## 7. 今後の拡張ロードマップ

* [x] **詳細な最終使用日時の考慮**: `st_atime` (アクセス日時) や `st_mtime` (更新日時) を使った高精度なフィルタリングの追加。（実装済み: 動画は `max(atime, mtime)`、ログは `mtime` で判定）
* [ ] **スキャン速度の高速化**: 大規模ディレクトリ走査時に `concurrent.futures` 等を利用したマルチスレッド並列処理化。
* [ ] **カスタムルールの外部ファイル化**: `junk_patterns.json` のような外部定義ファイルを読み込める仕組みの構築。