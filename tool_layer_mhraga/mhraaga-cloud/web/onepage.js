// The one page: header sign-in state, hero prompt, and lazy frames that grow to fit their content.
const $ = (id) => document.getElementById(id);
let token = null; try { token = localStorage.getItem("mh_token"); } catch {}
const authed = !!token;

if (authed) {
  $("sign").textContent = "Sign out"; $("sign").removeAttribute("href"); $("sign").className = "ghost btn2"; $("sign").onclick = () => { try { localStorage.removeItem("mh_token"); } catch {} location.reload(); };
  fetch("/api/me", { headers: { Authorization: "Bearer " + token } }).then((r) => (r.ok ? r.json() : Promise.reject())).then((me) => { if (me.must_change && !sessionStorage.getItem("mh_later")) { location.href = "login.html?change=1"; return; }
    $("who").textContent = me.name; $("hello").textContent = `Welcome back, ${me.name.split(" ")[0]}`; $("quota").textContent = `${me.daily_limit - me.composed_today} of ${me.daily_limit} songs left today`;
  }).catch(() => { try { localStorage.removeItem("mh_token"); } catch {} location.reload(); });
}
$("gate").hidden = authed;
document.querySelectorAll("[data-auth]").forEach((s) => (s.hidden = !authed));

// Suno-style shell for signed-in people: sidebar on desktop, bottom bar on phones. One view at a time, linkable by #hash.
const NAV = [["home", "🏠", "Home"], ["create", "✨", "Create"], ["playlist", "🎵", "Playlist"], ["mine", "📚", "My songs"], ["stories", "📖", "Stories"], ["people", "👤", "People"], ["film", "🎬", "Film"], ["team", "👥", "Team"], ["studio", "🧠", "Studio"], ["ragas", "🪈", "Ragas"]];
const VIEWS = { home: ["home-hero", "library", "app"], create: ["create"], playlist: ["playlist"], mine: ["mine"], stories: ["stories"], people: ["people"], film: ["film"], team: ["team"], studio: ["studio"], ragas: ["ragas"] };
let view = "home";
function show(v, push = true) {
  if (!authed) return;
  view = VIEWS[v] ? v : "home"; const on = new Set(VIEWS[view]);
  document.querySelectorAll("[data-sec]").forEach((s) => (s.hidden = !on.has(s.id)));
  document.querySelectorAll("#appnav a").forEach((a) => a.classList.toggle("on", a.dataset.v === view));
  document.querySelectorAll("[data-sec]:not([hidden]) iframe[data-src]").forEach(load);
  if (push && location.hash !== "#" + view) history.replaceState(null, "", "#" + view);
  scrollTo(0, 0);
}
if (authed) {
  document.body.classList.add("authed");
  const nav = $("appnav"); nav.hidden = false;
  const logo = document.createElement("a"); logo.className = "logo"; logo.href = "#home"; logo.innerHTML = '<span class="om">ॐ</span><b>mhRaaga</b>'; nav.append(logo);
  for (const [v, ic, label] of NAV) { const a = document.createElement("a"); a.className = "l"; a.href = "#" + v; a.dataset.v = v; const i = document.createElement("span"); i.className = "ic"; i.textContent = ic; a.append(i, label); nav.append(a); }
  nav.addEventListener("click", (e) => { const a = e.target.closest("a.l"); if (!a) return; e.preventDefault(); show(a.dataset.v); });
  logo.onclick = (e) => { e.preventDefault(); show("home"); };
  window.addEventListener("hashchange", () => show(location.hash.slice(1), false));
  // administrators get one more entry; the server checks the role again on every admin call
  try { const t = localStorage.getItem("mh_token"); if (t) fetch("/api/me", { headers: { Authorization: "Bearer " + t } }).then((r) => r.json()).then((m) => { if (m && m.admin) { const a = document.createElement("a"); a.className = "l"; a.href = "admin.html"; const i = document.createElement("span"); i.className = "ic"; i.textContent = "👤"; a.append(i, "Users & cost"); nav.append(a); } }).catch(() => {}); } catch {}
}

// frames: load when near the viewport, then follow their content height (same origin, so we can read it)
function fit(f) {
  try { const d = f.contentDocument; if (!d || !d.body) return; const set = () => (f.style.height = d.documentElement.scrollHeight + "px"); set();
    if (!f._ro) { f._ro = new ResizeObserver(set); f._ro.observe(d.body); } } catch {}
}
function load(f) { if (f.dataset.loaded) return; f.dataset.loaded = 1; f.src = f.dataset.src + (f.dataset.src.includes("?") ? "&" : "?") + "embed=1" + (f.dataset.hash || ""); f.addEventListener("load", () => fit(f)); }
const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && (load(e.target), io.unobserve(e.target))), { rootMargin: "600px" });
if (!authed) document.querySelectorAll("iframe[data-src]").forEach((f) => { if (f.closest("[hidden]")) return; io.observe(f); });

// hero prompt: hand it to the Create frame
const picked = new Set();
$("dchips").onclick = (e) => { const b = e.target.closest(".tag"); if (!b) return; const s = b.dataset.s; picked.has(s) ? picked.delete(s) : picked.add(s); b.classList.toggle("on", picked.has(s)); };
$("dform").onsubmit = (e) => {
  e.preventDefault(); const t = $("dtext").value.trim() || (picked.has("poem") ? "A tender poem about love and patience" : "A gentle raga for the morning");
  if (!authed) { try { sessionStorage.setItem("mh_prompt", JSON.stringify({ t, s: [...picked] })); } catch {} location.href = "login.html"; return; }
  const q = new URLSearchParams({ prompt: t }); if (picked.has("krishna")) q.set("style", "krishna"); else if (picked.has("poem")) q.set("style", "poem");
  const f = document.querySelector("#create iframe"); f.dataset.loaded = ""; f.dataset.src = "app.html?" + q; show("create"); load(f);
};
try { const p = JSON.parse(sessionStorage.getItem("mh_prompt") || "null"); if (p && authed) { sessionStorage.removeItem("mh_prompt"); $("dtext").value = p.t; (p.s || []).forEach((s) => document.querySelector(`#dchips [data-s="${s}"]`)?.click()); $("dform").requestSubmit(); } } catch {}
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || !e.data || typeof e.data.compose !== "string" || !/^app\.html(\?[\w=&%.:+-]*)?$/.test(e.data.compose)) return;
  const f = document.querySelector("#create iframe"); f.dataset.loaded = ""; f.dataset.src = e.data.compose; show("create"); load(f);
});

if (authed) show(location.hash.slice(1), false);
