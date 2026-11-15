// Admin dashboard: overview, users (type, name, status, limit, custom columns), custom columns, cloud cost.
// Every call is checked again on the server; hiding things here is only for convenience.
import { $, api, toast, el } from "./api.js";

const NS = "http://www.w3.org/2000/svg";
const usd = (n, d = 2) => "$" + (Number(n) || 0).toFixed(d);
const when = (s) => (s ? new Date(s).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");
let me = null, users = [], cols = [], meta = { default_limit: 30 }, editing = null, loaded = {};

// ---------------------------------------------------------------- charts (SVG, no inline styles)
function bars(box, rows, { fmt = (v) => v, alt = false } = {}) {
  box.replaceChildren(); const W = 560, H = 190, pad = 26, n = rows.length, bw = (W - pad) / n, real = Math.max(...rows.map((r) => r.v), 0.0001);
  const p90 = [...rows.map((r) => r.v)].sort((a, b) => a - b)[Math.floor(n * 0.9)], max = p90 > 0 && real > 3 * p90 ? p90 * 1.4 : real;   // one huge day (a monthly charge) must not flatten the rest
  const svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img");
  rows.forEach((r, i) => {
    const clipped = r.v > max, h = Math.max(r.v > 0 ? 2 : 0, ((H - pad - 22) * Math.min(r.v, max)) / max), x = pad + i * bw + bw * 0.15;
    const rect = document.createElementNS(NS, "rect"); rect.setAttribute("x", x); rect.setAttribute("y", H - pad - h); rect.setAttribute("width", bw * 0.7); rect.setAttribute("height", h); rect.setAttribute("rx", 3); rect.setAttribute("class", "bx" + (alt ? " alt" : "") + (clipped ? " clip" : ""));
    const t = document.createElementNS(NS, "title"); t.textContent = `${r.l}: ${fmt(r.v)}`; rect.append(t); svg.append(rect);
    if (r.v > 0 && (n <= 16 || clipped)) { const v = document.createElementNS(NS, "text"); v.setAttribute("x", x + bw * 0.35); v.setAttribute("y", H - pad - h - 4); v.setAttribute("text-anchor", "middle"); v.setAttribute("class", "val"); v.textContent = fmt(r.v); svg.append(v); }
    if (n <= 16 || i % 5 === 0) { const l = document.createElementNS(NS, "text"); l.setAttribute("x", x + bw * 0.35); l.setAttribute("y", H - 8); l.setAttribute("text-anchor", "middle"); l.textContent = r.l; svg.append(l); }
  });
  box.append(svg);
}
const stat = (label, value, sub) => el("div", { className: "stat" }, el("b", { textContent: value }), el("span", { textContent: label }), ...(sub ? [el("small", { textContent: sub })] : []));

// ---------------------------------------------------------------- overview
async function overview() {
  const s = await api("/admin/stats");
  $("stats").replaceChildren(stat("Users", s.users, `${s.admins} admin${s.admins === 1 ? "" : "s"}, ${s.disabled} disabled`), stat("Songs made", s.songs), stat("Songs today", s.composed_today, `limit ${s.default_limit} per user`),
    stat("Voice spend today", usd(s.voice_usd_today, 3), `site cap ${usd(s.voice_site_cap, 0)}, user cap ${usd(s.voice_user_cap)}`), stat("Cached voice files", s.tts_files ?? "—", s.tts_mb != null ? s.tts_mb + " MB" : ""));
  bars($("c-signups"), s.signups.map((x) => ({ l: x.day.slice(5), v: x.n })));
  bars($("c-voice"), s.voice_usd.map((x) => ({ l: x.day.slice(5), v: x.usd })), { fmt: (v) => usd(v, 3), alt: true });
  const a = $("audit"); a.replaceChildren();
  if (!s.recent.length) a.append(el("span", { className: "muted", textContent: "Nothing yet. Changes made here are logged." }));
  s.recent.forEach((r) => a.append(el("div", {}, el("time", { textContent: when(r.at) }), el("b", { textContent: r.what }), el("span", { textContent: r.target }), el("span", { className: "muted", textContent: r.detail }), el("span", { className: "muted", textContent: "by " + r.who }))));
}

// ---------------------------------------------------------------- users
function cell(c, v) {
  if (v === null || v === undefined || v === "") return "—";
  if (c.type === "yesno") return v ? "Yes" : "No";
  return String(v);
}
function drawUsers() {
  const q = $("u-q").value.trim().toLowerCase(), role = $("u-role").value;
  const head = ["", "Name", "Email", "Type", "Status", "Songs", "Today", "Voice $ today", "Voice $ total", "Joined", "Last sign-in", ...cols.map((c) => c.label)];
  $("utable").tHead.replaceChildren(el("tr", {}, ...head.map((h) => el("th", { textContent: h }))));
  const rows = users.filter((u) => (!role || u.role === role) && (!q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)));
  $("u-count").textContent = `${rows.length} of ${users.length} (all accounts in DynamoDB)`;
  const body = $("utable").tBodies[0]; body.replaceChildren();
  rows.forEach((u) => {
    const type = el("span", { className: "badge " + (u.owner ? "owner" : u.role === "admin" ? "admin" : ""), textContent: u.owner ? "owner" : u.role });
    const st = el("span", { className: "badge " + (u.disabled ? "off" : ""), textContent: u.disabled ? "disabled" : "active" });
    const btn = el("button", { className: "ghost", type: "button", textContent: "Edit" }); btn.onclick = () => openUser(u);
    body.append(el("tr", {}, el("td", { className: "act" }, btn), el("td", { textContent: u.name }), el("td", { textContent: u.email }), el("td", {}, type), el("td", {}, st), el("td", { textContent: u.songs ?? "—" }), el("td", { textContent: `${u.composed_today}/${u.limit}` }),
      el("td", { textContent: u.voice_usd_today ? usd(u.voice_usd_today, 3) : "—" }), el("td", { textContent: u.voice_usd_total ? usd(u.voice_usd_total, 3) : "—" }), el("td", { textContent: when(u.created) }), el("td", { textContent: when(u.last_login) }), ...cols.map((c) => el("td", { textContent: cell(c, u.extra[c.key]) }))));
  });
}
async function loadUsers() {
  const d = await api("/admin/users"); users = d.users; cols = d.columns; meta = d; drawUsers();
}
function field(label, input) { return el("label", { className: "field" }, el("span", { textContent: label }), input); }
function openUser(u) {
  editing = u; $("ud-title").textContent = u.email; $("ud-status").textContent = "";
  const owner = me.owner, f = $("ud-fields"); f.replaceChildren();
  const name = el("input", { id: "e-name", value: u.name, maxLength: 60 });
  const role = el("select", { id: "e-role" }, el("option", { value: "user", textContent: "User" }), el("option", { value: "admin", textContent: "Admin" })); role.value = u.role; role.disabled = !owner || u.owner;
  const lim = el("input", { id: "e-limit", type: "number", min: 0, max: 1000, value: u.limit, title: "Songs per day" });
  const dis = el("input", { id: "e-dis", type: "checkbox", checked: u.disabled }); dis.disabled = u.owner || u.email === me.email;
  const pw = el("input", { id: "e-pw", type: "text", maxLength: 128, placeholder: "leave empty to keep", autocomplete: "off" });
  f.append(field("Name (shown to others)", name), field(owner ? "Type" : "Type (owners only)", role), field("Songs per day", lim), el("label", { className: "field chk" }, dis, el("span", { textContent: "Account disabled (cannot sign in)" })), field("New password (sets it now)", pw));
  cols.forEach((c) => {
    let inp; const v = u.extra[c.key];
    if (c.type === "yesno") { inp = el("select", {}, el("option", { value: "", textContent: "—" }), el("option", { value: "yes", textContent: "Yes" }), el("option", { value: "no", textContent: "No" })); inp.value = v === true ? "yes" : v === false ? "no" : ""; }
    else if (c.type === "select") { inp = el("select", {}, el("option", { value: "", textContent: "—" }), ...c.options.map((o) => el("option", { value: o, textContent: o }))); inp.value = v ?? ""; }
    else { inp = el("input", { type: c.type === "number" ? "number" : c.type === "date" ? "date" : "text", step: "any", maxLength: 200, value: v ?? "" }); }
    inp.dataset.col = c.key; f.append(field(c.label, inp));
  });
  $("ud-del").hidden = u.owner || u.email === me.email; $("udlg").showModal();
  const more = $("ud-more"); more.textContent = "Loading details…";
  api("/admin/users/" + encodeURIComponent(u.email)).then((d) => {
    more.replaceChildren(el("b", { textContent: `Joined ${when(u.created)} · last sign-in ${when(u.last_login)} · voice spend ${usd(u.voice_usd_total, 3)} in total` }), el("br"),
      el("b", { textContent: `Latest songs (${d.songs.length})` }), ...d.songs.map((s) => el("div", { textContent: `${s.title} · ${s.raga} · ${s.language || ""} · ${s.source || ""}${s.style ? " · " + s.style : ""} · ${when(s.created)}` })),
      ...(d.log.length ? [el("b", { textContent: "Admin actions on this account" }), ...d.log.map((l) => el("div", { textContent: `${when(l.at)} · ${l.what} · ${l.detail} · by ${l.who}` }))] : []));
  }).catch((e) => (more.textContent = e.message));
}
async function saveUser() {
  const u = editing, body = {}; const name = $("e-name").value.trim(), lim = $("e-limit").value;
  if (name !== u.name) body.name = name;
  if (!$("e-role").disabled && $("e-role").value !== u.role) body.role = $("e-role").value;
  if (!$("e-dis").disabled && $("e-dis").checked !== u.disabled) body.disabled = $("e-dis").checked;
  if (String(lim) !== String(u.limit)) body.daily_limit = lim === "" ? null : Number(lim);
  if ($("e-pw").value) body.password = $("e-pw").value;
  const extra = {}; $("ud-fields").querySelectorAll("[data-col]").forEach((i) => { const k = i.dataset.col, old = u.extra[k]; let v = i.value; const was = old === true ? "yes" : old === false ? "no" : old == null ? "" : String(old); if (v !== was) extra[k] = v; });
  if (Object.keys(extra).length) body.extra = extra;
  if (!Object.keys(body).length) { $("ud-status").textContent = "Nothing changed."; return; }
  try { $("ud-status").textContent = "Saving…"; await api("/admin/users/" + encodeURIComponent(u.email), { method: "PATCH", body }); $("udlg").close(); toast("Saved."); await loadUsers(); loaded.overview = false; }
  catch (e) { $("ud-status").textContent = e.message; }
}

// ---------------------------------------------------------------- sign-up requests
let tmpMail = "";
async function requests() {
  const d = await api("/admin/requests"), box = $("req-list"); box.replaceChildren();
  $("req-n").hidden = !d.pending; $("req-n").textContent = d.pending;
  if (!d.requests.length) box.append(el("span", { className: "muted", textContent: "No requests yet." }));
  d.requests.forEach((r) => {
    const row = el("div", { className: "req " + r.status }, el("div", {}, el("b", { textContent: r.name }), el("span", { textContent: r.email }), ...(r.note ? [el("em", { className: "muted", textContent: "“" + r.note + "”" })] : []), el("small", { className: "muted", textContent: `asked ${when(r.created)}` + (r.decided ? ` · ${r.status} ${when(r.decided)} by ${r.by}` : "") })));
    const act = el("div", { className: "ract" });
    if (r.status !== "rejected") { const ok = el("button", { type: "button", className: "primary", textContent: r.status === "approved" ? "New temporary password" : "Approve" }); ok.onclick = () => approve(r, ok); act.append(ok); }
    if (r.status === "pending") { const no = el("button", { type: "button", className: "ghost", textContent: "Reject" }); no.onclick = async () => { try { await api("/admin/requests/" + encodeURIComponent(r.email) + "/reject", { method: "POST", body: {} }); toast("Rejected."); await requests(); } catch (e) { toast(e.message); } }; act.append(no); }
    row.append(el("span", { className: "badge " + (r.status === "pending" ? "off" : r.status === "approved" ? "admin" : ""), textContent: r.status }), act); box.append(row);
  });
}
async function approve(r, btn) {
  btn.disabled = true;
  try {
    const d = await api("/admin/requests/" + encodeURIComponent(r.email) + "/approve", { method: "POST", body: {} });
    const body = `Hello ${d.name},\n\nYour mhRaaga account is approved.\n\nSign in at https://www.mhraaga.in/login.html\nEmail: ${d.email}\nTemporary password: ${d.temp_password}\n\nAfter you sign in you will be asked to choose your own password.\n\nmhRaaga is an MVP (work in progress), so expect rough edges.\n\nKeshav Velhal`;
    $("r-who").textContent = d.email; $("r-pw").textContent = d.temp_password; $("r-body").value = body; tmpMail = body;
    $("r-mail").href = "mailto:" + encodeURIComponent(d.email).replace("%40", "@") + "?subject=" + encodeURIComponent("Your mhRaaga account") + "&body=" + encodeURIComponent(body);
    $("rdlg").showModal(); loaded.users = false; loaded.overview = false; await requests();
  } catch (e) { toast(e.message); } finally { btn.disabled = false; }
}
const copy = async (t) => { try { await navigator.clipboard.writeText(t); toast("Copied."); } catch { toast("Select the text and copy it."); } };

// ---------------------------------------------------------------- columns
function colRow(c = { key: "", label: "", type: "text" }) {
  const key = el("input", { value: c.key, placeholder: "key, e.g. plan", maxLength: 24 }), label = el("input", { value: c.label, placeholder: "Label", maxLength: 40 });
  const type = el("select", {}, ...["text", "number", "yesno", "date", "select"].map((t) => el("option", { value: t, textContent: t === "yesno" ? "yes / no" : t }))); type.value = c.type;
  const opts = el("input", { value: (c.options || []).join(", "), placeholder: "options, comma separated (select only)" }); opts.dataset.f = "options";
  const rm = el("button", { type: "button", className: "ghost", textContent: "Remove" }); const row = el("div", { className: "colrow" }, key, label, type, opts, rm); rm.onclick = () => row.remove();
  const sync = () => (opts.hidden = type.value !== "select"); type.onchange = sync; sync(); row._get = () => ({ key: key.value.trim().toLowerCase(), label: label.value.trim(), type: type.value, options: opts.value.split(",").map((s) => s.trim()).filter(Boolean) });
  return row;
}
function drawCols() { const box = $("cols"); box.replaceChildren(); cols.forEach((c) => box.append(colRow(c))); if (!cols.length) box.append(el("p", { className: "muted", textContent: "No custom columns yet." })); }
async function saveCols() {
  const list = [...$("cols").querySelectorAll(".colrow")].map((r) => r._get());
  try { $("col-status").textContent = "Saving…"; const d = await api("/admin/schema", { method: "PUT", body: { columns: list } }); cols = d.columns; $("col-status").textContent = "Saved."; drawCols(); await loadUsers(); }
  catch (e) { $("col-status").textContent = e.message; }
}

// ---------------------------------------------------------------- cost
async function costs(refresh = false) {
  const d = await api("/admin/costs" + (refresh ? "?refresh=1" : ""));
  $("cost-age").textContent = d.cached ? `From the cache, ${Math.round(d.age_s / 60)} min old` : "Just fetched";
  const eb = $("cost-err"); eb.replaceChildren(); Object.entries(d.errors || {}).forEach(([k, v]) => eb.append(el("div", { className: "errbox", textContent: `${k}: ${v}` })));
  const st = $("cost-stats"); st.replaceChildren();
  if (d.aws) { const cur = d.aws.months[d.aws.current] || { total: 0, ours: 0, services: [] }, prevKey = Object.keys(d.aws.months).filter((k) => k !== d.aws.current).sort().pop(), prev = d.aws.months[prevKey];
    st.append(stat("AWS this month (so far)", usd(cur.total), `projected ${usd(d.aws.projected, 0)}`), stat("…of which services mhRaaga uses", usd(cur.ours), "Lambda, DynamoDB, S3, CloudFront…"));
    if (prev) st.append(stat("AWS last month", usd(prev.total), prevKey));
    bars($("c-aws"), d.aws.daily.map((x) => ({ l: x.day.slice(5), v: x.usd })), { fmt: (v) => usd(v, 0) });
    const svc = $("svc"); svc.replaceChildren(); cur.services.forEach((s) => svc.append(el("div", { className: s.ours ? "ours" : "" }, el("span", { textContent: s.service }), el("b", { textContent: usd(s.usd) }))));
    $("cost-note").textContent = d.aws.note + " ● = a service this project uses."; }
  if (d.openrouter) { const o = d.openrouter; st.append(stat("OpenRouter, total used", usd(o.usage), o.limit != null ? `limit ${usd(o.limit, 0)}, left ${usd(o.limit_remaining)}` : "no spending limit set"), stat("OpenRouter this month", usd(o.usage_monthly), `week ${usd(o.usage_weekly)}, today ${usd(o.usage_daily, 3)}`)); }
  if (d.voice) st.append(stat("AI voice today", usd(d.voice.today, 3)), stat("AI voice this month", usd(d.voice.month, 2), "counted by the site"));
}

// ---------------------------------------------------------------- AI singer
async function singer() {
  const i = await api("/jobs/info"); $("sg-state").textContent = !i.enabled ? "The queue is switched off (deploy with GpuEngine=on)." : i.worker_alive ? `A GPU worker is alive (${i.worker}).` : "No GPU worker is running, so jobs will wait.";
  if ($("sg-song").options.length < 2) { try { const { songs } = await api("/songs"); songs.forEach((x) => $("sg-song").append(new Option(`${x.title} · ${x.raga} · ${x.language || ""}`, x.id))); } catch {} }
  const d = await api("/jobs"), box = $("sg-jobs"); box.replaceChildren();
  if (!d.jobs.length) box.append(el("span", { className: "muted", textContent: "No jobs yet." }));
  d.jobs.forEach((j) => { const row = el("div", {}, el("b", { textContent: j.title }), el("span", { className: "badge " + (j.status === "failed" ? "off" : j.status === "done" ? "admin" : ""), textContent: j.status }), el("span", { textContent: j.style }), el("span", { className: "muted", textContent: when(j.created) }));
    if (j.audio) { const a = el("audio", { controls: true, preload: "none" }); a.src = j.audio; row.append(a); } if (j.error) row.append(el("span", { className: "muted", textContent: j.error })); box.append(row); });
}
$("sg-go").onclick = async () => { try { $("sg-status").textContent = "Queuing…"; await api("/jobs", { method: "POST", body: { style: $("sg-style").value, lyrics: $("sg-lyrics").value, title: $("sg-title").value, song_id: $("sg-song").value || undefined } }); $("sg-status").textContent = "Queued."; await singer(); } catch (e) { $("sg-status").textContent = e.message; } };

// ---------------------------------------------------------------- tabs and start
async function show(t) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
  ["overview", "requests", "users", "columns", "costs", "singer"].forEach((x) => ($("t-" + x).hidden = x !== t));
  try { if (!loaded[t]) { if (t === "overview") await overview(); if (t === "requests") await requests(); if (t === "users") await loadUsers(); if (t === "columns") { await loadUsers(); drawCols(); } if (t === "costs") await costs(); if (t === "singer") await singer(); loaded[t] = t !== "singer" && t !== "requests"; } }
  catch (e) { toast(e.message); }
  history.replaceState(null, "", "#" + t);
}
async function start() {
  let m; try { m = await api("/me"); } catch { return; }
  me = { email: m.email, owner: false };
  $("who").textContent = `${m.name} · ${m.role}`;
  if (!m.admin) { $("gate").hidden = false; $("gate-msg").textContent = "This account is not an administrator."; return; }
  $("app").hidden = false;
  try { const d = await api("/admin/users"); me.owner = !!d.users.find((u) => u.email === m.email)?.owner; users = d.users; cols = d.columns; meta = d; } catch (e) { toast(e.message); }
  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => show(b.dataset.t)));
  $("u-q").oninput = drawUsers; $("u-role").onchange = drawUsers;
  $("ud-cancel").onclick = () => $("udlg").close(); $("ud-save").onclick = saveUser;
  $("ud-quota").onclick = async () => { try { await api("/admin/users/" + encodeURIComponent(editing.email), { method: "PATCH", body: { reset_quota: true } }); toast("Quota reset."); await loadUsers(); $("udlg").close(); } catch (e) { $("ud-status").textContent = e.message; } };
  $("ud-del").onclick = async () => { const c = prompt(`This deletes ${editing.email} and all their songs. Type the email to confirm:`); if (!c) return; try { const r = await api(`/admin/users/${encodeURIComponent(editing.email)}/delete`, { method: "POST", body: { confirm: c } }); $("udlg").close(); toast(`Deleted. ${r.songs_removed} songs removed.`); await loadUsers(); loaded.overview = false; } catch (e) { $("ud-status").textContent = e.message; } };
  $("u-add").onclick = () => { $("a-status").textContent = ""; $("a-role").disabled = !me.owner; $("adlg").showModal(); }; $("a-cancel").onclick = () => $("adlg").close();
  $("a-save").onclick = async () => { try { await api("/admin/users", { method: "POST", body: { name: $("a-name").value, email: $("a-email").value, password: $("a-pw").value, role: $("a-role").value } }); $("adlg").close(); ["a-name", "a-email", "a-pw"].forEach((i) => ($(i).value = "")); toast("User added."); await loadUsers(); loaded.overview = false; } catch (e) { $("a-status").textContent = e.message; } };
  $("col-add").onclick = () => { const b = $("cols"); if (!b.querySelector(".colrow")) b.replaceChildren(); b.append(colRow()); }; $("col-save").onclick = saveCols;
  $("cost-refresh").onclick = async () => { try { await costs(true); } catch (e) { toast(e.message); } };
  $("r-copy").onclick = () => copy($("r-pw").textContent); $("r-copy2").onclick = () => copy(tmpMail); $("r-close").onclick = () => $("rdlg").close();
  api("/admin/requests").then((d) => { $("req-n").hidden = !d.pending; $("req-n").textContent = d.pending; if (d.pending && !location.hash) show("requests"); }).catch(() => {});
  const t = location.hash.slice(1); show(["overview", "requests", "users", "columns", "costs", "singer"].includes(t) ? t : "users");
}
start();
