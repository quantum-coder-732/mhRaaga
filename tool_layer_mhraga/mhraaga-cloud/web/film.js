// Film studio: storyboard timeline, canvas effects, Box2D (planck.js) particles, colour grade + scope, WebM export.
import { $, api, toast, el } from "./api.js";
import * as planck from "./planck.mjs";
import { master, schedule, duckNow, releaseNow } from "./synth.js";
import { bestVoice } from "./voice.js";
import { neuralOn, loadLine, chunks } from "./neural.js";

const FX = { glow: "Glow", vignette: "Vignette", grain: "Film grain", blur: "Soft focus", lightleak: "Light leak", particles: "Physics petals", kenburns: "Slow zoom", fade: "Fade in/out", bw: "Black & white", warm: "Warm", cool: "Cool" };
const W = 960, H = 540, cv = $("cv"), cx = cv.getContext("2d", { willReadFrequently: true });
let proj = { title: "Untitled film", language: "english", scenes: [], music: true }, cur = 0, fid = null, playing = false, t0 = 0, tNow = 0, raf = 0, actx = null, dest = null, bedTimer = 0, rec = null;
const total = () => proj.scenes.reduce((a, s) => a + s.duration, 0);
const say = (m) => ($("f-status").textContent = m), fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const blank = () => ({ title: "New scene", text: "", narration: "", duration: 6, effects: ["fade", "vignette"], bg: { c1: "#241046", c2: "#120f2e", image: "" }, grade: { exposure: 0, contrast: 0, saturation: 0, hue: 0 }, mood: "" });
const imgCache = new Map();
const imageFor = (s) => { const u = s.bg.image; if (!u) return null; if (!imgCache.has(u)) { const i = new Image(); i.src = u; imgCache.set(u, i); } const i = imgCache.get(u); return i.complete ? i : null; };

// ---- grain tile
const grain = document.createElement("canvas"); grain.width = grain.height = 128;
{ const g = grain.getContext("2d"), d = g.createImageData(128, 128); for (let i = 0; i < d.data.length; i += 4) { const v = Math.random() * 255; d.data.set([v, v, v, 38], i); } g.putImageData(d, 0, 0); }

// ---- Box2D world for the particle effect (metres: 50 px = 1 m, y up)
let world = null, bodies = [];
function newWorld() {
  world = new planck.World({ gravity: planck.Vec2(0, -3.2) }); bodies = [];
  const ground = world.createBody(); ground.createFixture(planck.Edge(planck.Vec2(-1, 0.4), planck.Vec2(W / 50 + 1, 0.4)), { friction: 0.6, restitution: 0.35 });
  ground.createFixture(planck.Edge(planck.Vec2(-0.2, 0), planck.Vec2(-0.2, 20)), {}); ground.createFixture(planck.Edge(planck.Vec2(W / 50 + 0.2, 0), planck.Vec2(W / 50 + 0.2, 20)), {});
}
function spawn(n) { for (let i = 0; i < n; i++) { const b = world.createDynamicBody({ position: planck.Vec2(Math.random() * W / 50, H / 50 + Math.random() * 3), angle: Math.random() * 6, angularVelocity: (Math.random() - 0.5) * 2 });
  b.createFixture(planck.Circle(0.12 + Math.random() * 0.14), { density: 0.6, restitution: 0.45, friction: 0.4 }); b.glyph = Math.random() < 0.5 ? "✿" : "♪"; bodies.push(b); } }

// ---- rendering
function grade(s, extra = "") { const g = s.grade, fx = s.effects; const f = [`brightness(${1 + g.exposure})`, `contrast(${1 + g.contrast})`, `saturate(${1 + g.saturation})`, `hue-rotate(${g.hue * 180}deg)`];
  if (fx.includes("bw")) f.push("grayscale(1)"); if (fx.includes("warm")) f.push("sepia(.35)", "saturate(1.15)"); if (fx.includes("cool")) f.push("hue-rotate(18deg)", "saturate(.95)"); if (fx.includes("blur")) f.push("blur(1.6px)"); return f.join(" ") + " " + extra; }
function frame(s, t, dur) {
  const p = Math.min(1, t / dur), fx = s.effects;
  cx.save(); cx.filter = grade(s); cx.globalAlpha = 1;
  const zoom = fx.includes("kenburns") ? 1 + p * 0.12 : 1; cx.translate(W / 2, H / 2); cx.scale(zoom, zoom); cx.translate(-W / 2, -H / 2);
  const im = imageFor(s);
  if (im) { const r = Math.max(W / im.width, H / im.height); cx.drawImage(im, (W - im.width * r) / 2, (H - im.height * r) / 2, im.width * r, im.height * r); }
  else { const g = cx.createLinearGradient(0, 0, W * 0.7, H); g.addColorStop(0, s.bg.c1); g.addColorStop(1, s.bg.c2); cx.fillStyle = g; cx.fillRect(0, 0, W, H); }
  cx.restore(); cx.filter = "none";
  if (fx.includes("lightleak")) { cx.save(); cx.globalCompositeOperation = "screen"; const x = (0.2 + 0.6 * Math.sin(p * 3.1 + 1)) * W, g = cx.createRadialGradient(x, H * 0.3, 10, x, H * 0.3, 380); g.addColorStop(0, "rgba(255,170,90,.55)"); g.addColorStop(1, "rgba(255,100,150,0)"); cx.fillStyle = g; cx.fillRect(0, 0, W, H); cx.restore(); }
  if (fx.includes("particles") && world) { cx.save(); cx.font = "26px serif"; cx.textAlign = "center"; cx.textBaseline = "middle"; cx.fillStyle = "rgba(255,225,170,.9)";
    for (const b of bodies) { const q = b.getPosition(); cx.save(); cx.translate(q.x * 50, H - q.y * 50); cx.rotate(-b.getAngle()); cx.fillText(b.glyph, 0, 0); cx.restore(); } cx.restore(); }
  if (s.text) { const a = Math.min(1, t / 0.8) * (fx.includes("fade") ? Math.min(1, (dur - t) / 0.8) : 1); cx.save(); cx.globalAlpha = Math.max(0, a);
    cx.font = "italic 38px Georgia, 'Noto Serif Devanagari', serif"; cx.textAlign = "center"; cx.fillStyle = "#f3d27a"; if (fx.includes("glow")) { cx.shadowColor = "#ffcf66"; cx.shadowBlur = 28; }
    wrap(s.text, W * 0.78).forEach((l, i, arr) => cx.fillText(l, W / 2, H - 80 - (arr.length - 1 - i) * 46)); cx.restore(); }
  if (fx.includes("vignette")) { const g = cx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95); g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,.65)"); cx.fillStyle = g; cx.fillRect(0, 0, W, H); }
  if (fx.includes("grain")) { cx.save(); cx.globalCompositeOperation = "overlay"; cx.fillStyle = cx.createPattern(grain, "repeat"); cx.translate(-Math.random() * 128, -Math.random() * 128); cx.fillRect(0, 0, W + 128, H + 128); cx.restore(); }
  if (fx.includes("fade")) { const a = Math.max(Math.min(1, 1 - t / 0.6), Math.min(1, 1 - (dur - t) / 0.6), 0); if (a > 0) { cx.fillStyle = `rgba(0,0,0,${a})`; cx.fillRect(0, 0, W, H); } }
  for (const r of ripples) { const k = (performance.now() - r.t) / 700; if (k < 1) { cx.strokeStyle = `rgba(255,220,150,${1 - k})`; cx.lineWidth = 3; cx.beginPath(); cx.arc(r.x, r.y, 10 + k * 70, 0, 7); cx.stroke(); } }
}
function wrap(t, maxw) { const words = t.split(" "), lines = []; let l = ""; cx.save(); cx.font = "italic 38px Georgia"; for (const w of words) { if (cx.measureText((l + " " + w).trim()).width > maxw && l) { lines.push(l); l = w; } else l = (l + " " + w).trim(); } cx.restore(); if (l) lines.push(l); return lines; }
const ripples = []; cv.onclick = (e) => { const r = cv.getBoundingClientRect(); ripples.push({ x: (e.clientX - r.left) * W / r.width, y: (e.clientY - r.top) * H / r.height, t: performance.now() }); if (!playing) draw(); };   // click FX
function locate(t) { let a = 0; for (let i = 0; i < proj.scenes.length; i++) { const d = proj.scenes[i].duration; if (t < a + d || i === proj.scenes.length - 1) return { i, local: Math.max(0, t - a), start: a }; a += d; } return { i: 0, local: 0, start: 0 }; }
function scope() { const sc = $("scope").getContext("2d"), d = cx.getImageData(0, 0, W, H, { colorSpace: "srgb" }).data, bins = new Array(64).fill(0);
  for (let i = 0; i < d.length; i += 64) bins[Math.min(63, ((0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 4) | 0)]++;
  const m = Math.max(...bins) || 1; sc.fillStyle = "#0b0920"; sc.fillRect(0, 0, 256, 64); sc.fillStyle = "#f4b942"; bins.forEach((b, i) => sc.fillRect(i * 4, 64 - (b / m) * 60, 3, (b / m) * 60)); }
function draw() { if (!proj.scenes.length) { cx.fillStyle = "#120f2e"; cx.fillRect(0, 0, W, H); cx.fillStyle = "#b3a9d6"; cx.font = "24px system-ui"; cx.textAlign = "center"; cx.fillText("Auto-direct a film, or add a scene", W / 2, H / 2); return; }
  const l = locate(tNow), s = proj.scenes[l.i]; frame(s, l.local, s.duration); scope(); $("t-clock").textContent = `${fmt(tNow)} / ${fmt(total())}`; $("t-seek").value = total() ? (tNow / total()) * 1000 : 0; }

// ---- playback (+ optional export)
let lastScene = -1, lastTs = 0, bedM = null;
function tick(ts) {
  if (!playing) return; const dt = Math.min(0.1, (ts - lastTs) / 1000); lastTs = ts; tNow += dt; if (tNow >= total()) return stop(true);
  const l = locate(tNow); if (l.i !== lastScene) { lastScene = l.i; select(l.i, true); const s = proj.scenes[l.i]; newWorld(); if (s.effects.includes("particles")) spawn(36); if ($("o-tts").checked && s.narration) speakLine(s.narration); }
  if (world) world.step(dt, 8, 3); draw(); raf = requestAnimationFrame(tick);
}
function deviceSpeak(t) { if (!("speechSynthesis" in window)) return; speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(t), v = bestVoice(speechSynthesis.getVoices(), ({ hindi: "hi-IN", marathi: "mr-IN", telugu: "te-IN", gujarati: "gu-IN", kannada: "kn-IN", tamil: "ta-IN" })[proj.language] || "en-IN", $("o-voice").value); u.onstart = () => bedM && actx && duckNow(actx, bedM, 0.38); u.onend = () => bedM && actx && releaseNow(actx, bedM); if (v) { u.voice = v; u.lang = v.lang; } speechSynthesis.speak(u); }
// AI narration: real speech audio, so it is mixed with the music, ducks it, and is recorded in the WebM export. Falls back to the device voice.
let narRun = 0;
const lname = () => proj.language || "english";
async function preloadNarration() {
  const sc = proj.scenes.filter((s) => s.narration); if (!sc.length) return; say("Preparing the AI voice…");
  await Promise.all(chunks(sc[0].narration, 200).map((c) => loadLine(c, lname(), "narration")));        // the first scene is ready before the film starts
  for (const s of sc.slice(1)) chunks(s.narration, 200).forEach((c) => loadLine(c, lname(), "narration"));   // the rest load while it plays
  say("");
}
async function speakLine(t) {
  if (actx && (await neuralOn())) {
    const my = ++narRun;
    for (const p of chunks(t, 200)) {
      if (!playing || my !== narRun || !actx) return;
      const b = await loadLine(p, lname(), "narration"); if (!b) { deviceSpeak(p); return; }
      if (!playing || my !== narRun || !actx) return;
      const g = actx.createGain(), src = actx.createBufferSource(); src.buffer = b; src.connect(g); g.connect(actx.destination); if (dest) g.connect(dest);
      bedM && duckNow(actx, bedM, 0.38); src.start(); await new Promise((res) => (src.onended = res)); bedM && actx && releaseNow(actx, bedM);
    }
    return;
  }
  deviceSpeak(t);
}
async function startBed() {
  if (!$("o-music").checked) return;
  try { const { songs } = await api("/playlist", { auth: false }); if (!songs.length) return; const full = await api("/playlist/" + songs[Math.floor(Math.random() * songs.length)].id, { auth: false });
    const m = bedM = master(actx, 0.25); if (dest) m.out.connect(dest); schedule(actx, m.bus, { ...full.score, lyrics: [] }, actx.currentTime + 0.1, 0); bedTimer = setTimeout(() => playing && startBed(), Math.max(20, full.score.duration - 2) * 1000); } catch {}
}
async function play(exporting = false) {
  if (!proj.scenes.length) return; stop(false); if (tNow >= total()) tNow = 0; playing = true; lastScene = -1; lastTs = performance.now(); $("t-play").textContent = "❚❚";
  actx = new AudioContext(); await actx.resume(); dest = exporting ? actx.createMediaStreamDestination() : null; if ($("o-tts").checked) { try { if (await neuralOn()) await preloadNarration(); } catch {} } await startBed(); raf = requestAnimationFrame(tick);
  if (exporting) { const stream = cv.captureStream(30); if (dest) dest.stream.getAudioTracks().forEach((t) => stream.addTrack(t)); const parts = [];
    rec = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus") ? "video/webm;codecs=vp9,opus" : "video/webm" }); rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
    rec.onstop = () => { const a = el("a", { href: URL.createObjectURL(new Blob(parts, { type: "video/webm" })), download: (proj.title || "film").replace(/[^\p{L}\p{N}]+/gu, "_") + ".webm" }); a.click(); $("x-status").textContent = "Exported."; rec = null; }; rec.start(1000); $("x-status").textContent = "Recording in real time…"; }
}
function stop(end = false) { narRun++; playing = false; cancelAnimationFrame(raf); clearTimeout(bedTimer); try { speechSynthesis.cancel(); } catch {} try { actx && actx.close(); } catch {} actx = null; if (rec && rec.state !== "inactive") rec.stop(); $("t-play").textContent = "▶"; if (end) { tNow = 0; draw(); } }
$("t-play").onclick = () => (playing ? stop() : play()); $("t-stop").onclick = () => { stop(); tNow = 0; draw(); };
$("t-seek").oninput = () => { tNow = ($("t-seek").value / 1000) * total(); const l = locate(tNow); if (l.i !== cur) select(l.i, true); newWorld(); draw(); };
$("f-export").onclick = () => { if (!proj.scenes.length) return; tNow = 0; play(true); };

// ---- editing
function sceneList() { const box = $("f-list"); box.replaceChildren();
  proj.scenes.forEach((s, i) => { const b = el("button", { type: "button", className: "sitem" + (i === cur ? " on" : "") }, el("b", {}, `${i + 1}. ${s.title || "Scene"}`), el("small", {}, `${s.duration}s · ${s.effects.length} fx`)); b.onclick = () => { stop(); select(i); tNow = proj.scenes.slice(0, i).reduce((a, x) => a + x.duration, 0); draw(); }; box.append(b); }); }
function select(i, keepTime) { cur = Math.max(0, Math.min(proj.scenes.length - 1, i)); const s = proj.scenes[cur]; sceneList(); $("insp").hidden = !s; if (!s) return;
  $("i-title").value = s.title; $("i-text").value = s.text; $("i-narr").value = s.narration; $("i-dur").value = s.duration; $("i-dur-v").textContent = s.duration + " s"; $("i-c1").value = s.bg.c1; $("i-c2").value = s.bg.c2;
  for (const k of Object.keys(s.grade)) $("g-" + k).value = s.grade[k]; for (const b of $("i-fx").children) b.classList.toggle("on", s.effects.includes(b.dataset.fx)); if (!keepTime) draw(); }
for (const [k, label] of Object.entries(FX)) {
  const b = el("button", { type: "button", className: "tag", textContent: label }); b.dataset.fx = k;
  b.onclick = () => { const s = proj.scenes[cur]; if (!s) return; s.effects = s.effects.includes(k) ? s.effects.filter((x) => x !== k) : [...s.effects, k]; b.classList.toggle("on", s.effects.includes(k)); if (k === "particles" && s.effects.includes(k)) { newWorld(); spawn(36); } sceneList(); if (!playing) draw(); };
  $("i-fx").append(b);
}
const bind = (id, fn) => ($(id).oninput = () => { const s = proj.scenes[cur]; if (!s) return; fn(s, $(id).value); sceneList(); if (!playing) draw(); });
bind("i-title", (s, v) => (s.title = v)); bind("i-text", (s, v) => (s.text = v)); bind("i-narr", (s, v) => (s.narration = v)); bind("i-c1", (s, v) => (s.bg.c1 = v)); bind("i-c2", (s, v) => (s.bg.c2 = v));
bind("i-dur", (s, v) => { s.duration = +v; $("i-dur-v").textContent = v + " s"; }); for (const k of ["exposure", "contrast", "saturation", "hue"]) bind("g-" + k, (s, v) => (s.grade[k] = +v));
$("i-noimg").onclick = () => { const s = proj.scenes[cur]; if (s) { s.bg.image = ""; draw(); } };
$("i-img").onchange = async () => { const f = $("i-img").files[0], s = proj.scenes[cur]; if (!f || !s) return; const bmp = await createImageBitmap(f), r = Math.min(1, 960 / bmp.width), c = el("canvas", { width: Math.round(bmp.width * r), height: Math.round(bmp.height * r) });
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height); s.bg.image = c.toDataURL("image/jpeg", 0.6); if (s.bg.image.length > 120000) { s.bg.image = c.toDataURL("image/jpeg", 0.4); } draw(); };
$("s-add").onclick = () => { proj.scenes.splice(cur + 1, 0, blank()); select(cur + 1); };
$("s-dup").onclick = () => { if (proj.scenes[cur]) { proj.scenes.splice(cur + 1, 0, JSON.parse(JSON.stringify(proj.scenes[cur]))); select(cur + 1); } };
$("s-del").onclick = () => { if (proj.scenes[cur] && confirm("Delete this scene?")) { proj.scenes.splice(cur, 1); select(cur); draw(); } };
$("s-up").onclick = () => { if (cur > 0) { [proj.scenes[cur - 1], proj.scenes[cur]] = [proj.scenes[cur], proj.scenes[cur - 1]]; select(cur - 1); } };
$("s-dn").onclick = () => { if (cur < proj.scenes.length - 1) { [proj.scenes[cur + 1], proj.scenes[cur]] = [proj.scenes[cur], proj.scenes[cur + 1]]; select(cur + 1); } };
$("f-title").oninput = () => (proj.title = $("f-title").value);
$("f-sec").oninput = () => ($("f-sec-v").textContent = $("f-sec").value + " s");

// ---- projects + AI
function load(p, id) { stop(); proj = { title: p.title, language: p.language || "english", scenes: p.scenes || [], music: true }; fid = id || null; $("f-title").value = proj.title; tNow = 0; cur = 0; newWorld(); select(0); draw(); }
async function films() { try { const { films: fs } = await api("/films"); const sel = $("f-open"); sel.replaceChildren(new Option("My films…", "")); for (const f of fs) sel.append(new Option(`${f.title} (${f.nscenes} scenes)`, f.id)); if (fid) sel.value = fid; } catch {} }
$("f-open").onchange = async () => { const id = $("f-open").value; if (id) { try { load(await api("/films/" + id), id); } catch (e) { toast(e.message); } } };
$("f-new").onclick = () => load({ title: "Untitled film", scenes: [blank()] }, null);
$("f-save").onclick = async () => { try { proj.title = $("f-title").value || proj.title; const r = await api(fid ? "/films/" + fid : "/films", { method: fid ? "PUT" : "POST", body: proj }); fid = r.id; toast("Saved."); films(); } catch (e) { toast(e.message); } };
$("f-del").onclick = async () => { if (!fid || !confirm("Delete this film permanently?")) return; try { await api("/films/" + fid, { method: "DELETE" }); toast("Deleted."); load({ title: "Untitled film", scenes: [] }, null); films(); } catch (e) { toast(e.message); } };
$("f-plan").onclick = async () => { const idea = $("f-idea").value.trim(); if (idea.length < 4) return say("Describe the film in a sentence."); $("f-plan").disabled = true; say("Writing the director's brief and storyboard…");
  try { const p = await api("/film/plan", { method: "POST", body: { prompt: idea, style: $("f-style").value, seconds: +$("f-sec").value, language: $("f-lang").value } }); load(p, null); say(`Storyboard ready: ${p.scenes.length} scenes. Edit anything, then Save.`); }
  catch (e) { say(e.message); } finally { $("f-plan").disabled = false; } };
function voices() { const s = $("o-voice"); if (!("speechSynthesis" in window)) return; s.replaceChildren(new Option("Best match", "")); for (const v of speechSynthesis.getVoices()) s.append(new Option(`${/-IN$/i.test(v.lang) ? "🇮🇳 " : ""}${v.name} (${v.lang})`, v.voiceURI)); }
if ("speechSynthesis" in window) { voices(); speechSynthesis.onvoiceschanged = voices; }
// ---- auto-tune the look: measure the frame, then move exposure / contrast / saturation toward a balanced picture
$("g-auto").onclick = () => { const s = proj.scenes[cur]; if (!s) return; s.grade = { exposure: 0, contrast: 0, saturation: 0, hue: s.grade.hue || 0 }; stop(); draw();
  const d = cx.getImageData(0, 0, W, H).data; let n = 0, m = 0, q = 0, ch = 0;
  for (let i = 0; i < d.length; i += 64) { const y = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; m += y; q += y * y; ch += Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]); n++; }
  m /= n; const sd = Math.sqrt(Math.max(0, q / n - m * m)); ch /= n; const cl = (v, a) => Math.max(-a, Math.min(a, +v.toFixed(2)));
  s.grade.exposure = cl((120 - m) / 255 * 1.3, 0.4); s.grade.contrast = cl((64 - sd) / 64 * 0.5, 0.4); s.grade.saturation = cl((70 - ch) / 70 * 0.4, 0.5);
  select(cur); say(`Auto-tuned: brightness ${m | 0} → balanced, contrast ${sd | 0}, colour ${ch | 0}. Adjust the sliders to taste.`); };
newWorld(); load({ title: "Untitled film", scenes: [blank()] }, null); films();
{ const m = /open=(f-[0-9a-f]{8,16})/.exec(location.hash); if (m) api("/films/" + m[1]).then((p) => { load(p, m[1]); films(); }).catch(() => {}); }
