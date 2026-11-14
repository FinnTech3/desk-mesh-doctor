// termcast: turn a cast JSON into an animated terminal GIF (and MP4). Every character shown is REAL output captured
// by record.py. A "panel" step puts a REAL screenshot (taken by `bac shot` during the recording) beside the terminal.
//
// Usage:
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node termcast.mjs cast.json out.gif [out.mp4]
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node termcast.mjs cast.json out.png --still   (last frame only, 2x scale)
//
// cast.json:
// {
//   "title": "audio_probe.py",            window title
//   "width": 940, "rows": 22,             pixel width and visible text rows (scrolls when output is longer)
//   "fontSize": 15,
//   "steps": [
//     { "type": "cmd", "text": "python3 audio_probe.py probe hit.wav" },   typed, then Enter
//     { "type": "out", "text": "line1\nline2" },                           printed in bursts
//     { "type": "note", "text": "# a comment shown dim, typed instantly" },
//     { "type": "pause", "ms": 800 },
//     { "type": "panel", "src": "/abs/path/shot.png", "label": "saved by bac shot" }   image shown beside the terminal
//   ],
//   "panelWidth": 380                          set it to put a side panel next to the terminal
//   "highlight": [ { "re": "^FINDING", "cls": "red" } ]    optional extra rules: cls = red green yellow blue dim bold
// }
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
// Playwright is not a dependency of this repo. Point PLAYWRIGHT_DIR at any folder that has it in node_modules
// (for example a scratch folder where you ran `npm install playwright`), or put it on NODE_PATH.
const { chromium } = createRequire(path.resolve(process.env.PLAYWRIGHT_DIR || '.') + '/')('playwright');

const [,, castFile, outFile, third, fourth] = process.argv;
const still = third === '--still' || fourth === '--still';
const mp4Out = third && third !== '--still' ? third : null;
const cast = JSON.parse(fs.readFileSync(castFile, 'utf8'));
const FPS = 12;
const width = cast.width || 940;
const rows = cast.rows || 22;
const fontSize = cast.fontSize || 15;
const panelWidth = cast.panelWidth || 0;
// final hold on the last frame, in seconds
const endHold = cast.endHold ?? 3;
const lineH = Math.round(fontSize * 1.45);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const rules = [
  { re: /^(FINDING|FAIL|ERROR|error:|Traceback)/, cls: 'red' },
  { re: /\b(FAIL|FAILED|failed|ERROR)\b/, cls: 'red' },
  { re: /\b(PASS|passed|ok)\b/, cls: 'green' },
  { re: /^#/, cls: 'dim' },
  ...(cast.highlight || []).map((h) => ({ re: new RegExp(h.re), cls: h.cls })),
];
const line = (t) => {
  const r = rules.find((x) => x.re.test(t));
  return r ? `<span class="${r.cls}">${esc(t)}</span>` : esc(t);
};

// Build the list of states. A state is the full list of rendered lines plus whether a cursor shows.
const states = []; // { lines: [html], hold: frames }
const cur = [];
let curPanel = null;
const panels = [];
const push = (hold = 1, cursor = true) => states.push({ lines: cur.slice(), hold, cursor, panel: curPanel });
const prompt = '<span class="prompt">$</span> ';
push(Math.round(FPS * 0.3));
for (const s of cast.steps) {
  if (s.type === 'pause') { push(Math.max(1, Math.round((s.ms / 1000) * FPS))); continue; }
  if (s.type === 'panel') {
    const data = fs.readFileSync(s.src).toString('base64');
    panels.push({ uri: `data:image/png;base64,${data}`, label: s.label || '' });
    curPanel = panels.length - 1;
    push(Math.round(FPS * 1.1), false);
    continue;
  }
  if (s.type === 'note') { cur.push(`<span class="dim">${esc(s.text)}</span>`); push(Math.round(FPS * 0.4)); continue; }
  if (s.type === 'cmd') {
    const text = s.text;
    const per = Math.max(2, Math.ceil(text.length / (FPS * (cast.typeSeconds || 3))));   // never type for more than typeSeconds
    for (let i = per; i < text.length + per; i += per) {
      const shown = text.slice(0, Math.min(i, text.length));
      states.push({ lines: [...cur, prompt + esc(shown)], hold: 1, cursor: true, panel: curPanel });
    }
    cur.push(prompt + esc(text));
    push(Math.round(FPS * 0.2), false);
    continue;
  }
  if (s.type === 'out') {
    const ls = s.text.replace(/\n$/, '').split('\n');
    const burst = Math.max(cast.burst || 1, Math.ceil(ls.length / (FPS * 4)));   // finish printing within ~4 seconds
    for (let i = 0; i < ls.length; i += burst) {
      for (const t of ls.slice(i, i + burst)) cur.push(line(t));
      push(1, false);
    }
    push(Math.round(FPS * (s.holdSeconds ?? 1.2)), false);
  }
}
states.push({ lines: cur.slice(), hold: Math.round(FPS * endHold), cursor: false, last: true, panel: curPanel });
// Poster: one frame of the finished state first, so a viewer that shows only the first frame (a thumbnail, an
// unfurled link) sees the payoff. It equals the end of the loop, so nothing flickers when the clip restarts.
if (!still && cast.poster !== false) states.unshift({ ...states[states.length - 1], hold: 1, last: false });

const html = (st) => {
  const visible = st.lines.slice(-rows);
  const body = visible.map((l) => `<div class="l">${l || '&nbsp;'}</div>`).join('');
  const win = `<div class="win"><div class="bar"><i class="r"></i><i class="y"></i><i class="g"></i><span>${esc(cast.title || 'terminal')}</span></div>
  <div class="term">${body}${st.cursor ? '<span class="cur"></span>' : ''}</div></div>`;
  if (!panelWidth) return win;
  const p = st.panel === null || st.panel === undefined ? null : panels[st.panel];
  const side = p
    ? `<div class="side"><div class="cap">${esc(p.label)}</div><div class="gap"></div><img src="${p.uri}"><div class="gap"></div><div class="gap" style="flex:.35"></div></div>`
    : '<div class="side"><div class="cap">screenshots from bac shot appear here</div></div>';
  return `<div class="stage">${win}${side}</div>`;
};

const css = `
*{box-sizing:border-box}body{margin:0;background:transparent}
.stage{display:flex;width:${width + panelWidth}px;border-radius:${still ? 12 : 0}px;overflow:hidden;background:#1b1d26;box-shadow:0 0 0 1px #2d3040}
.win{width:${width}px;border-radius:${still && !panelWidth ? 12 : 0}px;overflow:hidden;background:#1b1d26;box-shadow:${panelWidth ? 'none' : '0 0 0 1px #2d3040'};font-family:'JetBrains Mono','DejaVu Sans Mono','SF Mono',Menlo,Consolas,monospace;font-size:${fontSize}px}
.bar{height:36px;background:#252836;display:flex;align-items:center;padding:0 14px;gap:8px;color:#8b90a8;font-size:13px}
.bar i{width:12px;height:12px;border-radius:50%;display:inline-block}.r{background:#ff5f57}.y{background:#febc2e}.g{background:#28c840}
.bar span{margin-left:12px;flex:1;text-align:center;margin-right:60px}
.term{font-variant-ligatures:none;font-feature-settings:'liga' 0,'calt' 0;height:${rows * lineH + 28}px;padding:14px 18px;color:#d5d9ea;overflow:hidden;white-space:pre;line-height:${lineH}px}
.l{height:${lineH}px}
.prompt{color:#7ee787}.red{color:#ff7b72}.green{color:#7ee787}.yellow{color:#e3b341}.blue{color:#79c0ff}.dim{color:#7a8099}.bold{font-weight:700;color:#fff}
.side{width:${panelWidth}px;background:#12141c;border-left:1px solid #2d3040;display:flex;flex-direction:column;align-items:center;padding:0 22px}
.side .gap{flex:1}
.cap{height:36px;color:#7a8099;font:12.5px/36px 'DejaVu Sans Mono',Menlo,Consolas,monospace;white-space:nowrap}
.side img{width:100%;border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.55)}
.cur{display:inline-block;width:9px;height:${fontSize + 2}px;background:#d5d9ea;vertical-align:text-bottom;margin-left:1px}
`;

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'termcast-'));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: width + panelWidth + 20, height: rows * lineH + 100 }, deviceScaleFactor: still ? 2 : 1 });
await page.setContent(`<style>${css}</style><body><div id="root"></div></body>`);
const el = () => page.locator(panelWidth ? '.stage' : '.win');

const cache = new Map();
let n = 0;
const frames = [];
const targets = still ? [states[states.length - 1]] : states;
for (const st of targets) {
  const key = html(st);
  if (!cache.has(key)) {
    await page.evaluate((h) => { document.getElementById('root').innerHTML = h; }, key);
    const f = path.join(tmp, `s${cache.size}.png`);
    await el().screenshot({ path: f, omitBackground: true });
    cache.set(key, f);
  }
  frames.push({ file: cache.get(key), hold: st.hold });
}
await browser.close();

if (still) {
  fs.copyFileSync(frames[0].file, outFile);
  console.log('still:', outFile);
  process.exit(0);
}

// Expand holds into a numbered frame sequence by hard-linking, then encode.
const seq = path.join(tmp, 'seq');
fs.mkdirSync(seq);
for (const f of frames) for (let k = 0; k < f.hold; k++) { n += 1; fs.linkSync(f.file, path.join(seq, `f${String(n).padStart(5, '0')}.png`)); }
const pattern = path.join(seq, 'f%05d.png');
execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-framerate', String(FPS), '-i', pattern,
  '-vf', `format=rgb24,split[a][b];[a]palettegen=max_colors=${panelWidth ? 160 : 48}:stats_mode=diff[p];[b][p]paletteuse=dither=${panelWidth ? 'bayer:bayer_scale=5' : 'none'}:diff_mode=rectangle`, outFile]);
if (mp4Out) execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-framerate', String(FPS), '-i', pattern, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-crf', '22', mp4Out]);
console.log(`wrote ${outFile} (${(fs.statSync(outFile).size / 1024).toFixed(0)} KB), ${n} frames, ${(n / FPS).toFixed(1)} s`);
if (!process.env.KEEP) fs.rmSync(tmp, { recursive: true, force: true }); else console.log('kept', tmp);
