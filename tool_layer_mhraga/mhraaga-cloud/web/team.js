// Team studio: shared film / song projects. Layers are owned by one artist each; the director orders and approves them.
// Changes from other people arrive by polling (every 5 s while the tab is visible). Saves use optimistic locking (base_rev).
import { $, api, toast, el } from "./api.js";

const FX = { glow: "Glow", vignette: "Vignette", grain: "Film grain", blur: "Soft focus", lightleak: "Light leak", particles: "Physics petals", kenburns: "Slow zoom", fade: "Fade", bw: "B&W", warm: "Warm", cool: "Cool" };
const SECTIONS = ["mukhda", "antara", "sanchari", "bridge", "alap note", "outro"];
const hue = (s) => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return `hsl(${h} 70% 68%)`; };
const initial = (e) => (e || "?")[0].toUpperCase();
let me = "", P = null, layers = new Map(), filter = "all", sel = null, timer = 0, lastNow = "", kind = "film", editing = null;

// ---------------------------------------------------------------- project list
async function home() {
  $("home").hidden = false; $("room").hidden = true; clearInterval(timer); P = null;
  try {
    const { projects } = await api("/teams"); const box = $("plist"); box.replaceChildren();
    if (!projects.length) box.append(el("p", { className: "muted" }, "No shared projects yet. Create one above, or ask a director to add your email."));
    for (const p of projects) { const b = el("button", { type: "button", className: "pcard" }, el("b", {}, p.title), el("small", {}, `${p.kind === "film" ? "🎬 Film" : "🎶 Song"} · you are ${p.role}`)); b.onclick = () => open(p.id); box.append(b); }
  } catch (e) { toast(e.message); }
}
$("np-kind").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; kind = b.dataset.k; for (const x of $("np-kind").children) x.classList.toggle("on", x === b); $("np-raga-w").hidden = kind !== "song"; };
$("np-go").onclick = async () => {
  try { const r = await api("/teams", { method: "POST", body: { kind, title: $("np-title").value, raga: $("np-raga").value, language: $("np-lang").value } }); $("np-title").value = ""; open(r.id); } catch (e) { $("np-status").textContent = e.message; }
};

// ---------------------------------------------------------------- room
async function open(pid) {
  try { const d = await api("/teams/" + pid); P = { ...d }; layers = new Map(d.layers.map((l) => [l.id, l])); lastNow = d.now; sel = null; }
  catch (e) { toast(e.message); return home(); }
  me = ""; try { me = (await api("/me")).email.toLowerCase(); } catch {}
  $("home").hidden = true; $("room").hidden = false; $("r-title").textContent = P.title; $("r-role").textContent = P.role; $("r-role").className = "chip " + P.role;
  $("invite").hidden = P.role !== "director"; $("l-add").hidden = P.role === "viewer"; $("editor").hidden = true;
  render(); clearInterval(timer); timer = setInterval(poll, 5000); sync("Live");
}
$("r-back").onclick = home;
const sync = (m) => ($("r-sync").textContent = `${m} · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`);

async function poll() {
  if (!P || document.hidden) return;
  try {
    const d = await api(`/teams/${P.id}?since=${encodeURIComponent(lastNow)}`);
    lastNow = d.now; const ids = new Set(d.layer_ids);
    for (const id of [...layers.keys()]) if (!ids.has(id)) layers.delete(id);
    for (const l of d.layers) layers.set(l.id, l);
    P.members = d.members; P.comments = d.comments; P.role = d.role; P.title = d.title;
    if (editing && layers.get(editing.id) && layers.get(editing.id).rev > editing.rev && !editing.dirty) openLayer(editing.id);   // someone else's change, no unsaved edits: refresh
    render(); sync("Live");
  } catch (e) { sync("Offline, retrying"); }
}

function render() {
  P.comments = P.comments || [];
  const all = [...layers.values()].sort((a, b) => a.slot - b.slot || a.id.localeCompare(b.id));
  const list = all.filter((l) => filter === "all" || (filter === "mine" ? l.by === me : l.status === filter));
  const box = $("lboard"); box.replaceChildren();
  if (!list.length) box.append(el("p", { className: "muted" }, all.length ? "Nothing matches this filter." : P.role === "viewer" ? "No layers yet." : "No layers yet. Add the first one."));
  for (const l of list) {
    const c = el("button", { type: "button", className: "lcard" + (l.id === sel ? " on" : "") + (l.by === me ? " mine" : "") },
      el("div", { className: "lt" }, el("span", { className: "slot" }, "#" + l.slot), el("span", { className: "chip " + l.status }, l.status)),
      el("b", {}, l.name || "Layer"), el("small", { className: "muted" }, l.title || ""),
      el("div", { className: "by" }, el("i", { className: "av", textContent: initial(l.by) }), el("span", {}, l.by === me ? "You" : l.by)));
    c.querySelector(".av").style.background = hue(l.by); c.onclick = () => openLayer(l.id); box.append(c);
  }
  const n = all.length, approved = all.filter((l) => l.status === "approved").length, by = new Set(all.map((l) => l.by)).size;
  const act = $("r-actions"); act.replaceChildren(el("span", { className: "muted" }, `${n} layers · ${approved} approved · ${by} artists`));
  const out = P.kind === "film" ? [["Open assembled film", openFilm]] : P.role === "director" ? [["Render song", renderSong], ["Copy lyrics", copyLyrics]] : [["Copy lyrics", copyLyrics]];
  for (const [t, fn] of out) { const b = el("button", { type: "button", className: "ghost", textContent: t }); b.onclick = fn; act.append(b); }
  const ms = Object.entries(P.members); $("m-count").textContent = `(${ms.length})`; const mb = $("members"); mb.replaceChildren();
  for (const [e, r] of ms) {
    const row = el("div", { className: "mrow" }, el("i", { className: "av", textContent: initial(e) }), el("span", { className: "n" }, e === me ? `${e} (you)` : e), el("span", { className: "chip " + r }, r));
    row.firstChild.style.background = hue(e);
    if (e !== P.director && (P.role === "director" || e === me)) { const x = el("button", { type: "button", className: "ghost danger", textContent: e === me ? "Leave" : "×" }); x.onclick = () => removeMember(e); row.append(x); }
    mb.append(row);
  }
  const cb = $("comments"); cb.replaceChildren(); const shown = sel ? P.comments.filter((c) => c.layer === sel) : P.comments.slice(-30);
  if (!shown.length) cb.append(el("small", { className: "muted" }, sel ? "No comments on this layer yet." : "No comments yet."));
  for (const c of shown) cb.append(el("div", { className: "cmt" }, el("b", {}, c.by === me ? "You" : c.by), el("small", { className: "muted" }, new Date(+c.at).toLocaleString()), document.createTextNode(c.text)));
}
$("r-filter").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; filter = b.dataset.f; for (const x of $("r-filter").children) x.classList.toggle("on", x === b); render(); };

// ---------------------------------------------------------------- layer editor
const blankScene = () => ({ title: "New shot", text: "", narration: "", duration: 6, effects: ["fade", "vignette"], bg: { c1: "#241046", c2: "#120f2e", image: "" }, grade: { exposure: 0, contrast: 0, saturation: 0, hue: 0 } });
$("l-add").onclick = async () => {
  try { const data = P.kind === "film" ? blankScene() : { section: "mukhda", lyrics: "", note: "" }; const r = await api(`/teams/${P.id}/layers`, { method: "POST", body: { name: P.kind === "film" ? "New shot" : "New section", data } }); await poll(); openLayer(r.id); } catch (e) { toast(e.message); }
};

async function openLayer(id) {
  sel = id; let L;
  try { L = await api(`/teams/${P.id}/layers/${id}`); } catch (e) { toast(e.message); return; }
  editing = { id, rev: L.rev, dirty: false }; render();
  const canEdit = P.role === "director" || (P.role === "artist" && L.by === me), box = $("editor"); box.hidden = false; box.replaceChildren();
  const mark = () => (editing.dirty = true), d = L.data;
  const name = el("input", { value: L.name, maxLength: 60, disabled: !canEdit }); name.oninput = mark;
  box.append(el("h3", {}, canEdit ? "Edit layer" : "View layer", el("small", {}, ` · by ${L.by === me ? "you" : L.by} · rev ${L.rev}`)), el("label", { className: "field" }, el("span", {}, "Layer name"), name));
  let collect;
  if (P.kind === "film") collect = filmForm(box, d, canEdit, mark); else collect = songForm(box, d, canEdit, mark);
  const status = el("select", { disabled: !canEdit && P.role !== "director" }); for (const s of ["wip", "review", "approved"]) { if (s === "approved" && P.role !== "director") continue; status.append(new Option(s === "wip" ? "In progress" : s === "review" ? "Ready for review" : "Approved", s)); } status.value = L.status === "approved" && P.role !== "director" ? "wip" : L.status; status.onchange = mark;
  box.append(el("label", { className: "field" }, el("span", {}, "Status"), status));
  let slot = null; if (P.role === "director") { slot = el("input", { type: "number", min: 0, max: 999, value: L.slot }); slot.oninput = mark; box.append(el("label", { className: "field" }, el("span", {}, "Order in the film / song"), slot)); }
  const act = el("div", { className: "actions" });
  if (canEdit) {
    const save = el("button", { type: "button", className: "primary", textContent: "Save layer" });
    save.onclick = async () => { try { const body = { name: name.value, data: collect(), base_rev: editing.rev, status: status.value }; if (slot) body.slot = +slot.value; await api(`/teams/${P.id}/layers/${id}`, { method: "PUT", body }); toast("Saved."); editing.dirty = false; await poll(); openLayer(id); } catch (e) { toast(e.message); if (/Reload|changed/.test(e.message)) openLayer(id); } };
    const del = el("button", { type: "button", className: "ghost danger", textContent: "Delete" });
    del.onclick = async () => { if (!confirm("Delete this layer?")) return; try { await api(`/teams/${P.id}/layers/${id}`, { method: "DELETE" }); sel = null; editing = null; box.hidden = true; await poll(); } catch (e) { toast(e.message); } };
    act.append(save, del);
  } else act.append(el("small", { className: "muted" }, "This layer belongs to another artist. Comment on it below."));
  box.append(act);
}

function filmForm(box, d, canEdit, mark) {
  const cv = el("canvas", { width: 480, height: 270, className: "prev" }), cx = cv.getContext("2d");
  const f = (label, node) => el("label", { className: "field" }, el("span", {}, label), node);
  const inp = (v, max) => { const i = el("input", { value: v || "", maxLength: max, disabled: !canEdit }); i.oninput = () => { mark(); paint(); }; return i; };
  const title = inp(d.title, 80), text = inp(d.text, 300), narr = el("textarea", { rows: 3, maxLength: 1200, value: d.narration || "", disabled: !canEdit }); narr.oninput = mark;
  const dur = el("input", { type: "range", min: 2, max: 40, step: 0.5, value: d.duration, disabled: !canEdit }), durv = el("b", {}, d.duration + " s"); dur.oninput = () => { durv.textContent = dur.value + " s"; mark(); };
  const c1 = el("input", { type: "color", value: d.bg.c1, disabled: !canEdit }), c2 = el("input", { type: "color", value: d.bg.c2, disabled: !canEdit }); c1.oninput = c2.oninput = () => { mark(); paint(); };
  let image = d.bg.image || "";
  const img = el("input", { type: "file", accept: "image/*", disabled: !canEdit });
  img.onchange = async () => { const fl = img.files[0]; if (!fl) return; const bmp = await createImageBitmap(fl), r = Math.min(1, 960 / bmp.width), c = el("canvas", { width: Math.round(bmp.width * r), height: Math.round(bmp.height * r) });
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height); image = c.toDataURL("image/jpeg", 0.55); if (image.length > 120000) image = c.toDataURL("image/jpeg", 0.4); mark(); paint(); };
  const fx = new Set(d.effects || []), tags = el("div", { className: "styles" });
  for (const [k, lab] of Object.entries(FX)) { const b = el("button", { type: "button", className: "tag" + (fx.has(k) ? " on" : ""), textContent: lab, disabled: !canEdit }); b.onclick = () => { fx.has(k) ? fx.delete(k) : fx.add(k); b.classList.toggle("on", fx.has(k)); mark(); paint(); }; tags.append(b); }
  const gr = {}, sliders = el("div", {});
  for (const [k, lo, hi] of [["exposure", -0.5, 0.5], ["contrast", -0.5, 0.5], ["saturation", -0.8, 0.8], ["hue", -0.5, 0.5]]) { gr[k] = el("input", { type: "range", min: lo, max: hi, step: 0.02, value: d.grade[k] || 0, disabled: !canEdit }); gr[k].oninput = () => { mark(); paint(); }; sliders.append(f(k[0].toUpperCase() + k.slice(1), gr[k])); }
  const imgEl = image ? Object.assign(new Image(), { src: image }) : null; if (imgEl) imgEl.onload = () => paint();
  function paint() {
    const g = cx.createLinearGradient(0, 0, 480 * 0.7, 270); g.addColorStop(0, c1.value); g.addColorStop(1, c2.value);
    cx.filter = `brightness(${1 + +gr.exposure.value}) contrast(${1 + +gr.contrast.value}) saturate(${1 + +gr.saturation.value}) hue-rotate(${+gr.hue.value * 180}deg)${fx.has("bw") ? " grayscale(1)" : ""}${fx.has("warm") ? " sepia(.35)" : ""}`;
    cx.fillStyle = g; cx.fillRect(0, 0, 480, 270);
    const im = image === d.bg.image ? imgEl : Object.assign(new Image(), { src: image, onload: paint }); if (image && im && im.complete && im.naturalWidth) { const r = Math.max(480 / im.width, 270 / im.height); cx.drawImage(im, (480 - im.width * r) / 2, (270 - im.height * r) / 2, im.width * r, im.height * r); }
    cx.filter = "none"; if (fx.has("vignette")) { const v = cx.createRadialGradient(240, 135, 80, 240, 135, 270); v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(0,0,0,.65)"); cx.fillStyle = v; cx.fillRect(0, 0, 480, 270); }
    if (title.value || text.value) { cx.font = "italic 20px Georgia, serif"; cx.textAlign = "center"; cx.fillStyle = "#f3d27a"; if (fx.has("glow")) { cx.shadowColor = "#ffcf66"; cx.shadowBlur = 14; } cx.fillText((text.value || title.value).slice(0, 48), 240, 240); cx.shadowBlur = 0; }
  }
  box.append(cv, f("Shot title", title), f("On-screen caption", text), f("Narration", narr), f("Duration", el("span", {}, dur, durv)), el("div", { className: "grid" }, f("Colour 1", c1), f("Colour 2", c2)), f("Background image (optional, kept small)", img), el("h3", {}, "Effects"), tags, el("h3", {}, "Colour grade"), sliders);
  paint();
  return () => ({ title: title.value, text: text.value, narration: narr.value, duration: +dur.value, effects: [...fx], bg: { c1: c1.value, c2: c2.value, image }, grade: Object.fromEntries(Object.entries(gr).map(([k, v]) => [k, +v.value])) });
}

function songForm(box, d, canEdit, mark) {
  const sec = el("select", { disabled: !canEdit }); for (const s of SECTIONS) sec.append(new Option(s[0].toUpperCase() + s.slice(1), s)); sec.value = d.section || "mukhda"; sec.onchange = mark;
  const ly = el("textarea", { rows: 7, maxLength: 1500, value: d.lyrics || "", placeholder: "Write the lines of this section…", disabled: !canEdit }); ly.oninput = mark;
  const note = el("input", { value: d.note || "", maxLength: 300, placeholder: "Note for the director (optional)", disabled: !canEdit }); note.oninput = mark;
  const f = (l, n) => el("label", { className: "field" }, el("span", {}, l), n);
  box.append(f("Section", sec), f("Lyrics", ly), f("Note", note));
  return () => ({ section: sec.value, lyrics: ly.value, note: note.value });
}

// ---------------------------------------------------------------- members, comments, outputs
$("inv-go").onclick = async () => {
  const emails = $("inv-emails").value.split(/[,;\s]+/).filter(Boolean); if (!emails.length) return;
  try { const r = await api(`/teams/${P.id}/invite`, { method: "POST", body: { emails, role: $("inv-role").value } }); toast(`Added ${r.added.length}.`); $("inv-emails").value = ""; P.members = r.members; render(); } catch (e) { toast(e.message); }
};
async function removeMember(e) { if (!confirm(e === me ? "Leave this project?" : `Remove ${e}?`)) return; try { const r = await api(`/teams/${P.id}/members/${encodeURIComponent(e)}`, { method: "DELETE" }); if (e === me) return home(); P.members = r.members; render(); } catch (x) { toast(x.message); } }
$("c-go").onclick = async () => { const t = $("c-text").value.trim(); if (!t) return; try { await api(`/teams/${P.id}/comments`, { method: "POST", body: { text: t, layer: sel || "" } }); $("c-text").value = ""; await poll(); } catch (e) { toast(e.message); } };
$("c-text").onkeydown = (e) => e.key === "Enter" && $("c-go").click();

async function openFilm() {
  try { const a = await api(`/teams/${P.id}/assemble`); if (!a.scenes.length) return toast("Add some layers first.");
    const r = await api("/films", { method: "POST", body: { title: a.title, language: a.language, scenes: a.scenes } }); toast(`Assembled from ${a.used}. Opening the film studio…`); location.href = `film.html?embed=1#open=${r.id}`; } catch (e) { toast(e.message); }
}
async function renderSong() { try { toast("Composing from the merged lyrics…"); const s = await api(`/teams/${P.id}/render`, { method: "POST" }); toast(`“${s.title}” is in your library (${s.raga}).`); } catch (e) { toast(e.message); } }
async function copyLyrics() { try { const a = await api(`/teams/${P.id}/assemble`); await navigator.clipboard.writeText(a.lyrics || ""); toast("Lyrics copied."); } catch (e) { toast(e.message); } }
document.addEventListener("visibilitychange", () => !document.hidden && P && poll());
home();
