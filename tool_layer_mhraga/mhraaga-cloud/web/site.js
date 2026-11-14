// Shared navigation: shows sign-in state, never touches the network.
const page = document.querySelector(".nav")?.dataset.page || "";
let token = null; try { token = localStorage.getItem("mh_token"); } catch {}
const nav = document.querySelector(".nav");
if (nav) {
  const link = (href, text, id) => { const a = document.createElement("a"); a.className = "l" + (page === id ? " on" : ""); a.href = href; a.textContent = text; return a; };
  const logo = document.createElement("a"); logo.className = "logo"; logo.href = "index.html";
  const om = document.createElement("span"); om.className = "om"; om.textContent = "ॐ";
  const b = document.createElement("b"); b.textContent = "mhRaaga"; logo.append(om, b);
  nav.append(logo, link("ragas.html", "Ragas", "ragas"), link("app.html", "Compose", "app"), link("index.html#app", "Get the app", "dl"));
  if (token) {
    const who = document.createElement("span"); who.className = "who"; who.id = "whoami"; nav.append(who);
    const out = document.createElement("button"); out.className = "ghost"; out.id = "signout"; out.textContent = "Sign out";
    out.onclick = () => { try { localStorage.removeItem("mh_token"); } catch {} location.href = "index.html"; };
    nav.append(out);
  } else { const a = document.createElement("a"); a.className = "btn"; a.href = "login.html"; a.textContent = "Sign in"; nav.append(a); }
}
