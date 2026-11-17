// Make a song with a singer: choose the free raga engine or a Lyria 3 model, then wait for the song and play it.
// Songs made this way are rows of My songs with an `audio` link.
import { $, api } from "./api.js";
let timer = null, models = {}, left = 0;
const say = (t) => ($("ly-status").textContent = t);
const STYLES = ["devotional bhajan, harmonium, bansuri, tabla, dholak, manjira", "sufi qawwali, harmonium, dholak, handclaps, building crescendo", "soft classical, sitar, tabla, tanpura, evening raga", "folk, dholak, manjira, male chorus, joyful", "ghazal, harmonium, tabla, soulful female vocal"];
STYLES.forEach((s) => { const b = document.createElement("button"); b.type = "button"; b.className = "tag"; b.textContent = s.split(",")[0]; b.onclick = () => { $("ly-style").value = s; }; $("ly-chips").append(b); });

async function info() {
  try {
    const i = await api("/lyria/info"); if (!i.enabled) return;
    $("ly").hidden = false; $("ly-per").textContent = i.per_day; left = i.left_today; models = Object.fromEntries(i.models.map((m) => [m.key, m]));
    $("ly-left-pill").textContent = `${left} of ${i.per_day} left today`; paint();
  } catch {}
}
function chosen() { return document.querySelector('input[name="lym"]:checked').value; }
function paint() {
  const m = chosen(); document.querySelectorAll(".model").forEach((l) => l.classList.toggle("on", l.dataset.m === m));
  $("ly-form").hidden = m === "free";
  if (m !== "free") { $("ly-go").textContent = `Make the song · $${(models[m]?.usd ?? 0).toFixed(2)}`; $("ly-go").disabled = left <= 0 || !!timer; if (left <= 0) say("Today's limit is used. Try tomorrow."); }
}
document.querySelectorAll('input[name="lym"]').forEach((r) => (r.onchange = paint));

export function playAudio(s) { const a = $("ly-audio"); $("ly").hidden = false; a.hidden = false; a.src = s.audio; a.play().catch(() => {}); say(s.title || ""); a.scrollIntoView({ block: "center", behavior: "smooth" }); }
window.addEventListener("mh-audio", (e) => playAudio(e.detail));

function finish() { clearInterval(timer); timer = null; $("ly-bar").hidden = true; info(); }
function wait(id, expect) {
  const t0 = Date.now(); $("ly-bar").hidden = false;
  timer = setInterval(async () => {
    const sec = (Date.now() - t0) / 1000; $("ly-fill").style.width = Math.min(95, (sec / expect) * 100) + "%";
    try {
      const s = await api("/lyria/" + id);
      if (s.status === "done") { $("ly-fill").style.width = "100%"; say(`Ready. Made by ${s.planner || "Lyria 3"} · $${(s.usd || 0).toFixed(2)}`); finish(); window.dispatchEvent(new Event("mh-refresh")); playAudio({ audio: s.audio, title: s.title }); }
      else if (s.status === "failed") { say(s.error || "It did not work. Try again."); finish(); window.dispatchEvent(new Event("mh-refresh")); }
      else say(`Making your song… ${Math.round(sec)} s`);
    } catch (err) { say(err.message); finish(); }
  }, 4000);
}
$("ly-go").onclick = async () => {
  const m = chosen(); if (m === "free") return; $("ly-go").disabled = true; say("Starting…");
  try {
    const r = await api("/lyria", { method: "POST", body: { title: $("ly-title").value, style: $("ly-style").value, lyrics: $("ly-lyrics").value, language: "hindi", model: m } });
    window.dispatchEvent(new Event("mh-refresh")); wait(r.id, m === "clip" ? 30 : 50);
  } catch (err) { say(err.message); $("ly-go").disabled = false; }
};
info();
