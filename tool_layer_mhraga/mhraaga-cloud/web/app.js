import { master, schedule } from "./synth.js";

const $ = (id) => document.getElementById(id);
const API = "/api";
const SVARA = ["Sa", "Re♭", "Re", "Ga♭", "Ga", "Ma", "Ma♯", "Pa", "Dha♭", "Dha", "Ni♭", "Ni"];
const SPEECH_LANG = { hindi: "hi-IN", marathi: "mr-IN", sanskrit: "hi-IN", english: "en-IN", telugu: "te-IN", gujarati: "gu-IN", kannada: "kn-IN", tamil: "ta-IN", "": "en-IN" };
let token = null, me = null, song = null, catalog = null;
const store = { get: (k) => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} } };

// ---------------------------------------------------------------- api
async function api(path, { method = "GET", body } = {}) {
  const r = await fetch(API + path, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  let data = {}; try { data = await r.json(); } catch {}
  if (r.status === 401 && token) { signOut(); throw new Error(data.error || "Please sign in."); }
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  return data;
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 3500); }
const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const chip = (txt, cls = "") => { const c = document.createElement("span"); c.className = "chip " + cls; c.textContent = txt; return c; };

// ---------------------------------------------------------------- auth (sign-in lives on login.html)
function signOut() { try { stop(); } catch {} token = null; me = null; song = null; store.set("mh_token", null); location.href = "login.html?next=app.html"; }

async function enter() {
  me = await api("/me");
  const w = document.getElementById("whoami"); if (w) w.textContent = `${me.name} · ${me.composed_today}/${me.daily_limit} today`;
  $("app").hidden = false;
  if (!catalog) await loadCatalog();
  await refreshLibrary(); refreshPlaylist();
}

async function loadCatalog() {
  catalog = await api("/ragas");
  for (const r of catalog.classical) { const o = document.createElement("option"); o.value = r.name; o.textContent = `${r.name} · ${r.time}`; $("og-classical").append(o); }
  const talas = ["teental", "keherwa", "dadra", "rupak", "jhaptal", "ektal", "adi"];
  for (const t of talas) { const o = document.createElement("option"); o.value = t; o.textContent = t; $("tala").append(o); }
}

// ---------------------------------------------------------------- compose form
function raga() {
  const v = $("raga").value;
  return v === "gopi" ? `gopi:${clampInt($("num").value, 1, 16000)}` : v === "mela" ? `mela:${clampInt($("num").value, 1, 72)}` : v;
}
const clampInt = (v, a, b) => Math.min(b, Math.max(a, parseInt(v, 10) || a));
$("raga").onchange = () => {
  const v = $("raga").value; $("num-wrap").hidden = !(v === "gopi" || v === "mela");
  $("num").max = v === "mela" ? 72 : 16000; $("num-label").textContent = v === "mela" ? "Melakarta number" : "Gopī number";
  if (v === "gopi" && !$("num").value) $("num").value = 1;
};
$("dice").onclick = () => { $("num").value = 1 + Math.floor(Math.random() * ($("raga").value === "mela" ? 72 : 16000)); };
$("tempo").oninput = () => ($("tempo-v").textContent = +$("tempo").value === 40 ? "auto" : $("tempo").value + " bpm");
$("dur").oninput = () => ($("dur-v").textContent = $("dur").value + " s");

async function compose(extra = {}) {
  const prompt = $("prompt").value.trim();
  if (prompt.length < 3) { $("status").className = "err"; $("status").textContent = "Describe the song first."; return; }
  $("go").disabled = true; $("surprise").disabled = true; $("status").className = ""; $("status").textContent = "Composing… the planner is choosing raga, tāla and words.";
  try {
    const body = { prompt, raga: raga(), tala: $("tala").value, language: $("language").value, lead: $("lead").value, tonic: +$("tonic").value || undefined,
      tempo: +$("tempo").value === 40 ? undefined : +$("tempo").value, duration: +$("dur").value, instrumental: $("instr").checked, lyrics: $("lyrics").value, ...extra };
    song = await api("/compose", { method: "POST", body });
    $("status").textContent = ""; await show(song); refreshLibrary(); me = await api("/me");
    const w = document.getElementById("whoami"); if (w) w.textContent = `${me.name} · ${me.composed_today}/${me.daily_limit} today`;
    await play();
  } catch (e) { $("status").className = "err"; $("status").textContent = e.message; } finally { $("go").disabled = false; $("surprise").disabled = false; }
}
$("go").onclick = () => compose();
$("surprise").onclick = () => { $("raga").value = "gopi"; $("raga").onchange(); $("dice").click(); if ($("prompt").value.trim().length < 3) $("prompt").value = "Krishna's flute calling the gopis at dawn"; compose(); };

// ---------------------------------------------------------------- library
async function refreshPlaylist() {
  try {
    const { songs } = await api("/playlist"); const ul = $("plist"); ul.replaceChildren(); $("pempty").hidden = songs.length > 0; $("pempty").textContent = "No songs yet.";
    for (const s of songs) { const li = document.createElement("li"); const b = document.createElement("button"); b.type = "button";
      const l = document.createElement("span"); l.textContent = s.title; const r = document.createElement("small"); r.textContent = `${s.raga} · ${s.tala}`; b.append(l, r);
      b.onclick = async () => { try { song = await api("/playlist/" + s.id); await show(song); await play(); } catch (e) { toast(e.message); } };
      li.append(b); ul.append(li); }
  } catch { $("pempty").textContent = "Playlist unavailable."; }
}
async function refreshLibrary() {
  const { songs } = await api("/songs"); const ul = $("songs"); ul.replaceChildren(); $("empty").hidden = songs.length > 0;
  for (const s of songs) {
    const li = document.createElement("li"); if (song && song.id === s.id) li.className = "on";
    const b = document.createElement("button"); const l = document.createElement("span"), r = document.createElement("small");
    l.textContent = s.title; r.textContent = `${s.raga} · ${s.tala} · ${fmt(s.duration)}`; b.append(l, r);
    b.onclick = async () => { try { song = await api("/songs/" + s.id); await show(song); await play(); } catch (e) { toast(e.message); } };
    li.append(b); ul.append(li);
  }
}

// ---------------------------------------------------------------- player
let ctx = null, bus = null, volNode = null, startAt = 0, offset = 0, playing = false, raf = 0, timers = [];
async function show(s) {
  stop(); song = s; $("player").hidden = false; $("s-title").textContent = s.title;
  const m = s.score.meta, chips = $("chips"); chips.replaceChildren(chip(m.raga, "gold"), chip(m.tala), chip(m.tempo + " bpm"), chip(`Sa ${m.sa} Hz`), chip(m.mood));
  $("s-info").textContent = m.gopi ? `Gopī ${m.gopi} of 16,000 · ascent from Mela ${m.mela?.[0] ?? ""}, descent from ${m.mela?.[1] ?? ""} · vādī ${SVARA[m.vadi % 12]}, samvādī ${SVARA[m.samvadi % 12]} · ${m.time}`
    : `vādī ${SVARA[m.vadi % 12]}, samvādī ${SVARA[m.samvadi % 12]} · best at ${m.time} · planned by ${s.source === "fallback" ? "built-in rules" : s.source}`;
  $("lyrics-out").textContent = (s.brief.lyrics || "(instrumental)"); $("lyric-now").textContent = ""; offset = 0; draw(0); $("clock").textContent = "0:00"; $("seek").value = 0;
  for (const li of $("songs").children) li.classList.remove("on");
  document.title = `${s.title} · mhRaaga`;
  $("player").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function pickVoice() {
  const sel = $("voice"), want = SPEECH_LANG[song?.brief?.language || ""] || "en-IN";
  const voices = speechSynthesis.getVoices(); if (!voices.length) return null;
  if (!sel.options.length) { for (const v of voices) { const o = document.createElement("option"); o.value = v.name; o.textContent = `${v.name} (${v.lang})`; sel.append(o); } }
  const match = voices.find((v) => v.lang.replace("_", "-") === want) || voices.find((v) => v.lang.startsWith(want.slice(0, 2)));
  if (match && !sel.dataset.user) sel.value = match.name;
  return voices.find((v) => v.name === sel.value) || null;
}
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => { $("voice").replaceChildren(); pickVoice(); };
$("voice").onchange = () => ($("voice").dataset.user = "1");

function speakLine(text, durSec) {
  if (!("speechSynthesis" in window) || !$("sing").checked) return;
  const u = new SpeechSynthesisUtterance(text.replace(/\[.*?\]/g, ""));
  const v = pickVoice(); if (v) { u.voice = v; u.lang = v.lang; } else u.lang = SPEECH_LANG[song.brief.language || ""] || "en-IN";
  u.rate = Math.min(1.25, Math.max(0.55, text.length / (Math.max(1, durSec) * 6.5))); u.pitch = 1.05; u.volume = 0.9;
  speechSynthesis.speak(u);
}

async function play() {
  if (!song) return; stop(false);
  ctx = new (window.AudioContext || window.webkitAudioContext)(); await ctx.resume();
  const m = master(ctx, $("vol").value / 100); bus = m.bus; volNode = m.out;
  startAt = ctx.currentTime + 0.12 - offset; schedule(ctx, bus, song.score, ctx.currentTime + 0.12, offset);
  playing = true; $("play").textContent = "❚❚"; $("play").setAttribute("aria-label", "Pause");
  timers = song.score.lyrics.filter((l) => !l.tag && l.t + l.dur > offset).map((l) => setTimeout(() => speakLine(l.text, l.dur), Math.max(0, (l.t - offset) * 1000)));
  loop();
}
function pause() { if (!playing) return; offset = ctx.currentTime - startAt; stop(false, true); }
function stop(reset = true, keep = false) {
  playing = false; cancelAnimationFrame(raf); timers.forEach(clearTimeout); timers = [];
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  if (ctx) { ctx.close().catch(() => {}); ctx = null; }
  $("play").textContent = "▶"; $("play").setAttribute("aria-label", "Play");
  if (reset && !keep) { offset = 0; $("seek").value = 0; $("clock").textContent = "0:00"; $("lyric-now").textContent = ""; if (song) draw(0); }
}
$("play").onclick = () => (playing ? pause() : play());
$("stop").onclick = () => stop();
$("vol").oninput = () => { if (volNode) volNode.gain.value = $("vol").value / 100; };
$("seek").onchange = () => { if (!song) return; offset = ($("seek").value / 1000) * song.score.duration; if (playing) play(); else { draw(offset); $("clock").textContent = fmt(offset); } };

function loop() {
  if (!playing) return; const t = ctx.currentTime - startAt, D = song.score.duration;
  if (t >= D + 0.5) { stop(); return; }
  $("seek").value = Math.round((t / D) * 1000); $("clock").textContent = `${fmt(t)} / ${fmt(D)}`;
  const cur = [...song.score.lyrics].reverse().find((l) => !l.tag && l.t <= t); $("lyric-now").textContent = cur && t < cur.t + cur.dur + 2 ? cur.text : "";
  draw(t); raf = requestAnimationFrame(loop);
}

function draw(t) {
  const cv = $("roll"), g = cv.getContext("2d"), W = cv.width, H = cv.height, sc = song.score, sa = sc.sa, span = 14, x = (tt) => W * 0.28 + ((tt - t) / span) * W * 0.72;
  const py = (hz) => H - 18 - ((12 * Math.log2(hz / sa) + 14) / 30) * (H - 36);
  g.clearRect(0, 0, W, H); g.fillStyle = "#0d0a24"; g.fillRect(0, 0, W, H);
  g.font = "11px system-ui"; g.textBaseline = "middle";
  for (let s = -12; s <= 14; s++) { // staff lines for the notes of this raga
    const inRaga = sc.meta.scale.includes(((s % 12) + 12) % 12); if (!inRaga) continue;
    const y = py(sa * Math.pow(2, s / 12)); g.strokeStyle = s % 12 === 0 ? "#6b5b2a" : "#2a2468"; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    if (s >= 0 && s <= 12) { g.fillStyle = "#8a80c4"; g.fillText(SVARA[((s % 12) + 12) % 12] + (s === 12 ? "'" : ""), 6, y - 7); }
  }
  for (const [tt, hz, d, orn] of sc.lead) {
    if (tt > t + span || tt + d < t - 4) continue;
    const on = tt <= t && t < tt + d, x0 = x(tt), w = Math.max(5, (d / span) * W * 0.72 - 2), y = py(hz);
    g.fillStyle = on ? "#f4b942" : tt < t ? "#5b4f99" : "#2ec4b6"; g.globalAlpha = on ? 1 : 0.85;
    g.beginPath(); g.roundRect(x0, y - 5, w, 10, 5); g.fill(); g.globalAlpha = 1;
    if (orn === 1) { g.strokeStyle = "#ff6b8a"; g.beginPath(); g.moveTo(x0 - 8, y + 12); g.lineTo(x0, y); g.stroke(); }
  }
  for (const [tt, , , v] of sc.tabla) { if (tt < t - 1 || tt > t + span) continue; g.fillStyle = v === 1 ? "#ff6b8a" : "#7d72c4"; g.fillRect(x(tt) - 1, H - 10, 2, v === 1 ? 10 : 6); }
  g.strokeStyle = "#f6efe0"; g.beginPath(); g.moveTo(W * 0.28, 0); g.lineTo(W * 0.28, H); g.stroke();
  const sec = sc.sections.find((s) => t >= s.t0 && t < s.t1); if (sec) { g.fillStyle = "#f4b942"; g.font = "12px system-ui"; g.fillText(sec.name.toUpperCase(), W - 70, 14); }
}

// ---------------------------------------------------------------- wav export
$("wav").onclick = async () => {
  if (!song) return; $("wav").disabled = true; toast("Rendering WAV (instruments only; the speech voice can't be captured by the browser)…");
  try {
    const sr = 44100, D = song.score.duration + 2, oc = new OfflineAudioContext(2, Math.ceil(sr * D), sr), m = master(oc, 0.9);
    schedule(oc, m.bus, song.score, 0.05, 0); const buf = await oc.startRendering();
    const L = buf.getChannelData(0), R = buf.getChannelData(1), n = L.length, dv = new DataView(new ArrayBuffer(44 + n * 4));
    const w = (o, s) => [...s].forEach((c, i) => dv.setUint8(o + i, c.charCodeAt(0)));
    w(0, "RIFF"); dv.setUint32(4, 36 + n * 4, true); w(8, "WAVEfmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 2, true);
    dv.setUint32(24, sr, true); dv.setUint32(28, sr * 4, true); dv.setUint16(32, 4, true); dv.setUint16(34, 16, true); w(36, "data"); dv.setUint32(40, n * 4, true);
    for (let i = 0; i < n; i++) { dv.setInt16(44 + i * 4, Math.max(-1, Math.min(1, L[i])) * 32767, true); dv.setInt16(46 + i * 4, Math.max(-1, Math.min(1, R[i])) * 32767, true); }
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([dv], { type: "audio/wav" }));
    a.download = song.title.replace(/[^\w]+/g, "_").slice(0, 40) + ".wav"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  } catch (e) { toast("WAV export failed: " + e.message); } finally { $("wav").disabled = false; }
};
$("del").onclick = async () => {
  if (!song || !confirm(`Delete "${song.title}"?`)) return;
  try { await api("/songs/" + song.id, { method: "DELETE" }); stop(); $("player").hidden = true; song = null; await refreshLibrary(); toast("Deleted."); } catch (e) { toast(e.message); }
};

// ---------------------------------------------------------------- speech to text
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const STT_LANG = { hindi: "hi-IN", marathi: "mr-IN", sanskrit: "hi-IN", english: "en-IN", telugu: "te-IN", gujarati: "gu-IN", kannada: "kn-IN", tamil: "ta-IN", "": "en-IN" };
let rec = null;
function dictate(btn, area) {
  if (!SR) { toast("Speech input needs Chrome, Edge or Safari."); return; }
  if (rec) { rec.stop(); return; }
  rec = new SR(); rec.lang = STT_LANG[$("language").value]; rec.interimResults = true; rec.continuous = true;
  const base = area.value ? area.value.trimEnd() + " " : ""; let final = "";
  btn.classList.add("rec"); toast("Listening… tap the mic again to stop. (Your browser's speech service processes the audio.)");
  rec.onresult = (e) => { let interim = ""; for (let i = e.resultIndex; i < e.results.length; i++) { const r = e.results[i]; r.isFinal ? (final += r[0].transcript + " ") : (interim += r[0].transcript); } area.value = (base + final + interim).trim(); };
  rec.onerror = (e) => toast(e.error === "not-allowed" ? "Microphone permission was blocked." : e.error === "no-speech" ? "Didn't catch anything." : "Speech error: " + e.error);
  rec.onend = () => { btn.classList.remove("rec"); rec = null; };
  rec.start();
}
$("mic-prompt").onclick = () => dictate($("mic-prompt"), $("prompt"));
$("mic-lyrics").onclick = () => dictate($("mic-lyrics"), $("lyrics"));

// ---------------------------------------------------------------- boot
(async () => {
  token = store.get("mh_token");
  if (!token) { location.href = "login.html?next=app.html"; return; }
  try { await enter(); } catch { signOut(); return; }
  const q = new URLSearchParams(location.search).get("raga");
  if (q) { const known = [...$("raga").options].some((o) => o.value === q);
    if (known) $("raga").value = q; else { const m = /^(gopi|mela):(\d+)$/.exec(q); if (m) { $("raga").value = m[1]; $("raga").onchange(); $("num").value = m[2]; } } }
})();
