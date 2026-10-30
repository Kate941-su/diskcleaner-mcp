---
paths:
  - "src/**"
---
# 安全性ルール

- `os.remove` / `os.unlink` / `shutil.rmtree` / `Path.unlink` / `Path.rmdir` など完全削除 API は使用禁止。ファイル退避は `trash.py` 内の `send2trash` のみ。
- 走査の起点とゴミ箱移動の対象は、必ず `guard.check_path()` を通してから使う。
- `move_to_trash` はスキャン結果（`ScanCache`）に含まれるパスしか受け付けない。この照合を外す変更はしない。
- シンボリックリンクは辿らない（`follow_symlinks=False` / `lstat`）。リンク自体のゴミ箱移動も拒否する。
- 保護パス（`platform_paths.py`）を変更・追加したら、`tests/test_guard.py` に拒否・許可の両方のテストを追加し、`docs/DESIGN.md` の保護パス表も更新する。
- 権限エラー等で走査できない場所は黙って落とさず、件数として結果に含める。
