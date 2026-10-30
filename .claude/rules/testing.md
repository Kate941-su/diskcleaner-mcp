---
paths:
  - "tests/**"
---
# テストルール

- 実際のホームディレクトリやシステム領域は触らない。ファイルは `tmp_path` 配下に作る。
- `send2trash` は monkeypatch でモックする（テストで本物のゴミ箱を汚さない）。
- OS依存の判定は `platform_paths.current_os` を monkeypatch で差し替え、linux / windows / darwin の3つすべてをテストする。
- 日時の条件は `os.utime` でファイルの atime/mtime を設定して検証する。
- ツールの E2E は `await mcp.call_tool(name, args)` で直接呼ぶ。
