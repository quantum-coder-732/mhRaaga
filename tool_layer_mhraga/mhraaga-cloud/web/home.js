// Landing page: animated wave + featured ragas.
const c = document.getElementById("wave"), g = c.getContext("2d");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
function draw(t) {
  const w = c.width, h = c.height; g.clearRect(0, 0, w, h);
  for (let k = 0; k < 7; k++) {
    g.beginPath();
    for (let x = 0; x <= w; x += 4) {
      const y = h / 2 + Math.sin(x / (46 + k * 9) + t / (900 + k * 140) + k) * (22 + k * 14) * Math.sin(x / w * Math.PI);
      x ? g.lineTo(x, y) : g.moveTo(x, y);
    }
    g.strokeStyle = `hsla(${40 + k * 22},85%,${62 - k * 3}%,${0.85 - k * 0.1})`; g.lineWidth = 2.2; g.stroke();
  }
  g.fillStyle = "#f4b942"; g.font = "bold 120px serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("ॐ", w / 2, h / 2);
  if (!reduce) requestAnimationFrame(draw);
}
requestAnimationFrame(draw);

// Reference library + the catalog's learning curve (both written by infra/publish_catalog.py).
fetch("/library/index.json").then((r) => r.json()).then(({ tunes }) => {
  const box = document.getElementById("tunes");
  for (const t of tunes) {
    const d = document.createElement("div"); d.className = "tune";
    const n = document.createElement("div"); n.textContent = t.title;
    const a = document.createElement("audio"); a.controls = true; a.preload = "none"; a.src = "/" + t.file;
    d.append(n, a); box.append(d);
  }
}).catch(() => {});
fetch("/catalog/report.json").then((r) => r.json()).then((rep) => {
  const c = rep.stats && rep.stats.curve;
  if (c && c.length > 1) document.getElementById("learn").textContent =
    `Self-improving catalog: ${rep.stats.size} songs in 7 languages. Critic reward rose from ${c[0].toFixed(3)} to ${c[c.length - 1].toFixed(3)} over ${c.length} rounds (${rep.stats.improved} songs replaced by better ones). Reference tunes below teach the critics what real raga sounds like.`;
}).catch(() => {});
