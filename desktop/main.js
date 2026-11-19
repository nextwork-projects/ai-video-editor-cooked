// cooked. desktop shell (experiment): runs home.py, shows the home page in a window and each video page in its own.
// No AI here. Claude runs in the user's own Claude app (the cooked. extension) or Claude Code.
const { app, BrowserWindow, Menu, shell } = require('electron');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

app.setName('cooked.');

// Homebrew's python3 and ffmpeg: an app opened from the Dock gets a bare PATH.
process.env.PATH = ['/opt/homebrew/bin', '/usr/local/bin', process.env.PATH].join(':');

function pluginDir() {
  const cands = [process.env.COOKED_PLUGIN, path.join(__dirname, '..', 'plugins', 'ai-editor')];
  const cache = path.join(os.homedir(), '.claude', 'plugins', 'cache');
  try {
    for (const m of fs.readdirSync(cache)) {
      const base = path.join(cache, m, 'ai-editor');
      if (!fs.existsSync(base)) continue;
      const vs = fs.readdirSync(base).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).reverse();
      cands.push(...vs.map(v => path.join(base, v)));
    }
  } catch {}
  const hit = cands.find(c => c && fs.existsSync(path.join(c, 'lib', 'ai_editor', 'home.py')));
  if (!hit) throw new Error('cooked. is not installed. Set COOKED_PLUGIN to the plugins/ai-editor folder.');
  return hit;
}

function freePort(p = Number(process.env.COOKED_PORT || 48900)) {
  return new Promise(res => {
    const s = net.createServer().once('error', () => res(freePort(p + 1)));
    s.listen(p, '127.0.0.1', () => s.close(() => res(p)));
  });
}

let home = null;           // the home.py process (null when another one was already serving)
const videoPorts = new Set();   // review.py servers home.py started for our windows: stopped on quit

function startHome(port) {
  const py = process.env.COOKED_PYTHON || 'python3';
  const p = spawn(py, [path.join(pluginDir(), 'lib', 'ai_editor', 'home.py'), 'serve', '--port', String(port), '--no-open'],
    { stdio: ['ignore', 'pipe', 'inherit'] });
  return new Promise((res, rej) => {
    let buf = '';
    p.stdout.on('data', d => {
      buf += d;
      const m = buf.match(/http:\/\/127\.0\.0\.1:\d+\/\?t=[\w-]+/);
      if (m) { res({ proc: p, url: m[0] }); p.stdout.removeAllListeners('data'); p.stdout.resume(); }
    });
    p.once('exit', code => rej(new Error(`home.py exited ${code}`)));
  });
}

const isLocal = u => { try { const x = new URL(u); return ['127.0.0.1', 'localhost'].includes(x.hostname); } catch { return false; } };

// One window per page. Another localhost port (a video's review.py) opens in its own window; the web opens in the
// browser.
function openWindow(url, opts = {}) {
  const win = new BrowserWindow({ width: opts.width || 1280, height: opts.height || 820, title: 'cooked.',
    backgroundColor: '#111111', webPreferences: { contextIsolation: true, sandbox: true } });
  const route = (e, target) => {
    if (!target || new URL(target).origin === new URL(win.webContents.getURL() || url).origin) return;
    e.preventDefault();
    if (isLocal(target)) openVideo(target); else shell.openExternal(target);
  };
  win.webContents.on('will-navigate', route);
  win.webContents.on('will-redirect', route);   // home's /review?dir= answers 302 to the video's own server
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (isLocal(target) && new URL(target).origin === new URL(url).origin) return { action: 'allow' };
    if (isLocal(target)) openVideo(target); else shell.openExternal(target);
    return { action: 'deny' };
  });
  win.loadURL(url);
  if (process.env.COOKED_SHOT_DIR) shotWhenLoaded(win, opts.shot || 'home');
  return win;
}

const videoWins = new Map();
function openVideo(url) {
  const origin = new URL(url).origin;
  videoPorts.add(new URL(url).port);
  const w = videoWins.get(origin);
  if (w && !w.isDestroyed()) return w.focus();
  videoWins.set(origin, openWindow(url, { width: 1440, height: 900, shot: 'video' }));
}

function menu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'cooked.', submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' },
      { type: 'separator' }, { role: 'quit' }] },
    { role: 'editMenu' },   // undo, redo, cut, copy, paste, select all
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'toggleDevTools' }, { type: 'separator' },
      { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' }, { role: 'togglefullscreen' }] },
    { role: 'windowMenu' },
  ]));
}

// ---- test hook: COOKED_SHOT_DIR saves a PNG of each window; COOKED_TEST_OPEN=<edit dir> clicks into that video
// from home (through home's /review redirect), then quits once both are saved.
const shots = new Set();
function shotWhenLoaded(win, name) {
  win.webContents.once('did-finish-load', () => setTimeout(async () => {
    const img = await win.webContents.capturePage();
    fs.mkdirSync(process.env.COOKED_SHOT_DIR, { recursive: true });
    fs.writeFileSync(path.join(process.env.COOKED_SHOT_DIR, `${name}.png`), img.toPNG());
    shots.add(name);
    console.log(`shot ${name} ${win.webContents.getURL()}`);
    if (name === 'home' && process.env.COOKED_TEST_OPEN)
      win.webContents.executeJavaScript(`location.href='/review?dir='+encodeURIComponent(${JSON.stringify(process.env.COOKED_TEST_OPEN)})`);
    if (shots.has('video') || (shots.has('home') && !process.env.COOKED_TEST_OPEN)) app.quit();
  }, Number(process.env.COOKED_SHOT_WAIT || 4000)));
}

function stopServers() {
  for (const port of videoPorts) {   // home.py starts review.py detached: find each by its port
    try {
      for (const pid of execFileSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN']).toString().split(/\s+/).filter(Boolean))
        process.kill(Number(pid));
    } catch {}
  }
  if (home && home.exitCode === null) home.kill();
}

app.whenReady().then(async () => {
  menu();
  try {
    const { proc, url } = await startHome(await freePort());
    home = proc;
    openWindow(url);
  } catch (e) {
    require('electron').dialog.showErrorBox('cooked. did not start', String(e.message || e));
    app.quit();
  }
});
app.on('window-all-closed', () => app.quit());
app.on('will-quit', stopServers);
process.on('SIGINT', () => app.quit());
process.on('SIGTERM', () => app.quit());
