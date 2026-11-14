// Neural voice client. Asks /api/tts for real speech audio (cached in S3 and shared), decodes it, and plays it through WebAudio so it
// is mixed with the music (reverb, ducking, export), instead of the device's own speech. If anything fails the callers fall back
// to the device voice, so a song or story never goes silent.
import { duckAt } from "./synth.js";
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
export const voiceMode = () => store.get("mh_vg") || "male";            // male | female | device
export const setVoiceMode = (v) => store.set("mh_vg", v);
export let neuralError = "";
let info = null;
export async function neuralOn() {
  if (voiceMode() === "device" || !store.get("mh_token")) return false;
  if (!info) info = fetch("/api/tts/info").then((r) => (r.ok ? r.json() : { enabled: false })).catch(() => ({ enabled: false }));
  return !!(await info).enabled;
}
const decoder = () => new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(1, 1, 24000);
const cache = new Map();            // "mode|lang|style|text" -> Promise<AudioBuffer | null>
let active = 0; const waiters = [];
const slot = () => new Promise((res) => (active < 2 ? (active++, res()) : waiters.push(res)));
const free = () => { const n = waiters.shift(); n ? n() : active--; };

export function loadLine(text, lang, style) {
  text = text.replace(/\[[^\]]*\]/g, "").trim(); if (!text) return Promise.resolve(null);
  const mode = voiceMode(), key = [mode, lang, style, text].join("|");
  if (!cache.has(key)) cache.set(key, (async () => {
    await slot();
    try {
      let r, d;
      for (let attempt = 0; attempt < 4; attempt++) {                  // a busy service (503) is worth another try
        r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + store.get("mh_token") }, body: JSON.stringify({ text, lang, style, voice: mode }) });
        d = await r.json().catch(() => ({})); if (r.status !== 503 || attempt === 3) break; await new Promise((x) => setTimeout(x, 1500 * (attempt + 1)));
      }
      if (!r.ok) throw new Error(d.error || "Voice error " + r.status);
      const a = await fetch(d.url); if (!a.ok) throw new Error("Voice audio " + a.status);
      return await decoder().decodeAudioData(await a.arrayBuffer());
    } catch (e) { neuralError = e.message; cache.delete(key); return null; }
    finally { free(); }
  })());
  return cache.get(key);
}

// Break long text into spoken chunks of at most `max` characters, on sentence ends where possible.
export function chunks(text, max = 200) {
  const out = []; let cur = "";
  const add = (t) => { if ((cur + " " + t).trim().length > max && cur) { out.push(cur); cur = t; } else cur = (cur + " " + t).trim(); };
  for (const s of text.match(/[^.!?।\n]+[.!?।]?/g) || [text]) {
    const t = s.trim(); if (!t) continue;
    if (t.length <= max) { add(t); continue; }
    for (const w of t.split(/\s+/)) add(w);          // a very long sentence: pack it word by word
  }
  if (cur) out.push(cur); return out.filter(Boolean);
}

// Play a decoded line at `when` (context time). If it is longer than the slot `fit`, speed it up a little (never more than 20%).
export function playBuffer(ctx, out, buf, when, fit = 0) {
  const s = ctx.createBufferSource(); s.buffer = buf; if (fit && buf.duration > fit) s.playbackRate.value = Math.min(1.2, buf.duration / fit);
  s.connect(out); s.start(when); return { src: s, end: when + buf.duration / s.playbackRate.value };
}
// Place voice lines on a context (live or offline). Lines never overlap: each starts at its slot, or just after the previous line if that ran long.
// A line longer than its slot is sped up a little (at most 20%). The music ducks under each line. Returns [[start, end], ...].
export const DUCK = 0.38;
export function scheduleVoice(c, m, items, startTime, from) {
  let cursor = -1, placed = [];
  for (const it of items.slice().sort((a, b) => a.t - b.t)) {
    if (!it.buf || it.t < from - 0.05) continue;
    const when = Math.max(startTime + (it.t - from), cursor + 0.12), r = playBuffer(c, m.voice, it.buf, when, it.dur + 0.3);
    duckAt(m, Math.max(0, when - 0.1), r.end - when + 0.2, DUCK); cursor = r.end; placed.push([when, r.end]);
  }
  return placed;
}
export const styleFor = (song) => (song?.score?.meta?.poem ? "poem" : /devotion|krishna|bhajan|meditat|prayer/i.test(`${song?.brief?.mood || ""} ${song?.prompt || ""} ${song?.title || ""}`) ? "bhajan" : "song");
