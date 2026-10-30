# diskclean-mcp 設計ドキュメント

開発者向けの資料です。利用方法は [README.md](../README.md)（日本語版: [README.ja.md](../README.ja.md)）を、元の計画書は [mcp.md](../mcp.md) を参照してください。

## 構成

```
src/diskclean_mcp/
├── server.py           # MCPServer 定義、4ツール + cleanup_workflow prompt、main()
├── platform_paths.py   # OS判定 current_os()、保護パス定義、標準キャッシュパス
├── guard.py            # パス正規化と保護判定 check_path() / protection_reason()
├── patterns.py         # 開発キャッシュ規則（名前 + マーカー）、動画拡張子、ログ判定
├── scanner.py          # 走査・サイズ計算・分類、analyze()、ScanCache
├── trash.py            # スキャン結果との照合と send2trash
└── models.py           # ツール戻り値の pydantic モデル（構造化出力）
```

MCP SDK は `mcp` 2.x の `mcp.server.mcpserver.MCPServer`（旧 FastMCP）を使用しています。

## ツール仕様

| ツール | 引数 | 戻り値 |
|---|---|---|
| `get_os_env_paths` | なし | `EnvPaths`: os, home, cache_paths（実在するもののみ） |
| `analyze_disk_usage` | `target_path`, `max_depth`=1（1〜3） | `UsageSummary`: total_mb, by_category_mb（dev_cache/video/log/other）, largest_children（深さ `max_depth` までのエントリのうち大きい順の上位30件。各要素は path / depth / size_mb）, entry_count（集計したエントリの総数）, skipped_errors, timed_out |
| `scan_cleanup_targets` | `target_path`, `target_type`（dev_cache / large_videos / old_logs / all）, `min_size_mb`=100, `older_than_days`=30, `unused_days`=90, `max_results`=200 | `ScanResult`: scan_id, found_count, total_reclaimable_mb, returned_count, truncated, timed_out, skipped_errors, items |
| `move_to_trash` | `scan_id`, `paths` | `TrashResult`: moved, moved_mb, skipped（理由付き）, failed（理由付き） |

- 読み取り系の3ツールには `read_only_hint`、`move_to_trash` には `destructive_hint` を付けています。
- 入力エラーや保護パスへの要求は `ToolError` として返します（クライアントには `isError` で伝わります）。
- 安全な手順はサーバーの `instructions` と `cleanup_workflow` prompt でも提供しています。Claude Desktop や Cline は `.claude/skills` を読まないためです。
- `analyze_disk_usage` の深さ指定: 走査は1回だけで、各ファイルのサイズを深さ `max_depth` 以内の祖先エントリすべてに加算します。各エントリのサイズは配下の合計なので、親子のサイズは重複します（深さ1のエントリの合計が total と一致します）。深さを増やすとエントリ数が急に増えるため、上限を3にしています。

## 検出ルール

| 種別 | 条件 |
|---|---|
| 開発キャッシュ（名前だけで判定） | `node_modules`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.next`, `.parcel-cache`, `.turbo` |
| 開発キャッシュ（マーカーが必要） | `target/`: 兄弟に `Cargo.toml` か `pom.xml`<br>`build/`: 兄弟に `build.gradle(.kts)`, `setup.py`, `pyproject.toml`, `CMakeLists.txt`, `package.json` のいずれか<br>`dist/`: 兄弟に `package.json`, `pyproject.toml`, `setup.py` のいずれか<br>`.venv/`, `venv/`: 中に `pyvenv.cfg` があり、兄弟に `pyproject.toml`, `requirements.txt`, `setup.py`, `setup.cfg`, `Pipfile`, `poetry.lock`, `uv.lock` のいずれかがある |
| 開発キャッシュ（場所を限定） | `~/.gradle/caches`, `~/.cargo/registry`（親ディレクトリには設定ファイルも入っているため）。下の除外ルールより優先します |
| 除外（候補にしない） | ホーム直下の隠しディレクトリ（`~/.nvm`, `~/.vscode`, `~/.local` など）、`~/Library`、`~/AppData`、`~/fvm` の中にある開発キャッシュ。pnpm のストア、nvm の npm 本体、VS Code 拡張、アプリ本体の venv などで、消すとツールやアプリが壊れるため<br>このサーバー自身が動いている Python 環境（`sys.prefix`） |
| 大容量動画 | 拡張子が `.mp4 .mov .mkv .avi .webm .flv .m4v .wmv`、サイズが `min_size_mb` 以上、かつ `max(atime, mtime)` が `unused_days` 日より古い（relatime/noatime 環境では atime が当てにならないため mtime も見る） |
| 古いログ | ファイル名が正規表現 `\.log(\.\d+)?(\.gz)?$` に一致し、mtime が `older_than_days` 日より古い（`.zip` や `.gz` だけではログとみなさない） |

- 開発キャッシュと判定したディレクトリ、除外した `node_modules` 等や venv、`.git` / `.hg` / `.svn` には降りません。除外したディレクトリの中のログや動画も候補にしません。
- アプリ管理領域でも、`~/Library/Logs` のような古いログは候補にします（除外は開発キャッシュだけが対象です）。
- サイズはシンボリックリンクを辿らずに `lstat` の `st_size` を合計しています（ハードリンクは重複して数えます）。

## 安全設計

1. **完全削除しない**: 破壊的な操作は `trash.py` の `send2trash` だけです。
2. **スキャンと退避の分離**: `scan_cleanup_targets` は、提示した候補だけを `ScanCache` に `scan_id` と一緒に保存します（プロセス内メモリ、有効期限30分、最大20件）。`move_to_trash` は、そこに含まれるパスしか受け付けません。
3. **保護パス**（`platform_paths.protection_rules`、判定は `guard.protection_reason`）

   | 種類 | 走査 | 退避 | 対象 |
   |---|---|---|---|
   | subtree（自身と配下すべて） | 拒否 | 拒否 | Linux: `/bin /sbin /usr /etc /boot /dev /proc /sys /lib* /run /var/lib /root /snap`<br>macOS: `/System /Library /Applications /bin /sbin /usr /etc /dev /cores /opt /private/{etc,var/db,var/root,var/vm}`、`~/Library/Keychains`<br>Windows: `%SystemRoot%`, `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%ProgramData%` |
   | ルート（`/`, `C:\`） | 拒否 | 拒否 | 全OS |
   | ルート直下 | 許可 | 拒否 | 全OS |
   | shallow（自身と直下） | 許可 | 拒否 | ホームの親（`/home`, `/Users`, `C:\Users`。つまり各ユーザーのホーム自体）<br>macOS: `/Volumes`, `~/Library` |

   - Windows と macOS では大文字と小文字を区別せずに比較します。
   - 入力パスは `expanduser` してから `resolve` するので、`..` を使って保護領域に入ることはできません。相対パスは拒否します。
4. **シンボリックリンク**: 走査では辿りません。リンク自体のゴミ箱移動も拒否します。
5. **リソース上限**: 走査は60秒で打ち切り（`timed_out`）、返す候補は最大1000件（`max_results`）、`move_to_trash` は1回あたり500件までです。読めないディレクトリは `skipped_errors` として件数を返します。

## 開発

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format .
npx @modelcontextprotocol/inspector uv run diskclean-mcp-server
```

- コーディング規約: [CLAUDE.md](../CLAUDE.md), [.claude/rules/](../.claude/rules/)
- テストは `tmp_path` 上のダミーツリーで行います。`send2trash` はモックしています。OS依存の保護判定は、`PurePosixPath` / `PureWindowsPath` を使って3つのOSすべてを検証しています。

## 配布

| 配布先 | 利用者側の起動方法 | 定義ファイル |
|---|---|---|
| PyPI（`diskclean-mcp-server`） | `uvx diskclean-mcp-server` | `pyproject.toml` |
| MCP Registry（`io.github.Kate941-su/diskclean-mcp-server`） | 各クライアントのレジストリ検索から登録（中身は PyPI のパッケージ） | `server.json` |
| Claude Desktop 拡張（`.mcpb`、GitHub Releases に添付） | ダブルクリックでインストール | `manifest.json`, `.mcpbignore` |

- パッケージ名（配布名）は `diskclean-mcp-server` ですが、import 名は `diskclean_mcp` のままです（`[tool.uv.build-backend] module-name`）。PyPI の `diskclean-mcp` は別のプロジェクトがすでに使っています。
- MCP Registry は、PyPI の説明文（= `README.md`）に含まれる `mcp-name: io.github.Kate941-su/diskclean-mcp-server` という文字列で所有者を確認します。README の HTML コメントは消さないでください。
- `.mcpb` は `server.type: "uv"`（manifest 0.4）です。依存パッケージは同梱せず、ホスト（Claude Desktop）が `pyproject.toml` と `uv.lock` から uv でインストールします。
- バージョン番号は `pyproject.toml`、`server.json`（2か所）、`manifest.json` の計4か所にあります。`tests/test_release_metadata.py` がずれを検出します。

## リリース手順

### 初回だけ必要な準備

1. **PyPI**: アカウントを作り、[Trusted Publisher を事前登録](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)します（pending publisher）。
   - PyPI Project Name: `diskclean-mcp-server`
   - Owner: `Kate941-su`、Repository: `diskcleaner-mcp`
   - Workflow: `release.yml`、Environment: `pypi`
2. **GitHub**: リポジトリの Settings → Environments に `pypi` を作ります（必要なら、承認者を設定してから公開されるようにします）。
3. **MCP Registry**: 追加の登録は不要です。`io.github.Kate941-su/*` という名前空間は、このリポジトリの GitHub Actions の OIDC で認証されます。

### 毎回のリリース

1. `pyproject.toml`、`server.json`（`version` と `packages[0].version`）、`manifest.json` のバージョンを上げます（`uv version --bump patch` のあと、JSON の2ファイルを手で合わせます）。
2. `uv run pytest` が通ることを確認してコミットし、`main` に push します。
3. タグを打って push します: `git tag v0.1.1 && git push origin v0.1.1`
4. `.github/workflows/release.yml` が次の順に実行します。
   1. CI（lint、3OS × Python 3.12/3.13 のテスト、パッケージの検証）
   2. タグとすべてのバージョン番号が一致しているかの確認、ビルド、`.mcpb` の作成
   3. PyPI へ公開
   4. MCP Registry へ公開（PyPI に反映されるのを待ってから実行）
   5. GitHub Release を作成し、`.mcpb` を添付

### ローカルでの確認

```bash
uv build && uvx twine check dist/*
uvx --from ./dist/diskclean_mcp_server-<version>-py3-none-any.whl diskclean-mcp-server   # stdio で起動
npx -y @anthropic-ai/mcpb@2.1.2 validate manifest.json
npx -y @anthropic-ai/mcpb@2.1.2 pack . dist/diskclean-mcp-server.mcpb
```

## 未実装・今後の課題

- `ctx.report_progress` による進捗通知
- 大規模ディレクトリの並列走査
- 検出パターンの外部ファイル化（`junk_patterns.json` など）
