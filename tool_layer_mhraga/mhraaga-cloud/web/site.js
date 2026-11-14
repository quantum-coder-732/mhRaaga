// Shared navigation: shows sign-in state, never touches the network.
const page = document.querySelector(".nav")?.dataset.page || "";
let token = null; try { token = localStorage.getItem("mh_token"); } catch {}
const nav = document.querySelector(".nav");
if (nav) {
  const link = (href, text, id) => { const a = document.createElement("a"); a.className = "l" + (page === id ? " on" : ""); a.href = href; a.textContent = text; return a; };
  const logo = document.createElement("a"); logo.className = "logo"; logo.href = "index.html";
  const om = document.createElement("span"); om.className = "om"; om.textContent = "ॐ";
  const b = document.createElement("b"); b.textContent = "mhRaaga"; logo.append(om, b);
  const ic = { home: "⌂", ragas: "☰", app: "✚", krishna: "♪", lib: "▤", dl: "⇩" };
  const link2 = (href, text, id) => { const a = link(href, "", id); const i = document.createElement("span"); i.className = "ic"; i.textContent = ic[id]; a.append(i, document.createTextNode(text)); return a; };
  nav.append(logo, link2("index.html", "Home", "home"), link2("ragas.html", "Explore", "ragas"), link2("app.html", "Create", "app"),
    link2("app.html#library", "Library", "lib"), link2("index.html#app", "Get the app", "dl"));
  const sp = document.createElement("span"); sp.className = "sp"; nav.append(sp);
  if (token) {
    const who = document.createElement("span"); who.className = "who"; who.id = "whoami"; nav.append(who);
    const out = document.createElement("button"); out.className = "ghost"; out.id = "signout"; out.textContent = "Sign out";
    out.onclick = () => { try { localStorage.removeItem("mh_token"); } catch {} location.href = "index.html"; };
    nav.append(out);
  } else { const a = document.createElement("a"); a.className = "btn"; a.href = "login.html"; a.textContent = "Sign in"; nav.append(a); }
}
