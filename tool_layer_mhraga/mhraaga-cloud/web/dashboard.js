// Signed-in home: prompt box, shortcuts, your recent songs, the community playlist.
import { $, api, el } from "./api.js";
const picked = new Set();
$("dchips").onclick = (e) => { const b = e.target.closest(".tag"); if (!b) return; const s = b.dataset.s; picked.has(s) ? picked.delete(s) : picked.add(s); b.classList.toggle("on", picked.has(s)); };
$("dform").onsubmit = (e) => {
  e.preventDefault(); const t = $("dtext").value.trim() || (picked.has("poem") ? "A tender poem about love and patience" : "A gentle raga for the morning");
  const q = new URLSearchParams({ prompt: t }); if (picked.has("krishna")) q.set("style", "krishna"); else if (picked.has("poem")) q.set("style", "poem");
  location.href = "app.html?" + q;
};
function card(s, href) {
  let h = 0; for (const c of s.title + s.raga) h = (h * 31 + c.codePointAt(0)) % 360;
  return el("a", { className: "scard", href }, el("div", { className: "th", style: `background:linear-gradient(135deg,hsl(${h},70%,45%),hsl(${(h + 60) % 360},65%,22%))` }, s.raga.startsWith("Gop") ? "🪈" : s.mood === "tender" ? "📜" : "♪"),
    el("strong", {}, s.title), el("small", {}, `${s.language || ""} · ${s.raga}${s.plays ? " · ▶ " + s.plays : ""}`));
}
(async () => {
  try { const me = await api("/me"); $("hello").textContent = `Welcome back, ${me.name.split(" ")[0]}`; $("quota").textContent = `${me.daily_limit - me.composed_today} of ${me.daily_limit} songs left today`; } catch {}
  try { const { songs } = await api("/songs"); $("mine").append(...songs.slice(0, 8).map((s) => card(s, "app.html#library"))); $("mine-empty").hidden = songs.length > 0; } catch {}
  try { const { songs } = await api("/playlist", { auth: false }); const top = [...songs].sort((a, b) => (b.plays || 0) - (a.plays || 0)).slice(0, 12); $("pop").append(...top.map((s) => card(s, "app.html?play=" + s.id))); } catch {}
  try { const r = await api("/rules", { auth: false }), c = r.learned?.curve; if (c && c.length > 1) $("learn").textContent = `The catalog has improved from ${c[0].toFixed(3)} to ${c.at(-1).toFixed(3)} on the critics' score. New songs start from what it has learned.`; } catch {}
})();
