# Disk Clean MCP Server

日本語 | [English](https://github.com/Kate941-su/diskcleaner-mcp/blob/main/README.md)

Claude などの AI アシスタントに「ディスクを掃除して」と頼むだけで、容量を圧迫している不要なファイルを探し、**ゴミ箱へ移動**してくれる MCP サーバーです。

- 削除はせずゴミ箱に移すだけなので、あとから元に戻せます
- 移動の前に必ず一覧が表示され、あなたが承認したものだけが移動されます
- OSのシステム領域には手を出しません

対応OS: macOS / Linux / Windows

## 見つけてくれるもの

| 種類 | 例 |
|---|---|
| 開発用キャッシュ | `node_modules`、`__pycache__`、Rust の `target/`、`build/`・`dist/`、Python の仮想環境（`.venv`）、`~/.gradle/caches`、`~/.cargo/registry` など |
| 大きくて使っていない動画 | 100MB 以上で、90日以上開いても更新してもいない `.mp4` `.mov` `.mkv` などの動画 |
| 古いログ | 30日以上更新されていない `.log` や `.log.gz` |

サイズや日数の基準は、頼むときに変えられます（例: 「500MB 以上の動画」「1年以上前のログ」）。

---

## インストール

### Claude Desktop（いちばん簡単）

1. [Releases](https://github.com/Kate941-su/diskcleaner-mcp/releases) から、最新の `diskclean-mcp-server-*.mcpb` をダウンロードします
2. ファイルをダブルクリックするか、Claude Desktop の **設定 → 拡張機能** にドラッグします
3. **インストール** をクリックします

Python などの準備は Claude Desktop が自動で行います。

### そのほかのアプリ（Claude Code、Cline、手動設定）

[uv](https://docs.astral.sh/uv/) を使って、サーバーを自動でダウンロードして起動します。Python を自分でインストールする必要はありません。

**手順1. uv をインストールする**

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows（PowerShell）:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

ターミナルを開き直して、`uv --version` が表示されれば完了です。

**手順2. アプリに登録する**

#### Claude Code

```bash
claude mcp add --scope user diskclean -- uvx diskclean-mcp-server
```

`--scope user` を付けると、どのプロジェクトからでも使えます。

あわせて、安全な手順をアシスタントに覚えさせるスキルも入れておくと便利です（任意）。

```bash
mkdir -p ~/.claude/skills/disk-cleanup
curl -fsSL https://raw.githubusercontent.com/Kate941-su/diskcleaner-mcp/main/.claude/skills/disk-cleanup/SKILL.md \
  -o ~/.claude/skills/disk-cleanup/SKILL.md
```

#### Claude Desktop（手動設定）

設定ファイルを開きます。

| OS | 設定ファイルの場所 |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

次の内容を追加して、Claude Desktop を再起動します。

```json
{
  "mcpServers": {
    "diskclean": {
      "command": "uvx",
      "args": ["diskclean-mcp-server"]
    }
  }
}
```

#### Cline（VS Code）

Cline の「MCP Servers」画面から設定ファイルを開き、上と同じ内容を追加します。

---

## 使い方

AI アシスタントに、普段の言葉で頼んでください。

```
ディスクがいっぱいなので、ホームフォルダの不要なファイルを探して
```

```
~/projects の中の node_modules をまとめて掃除したい
```

```
~/Movies で 1GB 以上ある、半年以上見ていない動画を探して
```

```
~/Library/Caches の中で何が容量を使っているか、2階層下まで見せて
```

### 実際の流れ

1. アシスタントが対象のフォルダを調べ、容量の内訳を教えてくれます
2. 削除候補の一覧（パス・種類・サイズ・最終更新日）と、空けられる容量の合計が表示されます。**この時点ではまだ何も移動していません**
3. 移動してよいものを伝えます（「全部」「node_modules だけ」「3番以外」など）
4. 承認したものだけがゴミ箱に移動され、結果が報告されます

### 元に戻すには

ゴミ箱に入っているので、いつでも復元できます。

- **macOS**: Finder でゴミ箱を開き、ファイルを右クリックして「戻す」
- **Windows**: ごみ箱を開き、ファイルを右クリックして「元に戻す」
- **Linux**: ファイルマネージャーでゴミ箱を開いて「復元」（ゴミ箱の実体は `~/.local/share/Trash`）

ディスク容量が実際に空くのは、ゴミ箱を空にしたときです。

### 移動されないもの

- OSのシステムフォルダ（`/usr`、`/System`、`C:\Windows`、`C:\Program Files` など）
- ホームフォルダそのもの、ディスクのルート直下のフォルダ
- 一覧で提示されていないファイル
- シンボリックリンク（リンク先の実体も含む）

`build/` や `dist/` は、隣にビルド設定ファイル（`package.json` など）がある場合だけ候補になります。そのため、同じ名前の普通のフォルダが誤って候補になることはありません。

---

## アップデート

Claude Desktop の拡張機能の場合は、Releases から新しい `.mcpb` をダウンロードして、もう一度インストールします。

uvx の場合、uv はダウンロードしたものをキャッシュしています。最新版にするには次のコマンドを実行し、アプリを再起動します。

```bash
uv cache clean diskclean-mcp-server
```

常に最新版で起動したい場合は、`"args": ["diskclean-mcp-server@latest"]` と書きます。この場合、起動のたびに更新を確認します。

---

## うまくいかないとき

**アシスタントにツールが表示されない**
- 設定を変えたあと、アプリを再起動したか確認してください
- Claude Desktop では、`uvx` が見つからずに起動に失敗することがあります。その場合は `"command"` に uvx のフルパスを書いてください。フルパスは、macOS / Linux なら `which uvx`、Windows なら `where uvx` で確認できます
- Claude Code では `claude mcp list` で登録状態を確認できます

**「読めなかった場所がある」と言われる（skipped_errors）**
- 権限がないフォルダは飛ばしています。macOS では、アプリに「フルディスクアクセス」を許可すると読めるようになる場合があります（システム設定 → プライバシーとセキュリティ）

**スキャンが途中で終わる（timed_out）**
- 1回のスキャンは最大60秒です。`~/projects` のように範囲を絞って頼んでください

---

## 開発者向け

設計・仕様・開発手順・リリース手順は [docs/DESIGN.md](https://github.com/Kate941-su/diskcleaner-mcp/blob/main/docs/DESIGN.md) を参照してください。

## ライセンス

[MIT](https://github.com/Kate941-su/diskcleaner-mcp/blob/main/LICENSE)
