// One-page site: there is no navigation. Pages are sections of index.html, loaded in frames; this only tidies a page when it is framed.
document.querySelectorAll(".nav").forEach((n) => n.remove());
if (window.self !== window.top) document.documentElement.classList.add("embed");
if (window.self !== window.top) {   // links to the Create page open the Create section of the one page
  document.addEventListener("click", (e) => { const a = e.target.closest('a[href^="app.html"]'); if (!a) return; e.preventDefault(); parent.postMessage({ compose: a.getAttribute("href") }, location.origin); });
}

{ const v = new URLSearchParams(location.search).get("view"); if (/^[a-z]+$/.test(v || "")) document.documentElement.classList.add("v-" + v); }   // app.html?view=playlist|mine shows just that list

// MVP notice and copyright at the end of every standalone page (not inside the one-page frames)
if (window.self === window.top && !document.querySelector(".mvpfoot") && !document.querySelector(".authpage")) {
  const f = document.createElement("footer"); f.className = "mvpfoot";
  const b = document.createElement("b"); b.textContent = "MVP version, work in progress."; f.append(b, " © 2026 Keshav Velhal. All rights reserved."); document.body.append(f);
}
