// Draw how the three scripts fit together, from REAL data: the JSON the scripts wrote in the recorded lab run
// and the text mesh_report.py printed for it.
// Usage: PLAYWRIGHT_DIR=... node fit-figure.mjs OUT.png RUN_DIR SCRIPTS_DIR
// RUN_DIR holds laptop-local.json, desk-local.json, laptop-to-desk.json and desk-to-laptop.json (blocked state).
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const { chromium } = createRequire(path.resolve(process.env.PLAYWRIGHT_DIR || '.') + '/')('playwright');
const [,, out, runDir, scriptsDir] = process.argv;
const read = (f) => JSON.parse(fs.readFileSync(path.join(runDir, f), 'utf8'));
const l2d = read('laptop-to-desk.json');
const d2l = read('desk-to-laptop.json');
const check = (doc, status) => { if (doc.summary.status !== status) throw new Error(`expected ${status}, got ${doc.summary.status}`); };
check(l2d, 'filtered');
check(d2l, 'ok');
const l2dPort = l2d.ports[0];
const d2lPort = d2l.ports[0];
const files = ['laptop-local.json', 'desk-local.json', 'laptop-to-desk.json', 'desk-to-laptop.json'].map((f) => path.join(runDir, f));
let report;
try {
  report = execFileSync('python3', [path.join(scriptsDir, 'mesh_report.py')], {
    input: files.map((f) => fs.readFileSync(f, 'utf8')).join('\n'), encoding: 'utf8',
  });
} catch (e) {
  if (e.status !== 1) throw e; // exit 1 means "found a problem": that is the result we want
  report = e.stdout;
}
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const reportHtml = esc(report.trimEnd()).split('\n').map((l) => {
  const cls = l.includes('[problem]') ? 'bad' : l.includes('filtered') ? 'bad' : l.includes('[ok]') ? 'good' : '';
  return `<div class="${cls}">${l || '&nbsp;'}</div>`;
}).join('');

const C = { local: '#38bdf8', link: '#f59e0b', report: '#a78bfa', red: '#f87171', green: '#4ade80' };
const chip = (x, y, w, h, color, title, sub, dashed = false) =>
  `<div class="chip" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;border-color:${color};${dashed ? 'border-style:dashed;' : ''}">` +
  `<b style="color:${color}">${title}</b><span>${sub}</span></div>`;
const card = (x, y, w, h, name, addr) =>
  `<div class="card" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px"><div class="cn">${name}</div><div class="ca">${addr}</div></div>`;
const json = (x, y, w, name) => `<div class="json" style="left:${x}px;top:${y}px;width:${w}px">${name}</div>`;
const ms = (n) => `${n} ms`;

const L = { x: 40, w: 320 }, D = { x: 520, w: 320 };
const html = `
<style>
*{box-sizing:border-box}body{margin:0;width:1280px;height:700px;position:relative;overflow:hidden;background:#0b1a24;color:#d7e3ec;font-family:system-ui,'Segoe UI',Helvetica,sans-serif}
.card{position:absolute;border:1.5px solid #2b4a5c;border-radius:14px;background:#10283a}
.cn{position:absolute;left:18px;top:12px;font-size:20px;font-weight:700;color:#fff}.ca{position:absolute;right:18px;top:17px;font:13px 'DejaVu Sans Mono',monospace;color:#7fa6bf}
.chip{position:absolute;border:2px solid;border-radius:10px;background:#0b1a24;padding:6px 14px}
.chip b{display:block;font:700 14.5px 'DejaVu Sans Mono',monospace}.chip span{display:block;margin-top:2px;font-size:13px;color:#9fb6c6}
.json{position:absolute;height:38px;border:1.5px solid #3b5a6c;border-radius:8px;background:#12303d;font:12.5px/35px 'DejaVu Sans Mono',monospace;text-align:center;color:#cfe3f0}
.lab{position:absolute;font:13px 'DejaVu Sans Mono',monospace;text-align:center;width:150px}
.out{position:absolute;left:900px;top:330px;width:340px;height:310px;border:1.5px solid #5b4a8a;border-radius:14px;background:#0d1117;padding:16px 16px;font:12.5px/1.55 'DejaVu Sans Mono',monospace;white-space:pre-wrap;color:#e6edf3}
.out .h{font:700 13px system-ui,sans-serif;color:#a78bfa;margin-bottom:12px;letter-spacing:.03em}
.bad{color:#ff8a80}.good{color:#4ade80}
.read{position:absolute;left:900px;top:50px;width:340px;font-size:14.5px;line-height:1.5;color:#b5c9d8}.read b{display:block;margin-bottom:8px;font:700 13px system-ui,sans-serif;letter-spacing:.03em;color:#7fa6bf}
.top{position:absolute;left:40px;top:16px;font:600 13px system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#7fa6bf}
.foot{position:absolute;left:40px;top:660px;width:820px;font-size:13px;line-height:1.45;color:#7fa6bf}
</style>
<div class="top">How the three scripts fit together</div>
${card(L.x, 50, L.w, 300, 'laptop', '192.168.50.10')}
${card(D.x, 50, D.w, 300, 'desk', '192.168.50.20')}
${chip(L.x + 16, 100, L.w - 32, 54, C.local, 'mesh_local.py', 'addresses, subnet, route, .local')}
${chip(L.x + 16, 168, L.w - 32, 54, C.link, 'mesh_link.py peer', 'can I reach the desk?')}
${chip(L.x + 16, 236, L.w - 32, 54, C.link, 'mesh_link.py listen 7001', 'stands in for the sharing tool', true)}
${chip(D.x + 16, 100, D.w - 32, 54, C.local, 'mesh_local.py', 'addresses, subnet, route, .local')}
${chip(D.x + 16, 168, D.w - 32, 54, C.link, 'mesh_link.py listen 7001', 'stands in for the sharing tool', true)}
${chip(D.x + 16, 236, D.w - 32, 54, C.link, 'mesh_link.py peer', 'can I reach the laptop?')}
<div class="lab" style="left:365px;top:150px;color:${C.red}">TCP 7001<br><b>${l2dPort.status}</b> ${ms(l2dPort.ms)}</div>
<div class="lab" style="left:365px;top:218px;color:${C.green}">TCP 7001<br><b>${d2lPort.status}</b> ${ms(d2lPort.ms)}</div>
${json(L.x + 8, 404, 150, 'laptop-local.json')}${json(L.x + 168, 404, 152, 'laptop-to-desk.json')}
${json(D.x + 8, 404, 150, 'desk-local.json')}${json(D.x + 168, 404, 152, 'desk-to-laptop.json')}
${chip(270, 520, 340, 66, C.report, 'mesh_report.py', 'reads the JSON on stdin, prints the matrix')}
<div class="read"><b>HOW IT READS THE MATRIX</b>One direction works and the other is silent, on one subnet. So the fault sits at the target of the failing direction. A router fault would break both ways.</div>
<div class="out"><div class="h">WHAT mesh_report.py PRINTS</div>${reportHtml}</div>
<svg width="1280" height="700" style="position:absolute;left:0;top:0">
 <defs>
  <marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker>
 </defs>
 <line x1="${L.x + L.w}" y1="195" x2="${D.x}" y2="195" stroke="${C.red}" stroke-width="3" stroke-dasharray="7 6" marker-end="url(#ar)"/>
 <line x1="${D.x}" y1="263" x2="${L.x + L.w}" y2="263" stroke="${C.green}" stroke-width="3" marker-end="url(#ar)"/>
 ${[[L.x + 83, 123], [L.x + 244, 123], [D.x + 83, 123], [D.x + 244, 123]].map(([x]) => `<line x1="${x}" y1="350" x2="${x}" y2="402" stroke="#4d7186" stroke-width="2" marker-end="url(#ar)"/>`).join('')}
 ${[[L.x + 83, 330], [L.x + 244, 400], [D.x + 83, 500], [D.x + 244, 550]].map(([x, tx]) => `<line x1="${x}" y1="444" x2="${tx}" y2="518" stroke="#4d7186" stroke-width="2" marker-end="url(#ar)"/>`).join('')}
 <line x1="610" y1="553" x2="898" y2="553" stroke="${C.report}" stroke-width="3" marker-end="url(#ar)"/>
</svg>
<div class="foot">Real data from a lab of two Linux network namespaces joined by a virtual cable. The desk drops inbound TCP 7001. The scripts never import each other: they pass JSON, and an agent (or you) runs them.</div>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 700 } });
await page.setContent(html);
await page.screenshot({ path: out });
await browser.close();
console.log('wrote', out, JSON.stringify({ l2d: [l2dPort.status, l2dPort.ms], d2l: [d2lPort.status, d2lPort.ms] }));
