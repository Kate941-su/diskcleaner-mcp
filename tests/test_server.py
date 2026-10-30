"""ツール呼び出しの E2E（MCPServer.call_tool 経由）。"""

from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from diskclean_mcp import trash
from diskclean_mcp.server import mcp


@pytest.fixture(autouse=True)
def isolated_home(home, monkeypatch):
    # 実際のホームに依存させない。Windows では tmp_path が ~/AppData 配下にあり、
    # アプリ管理領域として開発キャッシュが除外されてしまうため
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


async def call(name: str, **args) -> dict:
    return (await mcp.call_tool(name, args)).structured_content


async def test_lists_tools_and_prompt():
    assert {t.name for t in await mcp.list_tools()} == {
        "get_os_env_paths",
        "analyze_disk_usage",
        "scan_cleanup_targets",
        "move_to_trash",
    }
    assert [p.name for p in await mcp.list_prompts()] == ["cleanup_workflow"]


async def test_move_to_trash_is_marked_destructive():
    tools = {t.name: t for t in await mcp.list_tools()}
    assert tools["move_to_trash"].annotations.destructive_hint
    assert tools["scan_cleanup_targets"].annotations.read_only_hint


@pytest.mark.parametrize("path", ["/", "/usr", "relative/path"])
async def test_scan_rejects_protected(path):
    with pytest.raises(ToolError):
        await call("scan_cleanup_targets", target_path=path, target_type="all")


async def test_scan_rejects_missing_dir(tmp_path):
    with pytest.raises(ToolError, match="存在しません"):
        await call("scan_cleanup_targets", target_path=str(tmp_path / "nope"), target_type="all")


async def test_analyze(tree):
    result = await call("analyze_disk_usage", target_path=str(tree))
    assert result["by_category_mb"]["video"] > 399
    assert result["largest_children"][0]["path"].endswith("media")
    assert {e["depth"] for e in result["largest_children"]} == {1}


async def test_analyze_with_depth(tree):
    result = await call("analyze_disk_usage", target_path=str(tree), max_depth=2)
    depths = {
        Path(e["path"]).relative_to(tree).as_posix(): e["depth"] for e in result["largest_children"]
    }
    assert depths["media"] == 1
    assert depths["media/old.mp4"] == 2
    assert result["entry_count"] == len(result["largest_children"])  # 30件未満なら全件


@pytest.mark.parametrize("depth", [0, 4])
async def test_analyze_rejects_out_of_range_depth(tree, depth):
    with pytest.raises(ToolError):
        await call("analyze_disk_usage", target_path=str(tree), max_depth=depth)


async def test_scan_then_trash_flow(tree, monkeypatch):
    moved = []
    monkeypatch.setattr(trash, "send2trash", moved.append)

    scan = await call(
        "scan_cleanup_targets", target_path=str(tree), target_type="dev_cache", max_results=2
    )
    assert scan["found_count"] == 5
    assert scan["returned_count"] == 2
    assert scan["truncated"] is True
    shown = [item["path"] for item in scan["items"]]

    result = await call(
        "move_to_trash",
        scan_id=scan["scan_id"],
        paths=[*shown, str(tree / "py" / ".venv")],  # 3件目は提示されていない
    )
    assert sorted(result["moved"]) == sorted(shown)
    assert len(moved) == 2
    assert result["skipped"][0]["path"].endswith(".venv")


async def test_trash_unknown_scan_id():
    with pytest.raises(ToolError, match="期限切れ"):
        await call("move_to_trash", scan_id="missing", paths=["/tmp/x"])
