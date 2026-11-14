// Stories, pravachan and explainers: outline -> sections (each written by the model) -> scene-by-scene narration with a soft raga bed.
import { $, api, toast, el } from "./api.js";
import { master, schedule } from "./synth.js";

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
async function startBed() {
  if (!$("bg").checked) return;
  try {
    const { songs } = await api("/playlist", { auth: false }); if (!songs.length) return;
    const pick = songs[Math.floor(Math.random() * songs.length)], full = await api("/playlist/" + pick.id, { auth: false });
    ctx = ctx || new AudioContext(); await ctx.resume();
    const bus = master(ctx, 0.22).bus; schedule(ctx, bus, { ...full.score, lyrics: [] }, ctx.currentTime + 0.1, 0);
    bedTimer = setTimeout(() => ctx && startBed(), Math.max(30, full.score.duration - 3) * 1000);
  } catch {}
}
function stop() { run++; clearTimeout(bedTimer); try { speechSynthesis.cancel(); } catch {} try { ctx && ctx.close(); } catch {} ctx = null; $("play").textContent = "▶ Play"; }
$("stop").onclick = stop;
const speak = (txt, lang) => new Promise((res) => {
  const u = new SpeechSynthesisUtterance(txt), want = voices.find((v) => v.voiceURI === $("voice").value) || voices.find((v) => v.lang.replace("_", "-") === lang) || voices.find((v) => v.lang.startsWith(lang.slice(0, 2)));
  if (want) u.voice = want; u.lang = want ? want.lang : lang; u.rate = kind === "pravachan" ? 0.9 : 0.95; u.onend = u.onerror = res; speechSynthesis.speak(u); });
$("play").onclick = async () => {
  if (!piece) return; stop(); const my = run; $("stage").hidden = false; $("play").textContent = "❚❚ Playing"; await startBed();
  const lang = BCP[piece.language] || "en-IN";
  for (let i = 0; i < piece.sections.length; i++) {
    while (piece.ready <= i && my === run) await new Promise((r) => setTimeout(r, 700));   // wait while the next section is still being written
    if (my !== run) return; const s = piece.sections[i];
    $("st-head").textContent = s.heading; $("st-pts").replaceChildren(...(s.points || []).map((p) => el("li", {}, p))); setBar(((i) / piece.sections.length) * 100);
    for (const line of s.text.match(/[^.!?।\n]+[.!?।]?/g) || [s.text]) { if (my !== run) return; if (!line.trim()) continue; $("st-text").textContent = line.trim(); await speak(line.trim(), lang); }
  }
  if (my === run) { stop(); setBar(100); $("st-text").textContent = "The end."; }
};
