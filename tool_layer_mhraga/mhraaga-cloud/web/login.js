const $ = (id) => document.getElementById(id);
const store = { set: (k, v) => { try { localStorage.setItem(k, v); } catch {} }, get: (k) => { try { return localStorage.getItem(k); } catch { return null; } } };
let mode = "in";
const HEAD = { in: ["Welcome back", "Sign in to compose and keep your songs.", "Sign in"], up: ["Request access", "An administrator approves new accounts.", "Send request"], ch: ["Choose your password", "One more step.", "Save my password"] };
function setMode(m) {
  mode = m; $("tab-in").classList.toggle("on", m === "in"); $("tab-up").classList.toggle("on", m === "up");
  $("p-in").hidden = m !== "in"; $("p-up").hidden = m !== "up"; $("p-ch").hidden = m !== "ch";
  document.querySelector(".tabs").hidden = m === "ch"; $("c-later").hidden = m !== "ch";
  $("a-email").required = $("a-pass").required = m === "in"; $("steps").hidden = m !== "up"; $("chk").hidden = m !== "up";
  [$("h").textContent, $("sub").textContent, $("a-go").textContent] = HEAD[m]; $("a-err").textContent = ""; $("a-err").classList.remove("ok");
}
function step(n, text) { setMode("up"); $("steps").hidden = false; document.querySelectorAll("#steps li").forEach((li) => { const k = +li.dataset.s; li.className = k < n ? "done" : k === n ? "now" : ""; }); $("a-err").textContent = text || ""; $("a-err").classList.toggle("ok", !!text); }
$("tab-in").onclick = () => setMode("in"); $("tab-up").onclick = () => { setMode("up"); document.querySelectorAll("#steps li").forEach((li) => (li.className = "")); };
const post = async (url, body, token) => { const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: JSON.stringify(body) }); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || `Error ${r.status}`); return d; };
$("chk").onclick = async () => {
  try { const email = $("r-email").value.trim(); if (!email) throw new Error("Enter your email above first."); const d = await post("/api/auth/request", { email });
    if (d.status === "pending") step(2, d.message); else if (d.status === "approved") step(3, d.message); else if (d.status === "account") { setMode("in"); $("a-email").value = email; $("a-err").textContent = d.message; $("a-err").classList.add("ok"); } else { step(0, d.message); }
  } catch (err) { $("a-err").textContent = err.message; $("a-err").classList.remove("ok"); }
};
$("c-later").onclick = () => { try { sessionStorage.setItem("mh_later", "1"); } catch {} location.href = "index.html"; };
$("authform").onsubmit = async (e) => {
  e.preventDefault(); $("a-err").textContent = ""; $("a-go").disabled = true;
  try {
    if (mode === "up") {
      const d = await post("/api/auth/signup", { name: $("r-name").value, email: $("r-email").value, note: $("r-note").value }); step(2, d.message);
    } else if (mode === "ch") {
      await post("/api/me/password", { current: $("c-cur").value, new: $("c-new").value }, store.get("mh_token")); location.href = "index.html";
    } else {
      const d = await post("/api/auth/login", { email: $("a-email").value, password: $("a-pass").value });
      store.set("mh_token", d.token);
      if (d.must_change) { setMode("ch"); $("c-cur").value = $("a-pass").value; $("c-new").focus(); } else location.href = "index.html";
    }
  } catch (err) { $("a-err").textContent = err.message; $("a-err").classList.remove("ok"); } finally { $("a-go").disabled = false; }
};
if (new URLSearchParams(location.search).get("change") && store.get("mh_token")) setMode("ch");
