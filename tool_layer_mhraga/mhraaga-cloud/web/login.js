const $ = (id) => document.getElementById(id);
const store = { set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };
let mode = "in";
function setMode(m) {
  mode = m; $("tab-in").classList.toggle("on", m === "in"); $("tab-up").classList.toggle("on", m === "up");
  $("f-name").hidden = m === "in"; $("a-go").textContent = m === "in" ? "Sign in" : "Create account"; $("a-err").textContent = "";
  $("h").textContent = m === "in" ? "Welcome back" : "Create your account";
  $("a-pass").autocomplete = m === "in" ? "current-password" : "new-password";
}
$("tab-in").onclick = () => setMode("in"); $("tab-up").onclick = () => setMode("up");
$("authform").onsubmit = async (e) => {
  e.preventDefault(); $("a-err").textContent = ""; $("a-go").disabled = true;
  try {
    const body = { email: $("a-email").value, password: $("a-pass").value, ...(mode === "up" ? { name: $("a-name").value } : {}) };
    const r = await fetch("/api/auth/" + (mode === "in" ? "login" : "signup"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
    store.set("mh_token", d.token);
    const next = new URLSearchParams(location.search).get("next");
    location.href = "index.html";
  } catch (err) { $("a-err").textContent = err.message; } finally { $("a-go").disabled = false; }
};
