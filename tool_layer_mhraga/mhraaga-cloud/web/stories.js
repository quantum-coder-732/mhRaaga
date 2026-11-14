// Stories, pravachan and explainers: outline -> sections (each written by the model) -> scene-by-scene narration with a soft raga bed.
import { $, api, toast, el } from "./api.js";
import { startBed as bedStart, duckNow, releaseNow, master } from "./synth.js";
import { neuralOn, loadLine, chunks, playBuffer, voiceMode, setVoiceMode } from "./neural.js";
import { bestVoice } from "./voice.js";

let kind = (location.hash.slice(1) || "story"); if (!["story", "pravachan", "explainer"].includes(kind)) kind = "story";
let piece = null, run = 0, ctx = null, bedTimer = 0, voices = [];
const BCP = { english: "en-IN", hindi: "hi-IN", marathi: "mr-IN", telugu: "te-IN", gujarati: "gu-IN", kannada: "kn-IN", tamil: "ta-IN" };
const say = (m) => ($("status").textContent = m);
const paintKind = () => document.querySelectorAll("#kind button").forEach((b) => b.classList.toggle("on", b.dataset.k === kind));
document.querySelectorAll("#kind button").forEach((b) => (b.onclick = () => { kind = b.dataset.k; paintKind(); }));
paintKind();
$("min").oninput = () => ($("min-v").textContent = $("min").value + " min");

api("/people").then((d) => { for (const p of d.people) $("person").append(new Option(p.name + (p.style_notes ? " (style learned)" : ""), p.id)); }).catch(() => {});
function loadVoices() {
  voices = speechSynthesis.getVoices(); const sel = $("voice"); sel.replaceChildren(new Option("Best match for the language", ""));
  const g = (label, test) => { const og = el("optgroup", { label }); for (const v of voices.filter(test)) og.append(new Option(`${v.name} (${v.lang})`, v.voiceURI)); if (og.children.length) sel.append(og); };
  g("Indian voices", (v) => /-IN$/i.test(v.lang)); g("Other voices", (v) => !/-IN$/i.test(v.lang));
}
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }

// ---- writing
$("make").onclick = async () => {
  const topic = $("topic").value.trim(); if (topic.length < 3) return say("Say what it is about.");
  stop(); $("make").disabled = true; $("play").disabled = true; $("script").replaceChildren(); $("script-card").hidden = false; setBar(0);
  try {
    say("Planning…");
    const o = await api("/story/outline", { method: "POST", body: { topic, kind, minutes: +$("min").value, language: $("lang").value, person_id: $("person").value || undefined } });
    piece = { ...o, person_id: $("person").value || undefined, ready: 0 };
    for (let i = 0; i < o.sections.length; i++) {
      say(`Writing section ${i + 1} of ${o.sections.length}…`); setBar((i / o.sections.length) * 100);
      let d; for (let t = 0; t < 2; t++) { try { d = await api("/story/section", { method: "POST", body: { kind, title: o.title, heading: o.sections[i].heading, brief: o.sections[i].brief, idx: i, total: o.sections.length, language: o.language, person_id: piece.person_id,
        previous_tail: i ? o.sections[i - 1].text.slice(-300) : "" } }); break; } catch (e) { if (t) throw e; } }
      Object.assign(o.sections[i], d); piece.ready = i + 1;
      $("script").append(el("h3", {}, o.sections[i].heading), el("p", {}, d.text));
      if (i === 0) $("play").disabled = false;
    }
    setBar(100); say(`Ready: “${o.title}”. ${piece.sections.length} sections, about ${o.minutes} min.`);
  } catch (e) { say(e.message); } finally { $("make").disabled = false; }
};
const setBar = (p) => ($("bar").style.width = p + "%");

// ---- narration
let bed = null;
async function startBed() {
  if (!$("bg").checked) return;
  try {
    ctx = ctx || new AudioContext(); await ctx.resume();
    bed = bedStart(ctx, 0.9);   // tanpura and a soft pad only: no melody or tabla to compete with the speaker
  } catch {}
}
function stop() { bed = null; run++; clearTimeout(bedTimer); try { speechSynthesis.cancel(); } catch {} try { ctx && ctx.close(); } catch {} ctx = null; $("play").textContent = "▶ Play"; }
$("stop").onclick = stop;
const speak = (txt, lang) => new Promise((res) => {
  const u = new SpeechSynthesisUtterance(txt), want = bestVoice(voices, lang, $("voice").value);
  if (want) u.voice = want; u.lang = want ? want.lang : lang; u.rate = kind === "pravachan" ? 0.88 : 0.95; u.pitch = kind === "pravachan" ? 0.95 : 1;
  u.onstart = () => bed && ctx && duckNow(ctx, bed.m, 0.55);   // the bed steps back while the voice speaks
  u.onend = u.onerror = () => setTimeout(res, kind === "pravachan" ? 420 : 280);   // a breath between sentences
  speechSynthesis.speak(u); });
const LANG_NAME = { english: "english", hindi: "hindi", marathi: "marathi", telugu: "telugu", gujarati: "gujarati", kannada: "kannada", tamil: "tamil" };
// Neural voice: the next chunks are fetched while the current one plays; any failure drops to the device voice for that chunk.
async function sayChunk(text, lang, ahead, my) {
  if (my !== run) return;
  if (await neuralOn() && LANG_NAME[piece.language]) {
    for (const n of ahead) loadLine(n, piece.language, kind);                      // warm the cache, don't wait
    const buf = await loadLine(text, piece.language, kind);
    if (buf && my === run) {
      if (!ctx) { ctx = new AudioContext(); await ctx.resume(); }
      if (!bed) bed = { m: master(ctx, 0.9) };                                      // no music bed: still route the voice through the room reverb
      duckNow(ctx, bed.m, 0.38); const r = playBuffer(ctx, bed.m.voice, buf, ctx.currentTime + 0.05);
      await new Promise((res) => setTimeout(res, Math.max(0, (r.end - ctx.currentTime) * 1000) + (kind === "pravachan" ? 450 : 300)));
      return;
    }
  }
  await speak(text, BCP[piece.language] || "en-IN");
}
$("vg").value = voiceMode(); $("voice").closest("label").hidden = $("vg").value !== "device"; $("vg").onchange = () => { setVoiceMode($("vg").value); $("voice").closest("label").hidden = $("vg").value !== "device"; };
$("play").onclick = async () => {
  if (!piece) return; stop(); const my = run; $("stage").hidden = false; $("play").textContent = "❚❚ Playing"; await startBed();
  const lang = BCP[piece.language] || "en-IN";
  for (let i = 0; i < piece.sections.length; i++) {
    while (piece.ready <= i && my === run) await new Promise((r) => setTimeout(r, 700));   // wait while the next section is still being written
    if (my !== run) return; const s = piece.sections[i];
    $("st-head").textContent = s.heading; $("st-pts").replaceChildren(...(s.points || []).map((p) => el("li", {}, p))); setBar(((i) / piece.sections.length) * 100);
    const parts = chunks(s.text, 200);
    for (let k = 0; k < parts.length; k++) { if (my !== run) return; $("st-text").textContent = parts[k]; await sayChunk(parts[k], lang, parts.slice(k + 1, k + 3), my); }
  }
  if (my === run) { stop(); setBar(100); $("st-text").textContent = "The end."; }
};
