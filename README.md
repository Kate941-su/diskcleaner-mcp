# Disk Clean MCP Server

<!-- mcp-name: io.github.Kate941-su/diskclean-mcp-server -->

[日本語](https://github.com/Kate941-su/diskcleaner-mcp/blob/main/README.ja.md) | English

Ask Claude or another AI assistant to "clean up my disk". This MCP server finds the files that eat your disk space and **moves them to the trash**.

- Nothing is deleted. Items go to the OS trash, so you can restore them later
- You always see a list first, and only the items you approve are moved
- System folders are never touched

Supported OS: macOS / Linux / Windows

## What it finds

| Type | Examples |
|---|---|
| Developer caches | `node_modules`, `__pycache__`, Rust `target/`, `build/` and `dist/`, Python virtual environments (`.venv`), `~/.gradle/caches`, `~/.cargo/registry` |
| Large, unused videos | `.mp4`, `.mov`, `.mkv` and other videos over 100 MB that have not been opened or changed in 90 days |
| Old logs | `.log` and `.log.gz` files not updated in 30 days |

You can change the size and age limits when you ask (for example "videos over 500 MB" or "logs older than a year").

---

## Install

### Claude Desktop (easiest)

1. Download the latest `diskclean-mcp-server-*.mcpb` from [Releases](https://github.com/Kate941-su/diskcleaner-mcp/releases)
2. Double-click the file, or drag it into Claude Desktop's **Settings → Extensions**
3. Click **Install**

Claude Desktop sets up Python and everything else for you.

### Other apps (Claude Code, Cline, manual setup)

These use [uv](https://docs.astral.sh/uv/) to download and run the server. You do not need to install Python yourself.

**Step 1. Install uv**

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new terminal and check that `uv --version` works.

**Step 2. Add the server to your app**

#### Claude Code

```bash
claude mcp add --scope user diskclean -- uvx diskclean-mcp-server
```

`--scope user` makes it available in every project.

Optional: install the skill that teaches Claude the safe cleanup steps.

```bash
mkdir -p ~/.claude/skills/disk-cleanup
curl -fsSL https://raw.githubusercontent.com/Kate941-su/diskcleaner-mcp/main/.claude/skills/disk-cleanup/SKILL.md \
  -o ~/.claude/skills/disk-cleanup/SKILL.md
```

#### Claude Desktop (manual setup)

Open the config file:

| OS | Config file |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Add the following and restart Claude Desktop:

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

#### Cline (VS Code)

Open the config file from Cline's **MCP Servers** screen and add the same entry as above.

---

## How to use

Ask your assistant in plain words:

```
My disk is full. Find files I don't need in my home folder.
```

```
Clean up all the node_modules folders under ~/projects.
```

```
Find videos in ~/Movies over 1 GB that I haven't watched in six months.
```

```
Show me what is using space in ~/Library/Caches, two levels deep.
```

### What happens

1. The assistant looks at the folder and tells you what is using the space
2. You get a list of candidates (path, type, size, last modified) and the total space you can free. **Nothing has been moved yet**
3. You say what to move ("all of them", "only node_modules", "everything except #3")
4. Only the approved items go to the trash, and you get a report

### Restoring files

Everything goes to the trash, so you can bring it back at any time.

- **macOS**: open the Trash in Finder, right-click the item and choose **Put Back**
- **Windows**: open the Recycle Bin, right-click the item and choose **Restore**
- **Linux**: open the trash in your file manager and choose **Restore** (stored in `~/.local/share/Trash`)

Disk space is actually freed when you empty the trash.

### What is never moved

- OS system folders (`/usr`, `/System`, `C:\Windows`, `C:\Program Files`, and so on)
- Your home folder itself, and folders directly under the disk root
- Anything that was not in the list you were shown
- Symbolic links (and the files they point to)

`build/` and `dist/` only count as caches when a build file such as `package.json` sits next to them, so normal folders with the same name are not picked up by mistake.

---

## Updating

The Claude Desktop extension: download the new `.mcpb` from Releases and install it again.

With uvx: uv keeps a cached copy. To get the latest version, run the following and restart your app.

```bash
uv cache clean diskclean-mcp-server
```

To always start the newest version, use `"args": ["diskclean-mcp-server@latest"]` instead. This checks for updates every time the server starts.

---

## Troubleshooting

**The tools don't show up in my assistant**
- Restart the app after changing settings
- Claude Desktop may not find `uvx`. Put the full path in `"command"`. Find it with `which uvx` on macOS / Linux or `where uvx` on Windows
- In Claude Code, check with `claude mcp list`

**"Some folders could not be read" (skipped_errors)**
- Folders you don't have permission to read are skipped. On macOS, giving the app **Full Disk Access** may help (System Settings → Privacy & Security)

**The scan stopped early (timed_out)**
- One scan runs for up to 60 seconds. Ask for a smaller folder, such as `~/projects`

---

## For developers

See [docs/DESIGN.md](https://github.com/Kate941-su/diskcleaner-mcp/blob/main/docs/DESIGN.md) for the design, tool specs, development setup and release process (in Japanese).

## License

[MIT](https://github.com/Kate941-su/diskcleaner-mcp/blob/main/LICENSE)
