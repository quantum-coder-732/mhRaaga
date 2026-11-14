const $ = (id) => document.getElementById(id);
const NAMES = ["Sa", "Re♭", "Re", "Ga♭", "Ga", "Ma", "Ma♯", "Pa", "Dha♭", "Dha", "Ni♭", "Ni"];
const RATIO = [1, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2, 8 / 5, 5 / 3, 9 / 5, 15 / 8];
const mod = (n) => ((n % 12) + 12) % 12;
const label = (n) => NAMES[mod(n)] + (n < 0 ? "·" : n >= 12 ? "′" : "");
const hzOf = (sa, n) => sa * RATIO[mod(n)] * Math.pow(2, Math.floor(n / 12));
let current = null, ctx = null, stopper = null;

async function api(p) { const r = await fetch("/api" + p); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || r.status); return d; }
const chip = (t, cls = "") => { const s = document.createElement("span"); s.className = "chip " + cls; s.textContent = t; return s; };

async function show(spec) {
  const r = await api("/ragas/" + encodeURIComponent(spec)); current = { r, spec };
  $("detail").hidden = false; $("d-name").textContent = r.name;
  const chips = $("d-chips"); chips.replaceChildren(chip(r.time, "gold"), chip(r.mood), chip(r.tala));
  if (r.melakarta_names) chips.append(chip(r.melakarta_names.join(" → ")));
  const used = new Set([...r.aroha, ...r.avaroha].map(mod));
  const L = $("ladder"); L.replaceChildren();
  NAMES.forEach((nm, i) => { const d = document.createElement("div"); d.className = "sv" + (used.has(i) ? " in" : "") + (i === r.vadi ? " vadi" : i === r.samvadi ? " samvadi" : ""); d.textContent = nm; L.append(d); });
  const kv = $("d-kv"); kv.replaceChildren();
  const row = (k, v) => { const a = document.createElement("dt"), b = document.createElement("dd"); a.textContent = k; b.textContent = v; kv.append(a, b); };
  row("Aroha (ascent)", r.aroha.map(label).join(" "));
  row("Avaroha (descent)", r.avaroha.map(label).join(" "));
  row("Vādī · Samvādī", `${NAMES[r.vadi]} · ${NAMES[r.samvadi]}  (${mod(r.samvadi - r.vadi)} semitones apart)`);
  row("Pakaḍ", r.pakad.map(label).join(" "));
  if (r.tonic) row("Own tonic", r.tonic + " Hz");
  const p = new URLSearchParams(); p.set("raga", spec); $("compose").href = "app.html?" + p;
  if (r.tonic && [183, 233, 234].includes(Math.round(r.tonic))) $("tonic").value = String(Math.round(r.tonic));
  $("detail").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
}

function stopSound() { if (stopper) { stopper(); stopper = null; } $("listen").textContent = "▶ Listen"; }
$("listen").onclick = () => {
  if (stopper) return stopSound();
  if (!current) return;
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)(); ctx.resume();
  const sa = +$("tonic").value, r = current.r, t0 = ctx.currentTime + 0.1, out = ctx.createGain(); out.gain.value = 0.5; out.connect(ctx.destination);
  const tone = (hz, t, d, vol, type = "triangle") => { const o = ctx.createOscillator(), g = ctx.createGain(); o.type = type; o.frequency.value = hz;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + 0.04); g.gain.exponentialRampToValueAtTime(0.0008, t + d); o.connect(g); g.connect(out); o.start(t); o.stop(t + d + 0.05); return o; };
  const seq = [...r.aroha, ...r.avaroha.slice(1)], step = 0.55, total = seq.length * step + 1;
  const drone = [tone(sa / 2, t0, total, 0.18, "sine"), tone(sa * 0.75, t0, total, 0.1, "sine")];
  seq.forEach((n, i) => tone(hzOf(sa, n), t0 + i * step, step * 1.6, n === r.vadi || mod(n) === r.vadi ? 0.34 : 0.24));
  const h = setTimeout(stopSound, total * 1000);
  stopper = () => { clearTimeout(h); out.gain.setTargetAtTime(0, ctx.currentTime, 0.05); setTimeout(() => out.disconnect(), 300); };
  $("listen").textContent = "■ Stop";
};

let all = [], timeFilter = "";
function render() {
  const q = $("q").value.trim().toLowerCase(), g = $("grid"); g.replaceChildren();
  for (const r of all) {
    if (timeFilter && r.time !== timeFilter) continue;
    if (q && !(r.name + " " + r.mood + " " + r.time).toLowerCase().includes(q)) continue;
    const b = document.createElement("button"); b.className = "rcard"; b.type = "button";
    const h = document.createElement("h3"); h.textContent = r.name;
    const m = document.createElement("div"); m.className = "m"; m.textContent = `${r.time} · ${r.mood} · ${r.tala}`;
    b.append(h, m); b.onclick = () => { stopSound(); show(r.name).catch((e) => alert(e.message)); }; g.append(b);
  }
  if (!g.children.length) { const p = document.createElement("p"); p.className = "muted"; p.textContent = "No raga matches."; g.append(p); }
}
(async () => {
  const { classical, melakartas } = await api("/ragas"); all = classical;
  const times = [...new Set(classical.map((r) => r.time))];
  const T = $("times");
  for (const t of ["", ...times]) { const b = document.createElement("button"); b.className = "pill" + (t === "" ? " on" : ""); b.type = "button"; b.textContent = t || "All";
    b.onclick = () => { timeFilter = t; [...T.children].forEach((x) => x.classList.toggle("on", x === b)); render(); }; T.append(b); }
  $("q").oninput = render; render();
  const M = $("mela");
  for (const m of melakartas) { const b = document.createElement("button"); b.type = "button"; b.className = "ghost"; b.textContent = `${m.number}. ${m.name}`; b.onclick = () => { stopSound(); show("mela:" + m.number); }; M.append(b); }
  const first = new URLSearchParams(location.search).get("r"); if (first) show(first).catch(() => {});
})().catch((e) => { $("grid").textContent = "Could not load the ragas: " + e.message; });
$("ggo").onclick = () => { stopSound(); const n = Math.min(16000, Math.max(1, parseInt($("gnum").value, 10) || 1)); $("gnum").value = n; show("gopi:" + n).catch((e) => alert(e.message)); };
$("gdice").onclick = () => { $("gnum").value = 1 + Math.floor(Math.random() * 16000); $("ggo").click(); };
