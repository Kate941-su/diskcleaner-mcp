---
paths:
  - "**/*.py"
---
# Python コーディングルール

- Python 3.12。型ヒントは組み込みジェネリクス（`list[str]`, `X | None`）を使う。
- パス操作は `pathlib.Path`。文字列連結でパスを作らない。
- `uv run ruff check .` と `uv run ruff format .` が通ること。
- 例外を `except Exception: pass` で握りつぶさない。ツールの結果にエラー一覧・件数として返す。
- `print()` は使わない（stdio トランスポートを壊す）。ログは `logging`（stderr）。
