# diskclean-mcp

AIエージェント（Claude Code / Claude Desktop / Cline）から、ディスクを圧迫する開発キャッシュ・大容量動画・古いログを検出し、OSのゴミ箱へ安全に退避させる MCP サーバー。対応OSは Linux / Windows / macOS。設計の元資料は [mcp.md](mcp.md)、現在の設計・仕様は [docs/DESIGN.md](docs/DESIGN.md)。README（英語 `README.md` と日本語 `README.ja.md`）はエンドユーザー向け（インストール・使い方）に限定し、内容を変えるときは両方を更新する。

## コマンド

```bash
uv run pytest                 # テスト
uv run ruff check .           # Lint
uv run ruff format .          # フォーマット
uv run diskclean-mcp-server          # stdio でサーバー起動
npx @modelcontextprotocol/inspector uv run diskclean-mcp-server   # GUI で手動確認
```

Python は uv 管理の 3.12（システムの python3 は 3.9 のため使わない）。依存追加は `uv add`。

## 配布

PyPI パッケージ名は `diskclean-mcp-server`（import 名は `diskclean_mcp`）。MCP Registry 用の `server.json` と Claude Desktop 拡張用の `manifest.json` もある。バージョンを上げるときは4か所すべてを合わせる。手順は `docs/DESIGN.md` の「リリース手順」を参照。

## MCP SDK

`mcp` 2.x を使用。FastMCP は `mcp.server.mcpserver.MCPServer` に改名されている（`mcp.server.fastmcp` は import できない）。v1 のサンプルコードをそのまま貼らないこと。

## モジュール構成（`src/diskclean_mcp/`）

| モジュール | 責務 |
|---|---|
| `server.py` | MCPServer 定義、4ツール + `cleanup_workflow` prompt、`main()` |
| `platform_paths.py` | OS判定 `current_os()`、保護パス定義、標準キャッシュパス |
| `guard.py` | パス正規化と保護判定 `check_path()` |
| `patterns.py` | 開発キャッシュ規則（名前 + マーカー）、動画拡張子、ログ判定 |
| `scanner.py` | 走査・サイズ計算・分類、`analyze()`、`ScanCache` |
| `trash.py` | スキャン結果との照合と `send2trash` |
| `models.py` | ツール戻り値の pydantic モデル |

## 重要な制約

- **stdout に print しない**。stdio トランスポートが壊れる。ログは stderr（`logging`）か `ctx.info()`。
- 完全削除は行わない。破壊的操作は `trash.py` の `send2trash` のみ。
- 破壊的操作・走査の起点は必ず `guard.check_path()` を通す。

詳細ルールは `.claude/rules/` を参照。エージェント向けの利用手順は `.claude/skills/disk-cleanup/SKILL.md`。
