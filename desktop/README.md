# cooked. desktop (experiment)

Branch `exp/desktop-mcp`. A test of whether cooked. can be a desktop app with no API billing. Not for release.

Three pieces:

1. `plugins/ai-editor/mcp/server.py`: an MCP server. The user's own Claude calls its tools, so all AI runs on
   their Claude plan. No API key anywhere.
2. `plugins/ai-editor/mcp/cooked.mcpb`: that server packed as a one-click Claude desktop extension.
3. `desktop/`: an Electron shell. Home page in one window, each video in its own window.

## Try it

### The MCP server

Self-check (scratch library, no real files touched):

```bash
python3 plugins/ai-editor/mcp/server.py demo
```

In Claude desktop: double-click `plugins/ai-editor/mcp/cooked.mcpb`, or Settings > Extensions > Install
Extension and pick the file. Leave "cooked. plugin folder" empty to use the newest cooked. Claude Code installed,
or pick this checkout's `plugins/ai-editor`. Then ask Claude: "list my cooked. videos", "open <name>",
"get my notes on <name>".

In Claude Code instead:

```bash
claude mcp add cooked -- python3 /Users/maximussoares/Documents/ai-video-editor-textui/plugins/ai-editor/mcp/server.py
```

Rebuild the extension after changing the server:

```bash
plugins/ai-editor/mcp/pack.sh
```

Tools: `list_videos`, `open_video`, `get_notes`, `show`, `scene_ops`, `add_item`, `resolve_note`, `hand_back`,
`export`. Each wraps a CLI in `lib/ai_editor` (review.py, scene.py, library.py). `export` presses the page's
Export (POST /export) and waits for it.

### The Electron shell

```bash
cd desktop && npm install && npx electron .
```

If `npm install` skips Electron's download (npm's install-scripts policy), run `node node_modules/electron/install.js`.

It starts `home.py serve --no-open` on the first free port from 48900 (or reuses a home page already running), opens
it, and opens each video page in its own window. Links to the web open in the browser. Quitting stops home.py and
the video servers it started for the windows.

Env: `COOKED_PLUGIN` (plugin folder), `COOKED_PYTHON`, `COOKED_PORT`. Test hook: `COOKED_SHOT_DIR` saves a PNG of
each window, `COOKED_TEST_OPEN=<edit dir>` opens that video from home, then the app quits.

## What does not work yet

- MCP cannot wake Claude. Notes left on the page wait until the chat calls `get_notes`. The page still says "Notes
  go to your Terminal Claude" when a Terminal session ran the last command.
- `get_notes` waits 30 s by default. Claude desktop times out long tool calls, so it cannot block like `wait` does.
- Making a cut, the styled edit and teardowns still run as Claude Code skills. The MCP has no `cut` or `style_edit`
  tool. The skills cannot ship in an `.mcpb`: the format holds a server, tools and prompts, not skills.
- The home page's buttons that queue jobs (New video, Analyse a format) still wait for a Claude Code `home.py wait`.
- Review pages the MCP server opens stop when the Claude app restarts the server.
- In `npx electron` the Dock and the menu bar say "Electron". Only a packaged app (its own Info.plist) shows
  "cooked.".

## What a signed, bundled build still needs

- Python 3 bundled (python-build-standalone) with the plugin's requirements, instead of the user's python3.
- ffmpeg and ffprobe bundled (static arm64 and x64 builds), with their licences.
- Node and the Remotion renderer bundled, with its headless Chrome, so renders work offline on first launch.
- The plugin itself inside the app's Resources, and `COOKED_PLUGIN` pointed there.
- electron-builder or Electron Forge for the `.app` and `.dmg`, with icon and Info.plist name "cooked.".
- An Apple Developer ID certificate, hardened runtime, entitlements for the bundled binaries, and notarization
  (`notarytool`), or Gatekeeper blocks it.
- Auto-update (electron-updater against GitHub Releases, or Squirrel.Mac), signed too.
- The `.mcpb` shipped inside the app (or a "Connect to Claude" button that opens it), so one download sets up both.
