// Pre-renders Mermaid diagrams to SVG files with headless Chrome (the site's CSP forbids running Mermaid in the page).
// usage: node render_mermaid.mjs <mermaid.min.js> <blocks.json> <out_dir> ; blocks.json = {hash: "mermaid source"}
import { spawn } from "child_process"; import fs from "fs"; import os from "os"; import path from "path"; import { createRequire } from "module";
const require = createRequire(process.env.WS_MODULE_DIR + "/");
const WebSocket = require("ws");
const [lib, blocksFile, outDir] = process.argv.slice(2);
const blocks = JSON.parse(fs.readFileSync(blocksFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
const html = path.join(os.tmpdir(), "mm_" + process.pid + ".html");
fs.writeFileSync(html, `<!doctype html><meta charset=utf-8><body><script src="file://${path.resolve(lib)}"></script></body>`);
const port = 9410 + (process.pid % 80), prof = fs.mkdtempSync(path.join(os.tmpdir(), "mmprof-"));
const chrome = spawn("google-chrome", ["--headless=new", "--no-sandbox", "--allow-file-access-from-files", `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, "file://" + html], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 3000));
const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); const ws = new WebSocket(tabs.find((t) => t.type === "page").webSocketDebuggerUrl); await new Promise((r) => ws.on("open", r));
let id = 0; const pend = new Map(); ws.on("message", (m) => { const d = JSON.parse(m); if (d.id && pend.has(d.id)) { pend.get(d.id)(d.result || d.error); pend.delete(d.id); } });
const ev = (e) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method: "Runtime.evaluate", params: { expression: e, awaitPromise: true, returnByValue: true } })); });
await ev(`mermaid.initialize({startOnLoad:false, theme:'neutral', securityLevel:'loose', flowchart:{htmlLabels:false, useMaxWidth:false}, sequence:{useMaxWidth:false}, themeVariables:{fontFamily:'Arial, sans-serif'}})`);
let ok = 0, bad = [];
for (const [h, code] of Object.entries(blocks)) {
  const r = await ev(`(async()=>{try{const o=await mermaid.render('g${h}', ${JSON.stringify(code)});return {svg:o.svg}}catch(e){return {err:String(e.message||e).slice(0,200)}}})()`);
  const v = r.result?.value;
  if (v?.svg) {
    let svg = v.svg.replace(/<br>/g, "<br/>").replace(/&nbsp;/g, "&#160;");
    const vb = svg.match(/viewBox="([\d.\- ]+)"/); if (vb) { const [, , w, h2] = vb[1].split(" ").map(Number); svg = svg.replace(/<svg ([^>]*?)>/, (m, a) => `<svg ${a.replace(/\sxmlns="[^"]*"/g, "").replace(/\s(width|height)="[^"]*"/g, "").replace(/style="[^"]*"/, "")} xmlns="http://www.w3.org/2000/svg" width="${Math.round(w)}" height="${Math.round(h2)}">`); }
    fs.writeFileSync(path.join(outDir, h + ".svg"), `<?xml version="1.0" encoding="UTF-8"?>\n` + svg); ok++;
  } else bad.push(h + ": " + (v?.err || "unknown"));
}
console.log(`rendered ${ok}/${Object.keys(blocks).length}`); bad.forEach((b) => console.log("FAILED", b));
chrome.kill(); process.exit(0);
