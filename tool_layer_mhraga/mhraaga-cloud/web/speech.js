// Speech tab: type/dictate -> translate -> speak with an Indian or foreign voice over an optional raga bed. Browser speech services only.
import { master, schedule } from "./synth.js";
const $ = (id) => document.getElementById(id);
const api = async (path, opt = {}) => { let t = null; try { t = localStorage.getItem("mh_token"); } catch {}
  const r = await fetch("/api" + path, { method: opt.method || "GET", headers: { "Content-Type": "application/json", ...(t ? { Authorization: "Bearer " + t } : {}) }, body: opt.body ? JSON.stringify(opt.body) : undefined });
  const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || "Error " + r.status); return d; };
const say = (m) => ($("sp-status").textContent = m);

// ---- tabs and simple/advanced
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
  $("songs-pane").hidden = b.dataset.tab !== "songs"; $("speech-pane").hidden = b.dataset.tab !== "speech"; if (b.dataset.tab === "speech") loadVoices();
}));
document.querySelectorAll("#mode button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll("#mode button").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll("#songs-pane .adv").forEach((e) => (e.hidden = b.dataset.mode === "simple"));
}));

// ---- languages
const LANGS = [["hi-IN", "Hindi"], ["mr-IN", "Marathi"], ["te-IN", "Telugu"], ["ta-IN", "Tamil"], ["gu-IN", "Gujarati"], ["kn-IN", "Kannada"], ["bn-IN", "Bengali"], ["pa-IN", "Punjabi"], ["en-IN", "English (India)"],
  ["en-US", "English (US)"], ["en-GB", "English (UK)"], ["es-ES", "Spanish"], ["fr-FR", "French"], ["de-DE", "German"], ["it-IT", "Italian"], ["pt-BR", "Portuguese"], ["ru-RU", "Russian"], ["ja-JP", "Japanese"], ["ko-KR", "Korean"], ["zh-CN", "Chinese"], ["ar-SA", "Arabic"]];
const TO = { "hi-IN": "hindi", "mr-IN": "marathi", "te-IN": "telugu", "ta-IN": "tamil", "gu-IN": "gujarati", "kn-IN": "kannada", "bn-IN": "bengali", "pa-IN": "punjabi", "en-IN": "english", "en-US": "english", "en-GB": "english",
  "es-ES": "spanish", "fr-FR": "french", "de-DE": "german", "it-IT": "italian", "pt-BR": "portuguese", "ru-RU": "russian", "ja-JP": "japanese", "ko-KR": "korean", "zh-CN": "chinese", "ar-SA": "arabic" };
const HELLO = { hi: "नमस्ते, यह मेरी आवाज़ है।", mr: "नमस्कार, हा माझा आवाज आहे.", te: "నమస్కారం, ఇది నా స్వరం.", ta: "வணக்கம், இது என் குரல்.", gu: "નમસ્તે, આ મારો અવાજ છે.", kn: "ನಮಸ್ಕಾರ, ಇದು ನನ್ನ ಧ್ವನಿ.",
  bn: "নমস্কার, এটি আমার কণ্ঠ।", en: "Hello, this is my voice.", es: "Hola, esta es mi voz.", fr: "Bonjour, ceci est ma voix.", de: "Hallo, das ist meine Stimme.", it: "Ciao, questa è la mia voce.", pt: "Olá, esta é a minha voz.",
  ru: "Привет, это мой голос.", ja: "こんにちは、これは私の声です。", ko: "안녕하세요, 제 목소리입니다.", zh: "你好，这是我的声音。", ar: "مرحبا، هذا صوتي." };
for (const [c, n] of LANGS) { $("sp-stt").append(new Option(n, c)); $("sp-to").append(new Option(n, c)); }
$("sp-stt").value = "en-IN"; $("sp-to").value = "hi-IN";

// ---- tone presets
const TONES = { calm: [0.85, 0.95], warm: [0.95, 1.0], energetic: [1.1, 1.12], devotional: [0.8, 0.9], dramatic: [0.9, 0.8], bright: [1.0, 1.2] };
let tone = "warm";
for (const t of Object.keys(TONES)) { const b = document.createElement("button"); b.type = "button"; b.className = "tag" + (t === tone ? " on" : ""); b.textContent = t;
  b.onclick = () => { tone = t; document.querySelectorAll("#sp-tone .tag").forEach((x) => x.classList.toggle("on", x === b)); }; $("sp-tone").append(b); }

// ---- voices (Indian first, then the rest); gender is a best guess from the voice's name
const isIndian = (v) => /-IN$|^(hi|mr|te|ta|gu|kn|bn|pa|ur|ml)\b/i.test(v.lang);
const FEM = /female|woman|zira|heera|swara|neerja|kalpana|lekha|aditi|raveena|priya|samantha|karen|susan|hazel|victoria|moira|tessa|fiona|google.*(hindi|uk english female)|amelie|paulina|monica|anna|helena/i;
const MAL = /\bmale\b|hemant|ravi|prabhat|madhur|david|mark|daniel|alex|fred|jorge|thomas|google uk english male|diego|yuri|kyoko_?m/i;
const guess = (v) => (FEM.test(v.name) ? "f" : MAL.test(v.name) ? "m" : "");
let voices = [];
function loadVoices() {
  voices = speechSynthesis.getVoices(); if (!voices.length) { speechSynthesis.onvoiceschanged = loadVoices; return; }
  const g = $("sp-gender").value, keep = (v) => !g || guess(v) === g || guess(v) === "";
  const sel = $("sp-voice"), prev = sel.value; sel.replaceChildren(new Option("Best match for the language", ""));
  for (const [label, test] of [["Indian voices", isIndian], ["Other voices", (v) => !isIndian(v)]]) {
    const og = document.createElement("optgroup"); og.label = label;
    for (const v of voices.filter((x) => test(x) && keep(x))) og.append(new Option(`${v.name} (${v.lang})`, v.voiceURI));
    if (og.children.length) sel.append(og);
  }
  sel.value = prev;
  const box = $("sp-voices"); box.replaceChildren();
  if (!voices.length) box.textContent = "This device reports no voices.";
  for (const v of voices) { const r = document.createElement("div"); r.className = "vrow";
    const n = document.createElement("span"); n.textContent = `${isIndian(v) ? "🇮🇳 " : ""}${v.name} · ${v.lang}`; const b = document.createElement("button"); b.type = "button"; b.className = "ghost"; b.textContent = "▶";
    b.onclick = () => { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(HELLO[v.lang.slice(0, 2)] || HELLO.en); u.voice = v; u.lang = v.lang; speechSynthesis.speak(u); };
    r.append(n, b); box.append(r); }
}
$("sp-gender").onchange = loadVoices;
if ("speechSynthesis" in window) loadVoices(); else say("This browser has no speech synthesis.");

// ---- speak (sentence by sentence; a raga bed plays underneath if on)
let ctx = null, run = 0;
function stopAll() { run++; try { speechSynthesis.cancel(); } catch {} try { ctx && ctx.close(); } catch {} ctx = null; say(""); }
$("sp-stop").onclick = stopAll;
$("sp-var").oninput = () => ($("sp-var-v").textContent = $("sp-var").value);
async function bed() {
  const { songs } = await api("/playlist"); if (!songs.length) return;
  const pick = songs[Math.min(songs.length - 1, Math.floor(((+$("sp-var").value - 1) / 6) * (songs.length - 1)))];
  const full = await api("/playlist/" + pick.id); ctx = new AudioContext(); await ctx.resume();
  schedule(ctx, master(ctx, 0.3).bus, { ...full.score, lyrics: [] }, ctx.currentTime + 0.1, 0);
}
$("sp-go").onclick = async () => {
  const text = $("sp-text").value.trim(); if (!text) return say("Write or paste a script first."); stopAll(); const my = run;
  const lang = $("sp-to").dataset.spoken || $("sp-stt").value; const want = voices.find((v) => v.voiceURI === $("sp-voice").value);
  const best = want || voices.find((v) => v.lang.replace("_", "-") === lang) || voices.find((v) => v.lang.startsWith(lang.slice(0, 2)));
  const [rate, pitch] = TONES[tone];
  if ($("sp-bg").value === "1") { try { await bed(); } catch (e) { say("Background music unavailable: " + e.message); } }
  const parts = text.match(/[^.!?।\n]+[.!?।]?/g) || [text]; say("Speaking…");
  for (const p of parts) { if (my !== run) return; if (!p.trim()) continue;
    await new Promise((res) => { const u = new SpeechSynthesisUtterance(p.trim()); if (best) u.voice = best; u.lang = best ? best.lang : lang; u.rate = rate; u.pitch = pitch; u.onend = u.onerror = res; speechSynthesis.speak(u); }); }
  if (my === run) { say("Done."); try { ctx && ctx.close(); } catch {} ctx = null; }
};

// ---- translate (server, language model)
let original = "";
$("sp-tr").onclick = async () => {
  const text = $("sp-text").value.trim(); if (!text) return say("Nothing to translate."); const to = $("sp-to").value; $("sp-tr").disabled = true; say("Translating…");
  try { const r = await api("/translate", { method: "POST", body: { text, to: TO[to] } }); original = text; $("sp-text").value = r.text; $("sp-to").dataset.spoken = to; $("sp-stt").value = to; say("Translated. Press Speak."); }
  catch (e) { say(e.message); } finally { $("sp-tr").disabled = false; }
};
$("sp-stt").onchange = () => delete $("sp-to").dataset.spoken;

// ---- dictation in the chosen language
let rec = null;
$("sp-mic").onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition; if (!SR) return say("Speech-to-text needs Chrome, Edge or Safari.");
  if (rec) { rec.stop(); return; }
  rec = new SR(); rec.lang = $("sp-stt").value; rec.interimResults = true; rec.continuous = true; const base = $("sp-text").value ? $("sp-text").value + " " : "";
  rec.onresult = (e) => { let t = ""; for (const r of e.results) t += r[0].transcript; $("sp-text").value = base + t; };
  rec.onend = () => { rec = null; $("sp-mic").classList.remove("rec"); }; rec.onerror = (e) => say("Mic: " + e.error); rec.start(); $("sp-mic").classList.add("rec");
};

if (location.hash === "#speech") document.querySelector('.tabs button[data-tab="speech"]').click();
