---
paths:
  - "src/diskclean_mcp/server.py"
  - "src/diskclean_mcp/models.py"
---
# MCP ツール定義ルール

- `mcp` 2.x の `MCPServer`（旧 FastMCP）を使う。`mcp.server.fastmcp` は存在しない。
- ツールの docstring と引数の型ヒントが、そのまま LLM 向けの説明と入力スキーマになる。用途・前提条件・副作用を具体的に書く。
- 戻り値は `models.py` の pydantic モデルにする（構造化出力）。`str(dict)` は返さない。
- レスポンスが大きくなりすぎないよう、件数の上限（`max_results`）を設け、超過時は `truncated: true` を返す。
- 入力エラーや保護パスへの要求は `ToolError` を送出する（クライアントには `isError` で伝わる）。
- ツールを追加・変更したら `.claude/skills/disk-cleanup/SKILL.md`、`server.py` の `INSTRUCTIONS` と `cleanup_workflow` prompt、`docs/DESIGN.md`（仕様）、利用者に影響があれば README も更新する。
