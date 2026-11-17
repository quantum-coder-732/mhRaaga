// Render saved songs to MP3 files, using the site's own player code in headless Chrome (same synth, same AI voice mix, same encoder
// as the Export MP3 button), so the file sounds exactly like the song in the app.
//
//   node tools/render_songs.mjs OUT_DIR TOKEN ID[:slug] [ID[:slug] ...]
//
// Needs: google-chrome, and the `ws` npm package reachable from NODE_PATH (npm i ws). TOKEN is a signed-in user's login token; the songs must be
// that user's. Voice lines are fetched through /api/tts (cached in S3, so a line that was voiced before costs nothing).
import WebSocket from "ws";
import { spawn } from "node:child_process";
import fs from "node:fs";

const [, , outDir, token, ...items] = process.argv;
if (!outDir || !token || !items.length) { console.error("usage: node render_songs.mjs OUT_DIR TOKEN ID[:slug] ..."); process.exit(1); }
fs.mkdirSync(outDir, { recursive: true });
const port = 9700 + Math.floor(Math.random() * 200);
const chrome = spawn("google-chrome", ["--headless=new", "--no-sandbox", "--remote-debugging-port=" + port, "--user-data-dir=/tmp/render-prof-" + Date.now(), "--autoplay-policy=no-user-gesture-required", "about:blank"], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 2500));
const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const ws = new WebSocket(tabs.find((t) => t.type === "page").webSocketDebuggerUrl); await new Promise((r) => ws.on("open", r));
let id = 0; const pend = new Map();
ws.on("message", (m) => { const d = JSON.parse(m.toString()); if (d.id && pend.has(d.id)) pend.get(d.id)(d.result); });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Runtime.enable"); await send("Page.enable");
await send("Page.navigate", { url: "https://www.mhraaga.in/developers.html" }); await new Promise((r) => setTimeout(r, 4000));
await send("Runtime.evaluate", { expression: `localStorage.setItem("mh_token", ${JSON.stringify(token)}); localStorage.setItem("mh_vg", "male");` });

const RENDER = (sid) => `(async () => {
  const [synth, neural] = await Promise.all([import("/synth.js"), import("/neural.js")]);
  if (!window.lamejs) await new Promise((ok, no) => { const s = document.createElement("script"); s.src = "/lame.min.js"; s.onload = ok; s.onerror = no; document.head.append(s); });
  const song = await (await fetch("/api/songs/${sid}", { headers: { Authorization: "Bearer " + localStorage.getItem("mh_token") } })).json();
  if (!song.score) return { error: "no score: " + JSON.stringify(song).slice(0, 120) };
  const lang = song.language || (song.brief && song.brief.language) || "hindi", style = neural.styleFor(song);
  const lines = song.score.lyrics.map((l, i) => [l, i]).filter(([l]) => l.dur > 0 && !l.tag);
  const bufs = await Promise.all(lines.map(([l]) => neural.loadLine(l.text, lang, style)));
  const voiced = bufs.filter(Boolean).length;
  const sr = 44100, D = song.score.duration + 2, oc = new OfflineAudioContext(2, Math.ceil(sr * D), sr), m = synth.master(oc, 0.9);
  synth.schedule(oc, m.bus, song.score, 0.05, 0);
  neural.scheduleVoice(oc, m, lines.map(([l], k) => ({ t: l.t, dur: l.dur, buf: bufs[k] })), 0.05, 0);
  const buf = await oc.startRendering(), pcm = (f) => { const o = new Int16Array(f.length); for (let i = 0; i < f.length; i++) o[i] = Math.max(-1, Math.min(1, f[i])) * 32767; return o; };
  const l = pcm(buf.getChannelData(0)), r = pcm(buf.getChannelData(1)), enc = new lamejs.Mp3Encoder(2, sr, 160), parts = [];
  for (let i = 0; i < l.length; i += 1152) { const b = enc.encodeBuffer(l.subarray(i, i + 1152), r.subarray(i, i + 1152)); if (b.length) parts.push(new Uint8Array(b)); }
  const e = enc.flush(); if (e.length) parts.push(new Uint8Array(e));
  const bytes = new Uint8Array(parts.reduce((n, p) => n + p.length, 0)); let o = 0; for (const p of parts) { bytes.set(p, o); o += p.length; }
  let bin = ""; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return { title: song.title, seconds: Math.round(song.score.duration), lines: lines.length, voiced, planner: song.planner || "", b64: btoa(bin) };
})()`;

for (const it of items) {
  const [sid, slug = it.split(":")[0]] = it.split(":");
  const r = await send("Runtime.evaluate", { expression: RENDER(sid), awaitPromise: true, returnByValue: true, timeout: 600000 });
  const v = r.result && r.result.value;
  if (!v || v.error || !v.b64) { console.log(sid, "FAILED", JSON.stringify(r.exceptionDetails || v).slice(0, 300)); continue; }
  const file = `${outDir}/${slug}.mp3`; fs.writeFileSync(file, Buffer.from(v.b64, "base64"));
  console.log(JSON.stringify({ id: sid, file, title: v.title, seconds: v.seconds, voiced_lines: `${v.voiced}/${v.lines}`, planner: v.planner, bytes: fs.statSync(file).size }));
}
chrome.kill(); process.exit(0);
