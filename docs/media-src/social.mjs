// docs/social-preview.png (1280 x 640): logo, name, promise, and the REAL report from the recorded lab run.
// Usage: PLAYWRIGHT_DIR=... node social.mjs OUT.png VERDICT.cast.json LOGO.png
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(path.resolve(process.env.PLAYWRIGHT_DIR || '.') + '/')('playwright');
const [,, out, castFile, logoPng] = process.argv;
const cast = JSON.parse(fs.readFileSync(castFile, 'utf8'));
const report = cast.steps.find((s) => s.type === 'out' && (s.raw || '').startsWith('| from'));
if (!report) throw new Error('no mesh_report output in the recording');
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const rows = report.raw.split('\n').map((l) => {
  const cls = l.includes('[problem]') || l.includes('filtered') ? 'bad' : '';
  return `<div class="${cls}">${esc(l) || '&nbsp;'}</div>`;
}).join('');
const logo = `data:image/png;base64,${fs.readFileSync(logoPng).toString('base64')}`;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
await page.setContent(`<style>
*{box-sizing:border-box}body{margin:0;width:1280px;height:640px;overflow:hidden;position:relative;background:linear-gradient(135deg,#0e6b8a 0%,#14264f 80%);font-family:system-ui,'Segoe UI',Helvetica,sans-serif;color:#fff}
.logo{position:absolute;left:84px;top:96px;width:112px;height:112px;border-radius:26px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
h1{position:absolute;left:84px;top:244px;margin:0;font-size:60px;letter-spacing:-.02em}
.promise{position:absolute;left:84px;top:332px;width:520px;font-size:33px;line-height:1.3;color:#d4e8f5;text-wrap:balance}
.meta{position:absolute;left:84px;bottom:56px;font-size:22px;color:#9cc2dc}
.card{position:absolute;left:690px;top:130px;width:530px;background:#0d1117;border-radius:16px;box-shadow:0 18px 50px rgba(0,0,0,.5);padding:20px 24px;font:15px/1.6 'DejaVu Sans Mono',Menlo,monospace;color:#e6edf3;white-space:pre-wrap}
.card .h{font:600 14px system-ui,sans-serif;color:#7fa6bf;letter-spacing:.06em;margin-bottom:12px}
.bad{color:#ff8a80}
</style>
<img class="logo" src="${logo}"><h1>Desk Mesh Doctor</h1>
<div class="promise">Find out why your devices will not work as one desk, and fix it.</div>
<div class="meta">Built by FinnTech3 &nbsp;·&nbsp; MIT &nbsp;·&nbsp; Python 3.10+</div>
<div class="card"><div class="h">mesh_report.py, REAL OUTPUT FROM A TWO-DEVICE LAB</div>${rows}</div>`);
await page.screenshot({ path: out });
await browser.close();
console.log('wrote', out);
