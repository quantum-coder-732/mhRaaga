// Studio hub: live AI rules (with admin editor) and what the self-learning loop has learned.
import { $, api, el, signedIn } from "./api.js";
const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
(async () => {
  const r = await api("/rules", { auth: false });
  $("r-ver").textContent = `v${r.version}${r.updated ? " · " + r.updated.slice(0, 10) : ""}`;
  for (const p of r.principles) $("r-list").append(el("li", {}, p));
  $("r-list").append(el("li", { className: "muted" }, `${r.blocked_count} blocked phrases are also enforced on every prompt, lyric, translation and story.`));
  const L = r.learned || {};
  $("l-sum").textContent = L.updated ? `Updated ${L.updated.slice(0, 10)}. ${L.runs} learning runs.` : "No learning run has been published yet.";
  if ((L.curve || []).length > 1) {                       // sparkline of the critics' mean reward per round
    const c = L.curve, lo = Math.min(...c), hi = Math.max(...c), W = 320, Hh = 70, ns = "http://www.w3.org/2000/svg", s = document.createElementNS(ns, "svg"), pl = document.createElementNS(ns, "polyline");
    s.setAttribute("viewBox", `0 0 ${W} ${Hh}`); pl.setAttribute("fill", "none"); pl.setAttribute("stroke", "#f4b942"); pl.setAttribute("stroke-width", "3");
    pl.setAttribute("points", c.map((v, i) => `${(i / (c.length - 1)) * W},${Hh - 6 - ((v - lo) / (hi - lo || 1)) * (Hh - 12)}`).join(" ")); s.append(pl); $("l-curve").append(s, el("small", { className: "muted" }, `Critic score ${c[0].toFixed(3)} → ${c.at(-1).toFixed(3)}`));
  }
  const t = el("table", { className: "ltab" }, el("tr", {}, ...["Language", "Tāla", "Tempo", "Lead"].map((h) => el("th", {}, h))));
  for (const [lang, d] of Object.entries(L.leaders || {})) t.append(el("tr", {}, el("td", {}, lang), el("td", {}, d.tala?.arm || ""), el("td", {}, d.tempo?.arm || ""), el("td", {}, d.lead?.arm || "")));
  $("l-lead").append(t);
  if (signedIn()) { try { const me = await api("/me"); if (me.admin) {
    const f = await api("/rules/full"); $("r-pr").value = f.principles.join("\n"); $("r-bl").value = f.blocked_terms.join("\n"); $("r-im").value = f.blocked_impersonation.join("\n"); $("r-admin").hidden = false;
    $("r-save").onclick = async () => { try { const o = await api("/rules", { method: "PUT", body: { principles: lines($("r-pr").value), blocked_terms: lines($("r-bl").value), blocked_impersonation: lines($("r-im").value) } }); $("r-status").textContent = "Saved as version " + o.version; } catch (e) { $("r-status").textContent = e.message; } };
  } } catch {} }
})().catch(() => {});
