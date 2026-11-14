// One-page site: there is no navigation. Pages are sections of index.html, loaded in frames; this only tidies a page when it is framed.
document.querySelectorAll(".nav").forEach((n) => n.remove());
if (window.self !== window.top) document.documentElement.classList.add("embed");
if (window.self !== window.top) {   // links to the Create page open the Create section of the one page
  document.addEventListener("click", (e) => { const a = e.target.closest('a[href^="app.html"]'); if (!a) return; e.preventDefault(); parent.postMessage({ compose: a.getAttribute("href") }, location.origin); });
}

{ const v = new URLSearchParams(location.search).get("view"); if (/^[a-z]+$/.test(v || "")) document.documentElement.classList.add("v-" + v); }   // app.html?view=playlist|mine shows just that list
