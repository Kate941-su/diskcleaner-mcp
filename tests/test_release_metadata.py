"""公開用メタデータ（PyPI / MCP Registry / .mcpb）の整合性チェック。"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
SERVER = json.loads((ROOT / "server.json").read_text())
MANIFEST = json.loads((ROOT / "manifest.json").read_text())


def test_versions_match():
    version = PYPROJECT["version"]
    assert SERVER["version"] == version
    assert all(p["version"] == version for p in SERVER["packages"])
    assert MANIFEST["version"] == version


def test_package_names_match():
    assert SERVER["packages"][0]["identifier"] == PYPROJECT["name"]
    assert MANIFEST["name"] == PYPROJECT["name"]
    assert PYPROJECT["name"] in PYPROJECT["scripts"]
    assert PYPROJECT["name"] in MANIFEST["server"]["mcp_config"]["args"]


def test_readme_has_registry_ownership_marker():
    # MCP Registry は PyPI の説明文（= README.md）に `mcp-name: <name>` があるかで所有者を確認する
    readme = (ROOT / "README.md").read_text()
    assert re.search(rf"mcp-name: {re.escape(SERVER['name'])}(\s|-->)", readme)


async def test_manifest_lists_all_tools():
    from diskclean_mcp.server import mcp

    tools = {t.name for t in await mcp.list_tools()}
    assert {t["name"] for t in MANIFEST["tools"]} == tools
