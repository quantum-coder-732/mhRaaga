#!/usr/bin/env python3
"""Build the documentation site (HTML) from the Markdown files.

  python3 tools/build_docs.py

Reads  README.md, docs/**/*.md
Writes tool_layer_mhraga/mhraaga-cloud/web/docs/**  (published at https://www.mhraaga.in/docs/ by infra/deploy.sh)

Needs `pip install markdown pygments` and, for the Mermaid diagrams, `npm i mermaid@10` plus headless Chrome (diagrams are rendered
to SVG files at build time because the site's CSP forbids running scripts that inject styles). Set MERMAID_JS and WS_MODULE_DIR
(a folder whose node_modules has `ws`) for that step; without them the diagrams are shown as text.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tool_layer_mhraga/mhraaga-cloud/web/docs"
GH = "https://github.com/quantum-coder-732/mhRaaga/blob/main/"
CACHE = Path(os.environ.get("DOCS_CACHE", "/tmp/mhraaga_docs_cache"))

# ------------------------------------------------------------------ the page tree
GROUPS = [
    ("Start here", [("README.md", "overview.html", "Overview"), (None, "system.html", "How the system works"), (None, "agents.html", "All the agents")]),
    ("mhRaaga", [
        ("docs/ARCHITECTURE.md", None, "Architecture"), ("docs/ENGINE.md", None, "Engine, module by module"), ("docs/BACKEND.md", None, "Backend, file by file"), ("docs/ADMIN.md", None, "Admin dashboard"), ("docs/API.md", None, "API for developers"), ("docs/SOUND.md", None, "Sound"),
        ("docs/VOICE.md", None, "AI voice"), ("docs/TEAM_AND_PHYSICS.md", None, "Shared studio and physics"), ("docs/STUDIO.md", None, "Stories, people, rules"),
        ("docs/AGENTIC_ARCHITECTURE.md", None, "Song factory agents"), ("docs/DOMAIN.md", None, "Domain and HTTPS"),
        ("docs/SINGER.md", None, "The singer layer (YuE2)"), ("docs/FILES.md", None, "Every music file"), ("docs/THIRD_PARTY.md", None, "Vendored upstream repos"), ("docs/components/android-app.md", None, "Android app")]),
    ("Kalkee, the agents", [("docs/kalkee/PLATFORM.md", None, "KALKEE: the platform"), ("docs/kalkee/README.md", "kalkee/index.html", "Kalkee in mhRaaga"), ("docs/kalkee/AGENTS.md", None, "The music agents"), ("docs/kalkee/LEARNING.md", None, "How the agents learn")]),
]
KALKEE_GROUPS = []


def title_of(md: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return re.sub(r"[`*_]", "", m.group(1)).strip() if m else fallback


def pretty(name: str) -> str:
    n = re.sub(r"\.md$", "", name)
    n = re.sub(r"^README_", "", n)
    return n.replace("_", " ").title() if n != "README" else "Overview"


def build_tree():
    """-> list of (group, [ {src, out, title} ]) and a map src -> out."""
    groups, smap = [], {}
    for g, items in GROUPS:
        rows = []
        for src, out, title in items:
            if src:
                out = out or (src[5:] if src.startswith("docs/") else src)
                out = re.sub(r"\.md$", ".html", out)
                smap[src] = out
            rows.append({"src": src, "out": out, "title": title})
        groups.append((g, rows))
    for g, folder in KALKEE_GROUPS:
        pass
    return groups, smap


# ------------------------------------------------------------------ markdown
def collect_mermaid(md: str, blocks: dict) -> str:
    def sub(m):
        code = m.group(1)
        h = hashlib.sha1(code.encode()).hexdigest()[:12]
        blocks[h] = code
        return f"\n\n@@DIAGRAM:{h}@@\n\n"
    return re.sub(r"^```mermaid\n(.*?)^```", sub, md, flags=re.S | re.M)


def fix_links(body: str, src: str, smap: dict, depth_prefix: str) -> str:
    here = (ROOT / src).parent

    def sub(m):
        href = m.group(2)
        if re.match(r"(https?:|mailto:|#|data:)", href):
            return m.group(0)
        path, _, frag = href.partition("#")
        if not path:
            return m.group(0)
        target = (here / path).resolve()
        try:
            rel = str(target.relative_to(ROOT))
        except ValueError:
            return m.group(0)
        if rel in smap:
            return f'{m.group(1)}"{depth_prefix}{smap[rel]}{"#" + frag if frag else ""}"'
        if target.exists() and not target.is_dir():
            return f'{m.group(1)}"{GH}{rel}" target="_blank" rel="noopener"'
        if target.is_dir():
            return f'{m.group(1)}"{GH.replace("/blob/", "/tree/")}{rel}" target="_blank" rel="noopener"'
        return f'{m.group(1)}"{GH}{rel}" target="_blank" rel="noopener"'
    return re.sub(r'(<a\s[^>]*?href=)"([^"]+)"', sub, body)


def render_md(src: str, blocks_out: dict, smap: dict, prefix: str) -> tuple[str, list, str]:
    text = (ROOT / src).read_text(encoding="utf-8")
    text = collect_mermaid(text, blocks_out)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list", "codehilite"],
                           extension_configs={"codehilite": {"css_class": "hl", "guess_lang": False, "noclasses": False}, "toc": {"toc_depth": "2-3"}})
    body = md.convert(text)
    body = fix_links(body, src, smap, prefix)
    toc = [(t["level"], t["id"], t["name"]) for t in md.toc_tokens for t in [t] + t.get("children", [])] if hasattr(md, "toc_tokens") else []
    return body, toc, title_of(text, pretty(Path(src).name))


def diagrams(body: str, prefix: str, have: set, blocks: dict) -> str:
    def sub(m):
        h = m.group(1)
        if h in have:
            return f'<figure class="diagram"><a href="{prefix}diagrams/{h}.svg" target="_blank" rel="noopener" title="Open the diagram full size"><img src="{prefix}diagrams/{h}.svg" alt="Diagram" loading="lazy"></a></figure>'
        return f'<pre class="plain"><code>{html.escape(blocks[h])}</code></pre>'
    return re.sub(r"<p>@@DIAGRAM:([0-9a-f]+)@@</p>", sub, body)


# ------------------------------------------------------------------ page shell
def nav_html(groups, prefix, current_out):
    parts = []
    for g, rows in groups:
        open_attr = " open" if any(r["out"] == current_out for r in rows) or g == "Start here" else ""
        lis = "".join(
            f'<li><a href="{prefix}{r["out"]}"{" class=cur aria-current=page" if r["out"] == current_out else ""}>{html.escape(r["title"])}</a></li>' for r in rows)
        parts.append(f"<details{open_attr}><summary>{html.escape(g)}</summary><ul>{lis}</ul></details>")
    return "".join(parts)


def shell(title, content, groups, out, toc=None, desc=""):
    prefix = "../" * out.count("/")
    toc_html = ""
    if toc:
        toc_html = '<aside class="toc"><b>On this page</b>' + "".join(f'<a class="l{lv}" href="#{i}">{html.escape(n)}</a>' for lv, i, n in toc[:60]) + "</aside>"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · mhRaaga docs</title><meta name="description" content="{html.escape(desc or title)}">
<link rel="stylesheet" href="{prefix}docs.css"></head>
<body data-root="{prefix}">
<header class="top"><button id="navbtn" aria-label="Menu" class="ibtn">☰</button><a class="brand" href="{prefix}index.html">mhRaaga <span>docs</span></a>
<div class="search"><input id="q" type="search" placeholder="Search the docs…" autocomplete="off" aria-label="Search"><div id="res" role="listbox"></div></div>
<a class="ibtn lnk" href="/developers.html">API</a><a class="ibtn lnk" href="/">Open app</a><button id="theme" class="ibtn" aria-label="Light or dark">◐</button></header>
<div class="shell"><nav class="side" id="side">{nav_html(groups, prefix, out)}</nav>
<main class="doc"><article>{content}</article><footer class="foot">mhRaaga documentation · built from the Markdown in the repository · <a href="{GH.replace("/blob/", "/tree/")}docs" target="_blank" rel="noopener">source</a></footer></main>{toc_html}</div>
<script src="{prefix}docs.js"></script></body></html>'''


# ------------------------------------------------------------------ hand-written pages
def svg_box(x, y, w, h, t1, t2="", hot=False):
    cls = "box hot" if hot else "box"
    s = f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/><text x="{x + 12}" y="{y + 24}">{html.escape(t1)}</text>'
    if t2:
        s += f'<text class="sub" x="{x + 12}" y="{y + 42}">{html.escape(t2)}</text>'
    return s


def page_system() -> str:
    d1 = ('<svg class="dg" viewBox="0 0 940 250" role="img" aria-label="Request to song to sound to voice"><defs><marker id="a1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z"/></marker></defs>'
          + svg_box(10, 20, 170, 64, "1  You describe it", "a sentence, or your lyrics") + svg_box(210, 20, 170, 64, "2  Brief", "language model plans it")
          + svg_box(410, 20, 170, 64, "3  Raga + tala", "from 16,000 ragas", True) + svg_box(610, 20, 170, 64, "4  Score", "alap, gat, tihai")
          + svg_box(210, 150, 170, 64, "5  Feel", "Box2D, GAN, auto-tune", True) + svg_box(410, 150, 170, 64, "6  Instruments", "played on your device")
          + svg_box(610, 150, 170, 64, "7  Voice", "neural speech, cached", True) + svg_box(780, 85, 150, 64, "8  Mix", "ducking, limiter")
          + '<g class="ar"><path marker-end="url(#a1)" d="M180 52 L210 52"/><path marker-end="url(#a1)" d="M380 52 L410 52"/><path marker-end="url(#a1)" d="M580 52 L610 52"/>'
            '<path marker-end="url(#a1)" d="M695 84 L695 110 L295 110 L295 150"/><path marker-end="url(#a1)" d="M380 182 L410 182"/><path marker-end="url(#a1)" d="M580 182 L610 182"/>'
            '<path marker-end="url(#a1)" d="M780 182 L855 182 L855 149"/></g></svg>')
    d2 = ('<svg class="dg" viewBox="0 0 940 300" role="img" aria-label="Clients, CloudFront, S3, API Gateway, Lambda, DynamoDB, SSM, OpenRouter"><defs><marker id="a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z"/></marker></defs>'
          + svg_box(10, 20, 170, 56, "Web app", "browser, Web Audio") + svg_box(10, 122, 170, 56, "Android app", "Flutter") + svg_box(10, 224, 170, 56, "Your server", "token + HTTPS")
          + svg_box(250, 110, 180, 80, "CloudFront", "www.mhraaga.in, HTTPS", True) + svg_box(500, 20, 170, 56, "S3 (private)", "site, tts audio, catalogue")
          + svg_box(500, 122, 170, 56, "API Gateway", "throttled, secret header") + svg_box(500, 224, 170, 56, "Lambda", "Python 3.12, x86_64", True)
          + svg_box(740, 20, 190, 56, "DynamoDB", "users, songs") + svg_box(740, 122, 190, 56, "SSM", "keys, JWT, origin secret") + svg_box(740, 224, 190, 56, "OpenRouter", "plan, translate, voice")
          + '<g class="ar"><path marker-end="url(#a2)" d="M180 48 L250 130"/><path marker-end="url(#a2)" d="M180 150 L250 150"/><path marker-end="url(#a2)" d="M180 252 L250 170"/>'
            '<path marker-end="url(#a2)" d="M430 125 L500 55"/><path marker-end="url(#a2)" d="M430 150 L500 150"/><path marker-end="url(#a2)" d="M585 178 L585 224"/>'
            '<path marker-end="url(#a2)" d="M670 240 L740 55"/><path marker-end="url(#a2)" d="M670 252 L740 150"/><path marker-end="url(#a2)" d="M670 266 L740 252"/></g></svg>')
    return f'''<h1>How the system works</h1>
<p class="lead">mhRaaga turns a sentence into a raga song, with the words spoken over it. This page walks through it from the click to the sound, then shows the machinery behind it.</p>
<h2 id="story">The story of one song</h2>{d1}
<ol class="steps">
<li><b>You describe it.</b> "A calm morning bhajan to Krishna", or paste your own lyrics. You can pick a language, a lead instrument, a tala and a length.</li>
<li><b>The brief.</b> A hosted language model (via OpenRouter) turns that into a plan: raga, tala, tempo, mood, language and lyrics. If the model is down, keyword rules still make a plan, so a song is always produced.</li>
<li><b>The raga and the tala.</b> The engine knows 30 classical ragas, all 72 melakartas and the 16,000 "gopi" ragas (a pair of melakartas, one of three tonics, a janya cut). Each has an ascent, a descent, a vadi and samvadi, and a time of day.</li>
<li><b>The score.</b> The composer writes the classical form: <i>alap</i> (the drone and free flute), <i>gat</i> (the tabla enters; each cycle opens on <i>sam</i>; the vadi is held; meend and kan ornaments), then a <i>tihai</i> that lands exactly on <i>sam</i>. Lyrics are timed to the phrases.</li>
<li><b>The feel.</b> Real physics makes it human: a Box2D spring gives rubato, a falling ball gives each note its weight, another spring gives the meend glide. A small GAN offers fresh phrases. Auto-tune pulls every note toward its shruti, and the last note is snapped exactly to Sa.</li>
<li><b>The instruments.</b> The score is plain JSON. Your device plays it with physical models: plucked-string tanpura, breathy bansuri, reed harmonium, tabla from its modes, a room reverb, human timing and dynamics.</li>
<li><b>The voice.</b> Each lyric line is spoken by a neural voice model. The audio is made once, stored in S3 and shared by everyone, so the second listener pays nothing and waits nothing. If the voice service is busy, your device's own voice reads that line instead.</li>
<li><b>The mix.</b> The browser lays the voice over the music, turns the music down under each line, and runs a limiter so nothing clips. Downloads (MP3 or WAV) include the voice.</li></ol>
<h2 id="infra">The machinery</h2>{d2}
<table><tr><th>Part</th><th>What it is</th></tr>
<tr><td>CloudFront</td><td>The only public door. Serves the site and audio from S3, forwards <code>/api/*</code> to the API with a secret header. The raw API address answers 403.</td></tr>
<tr><td>Lambda</td><td>One Python function: the whole engine, accounts, the studio, the team projects and the voice endpoint. It also holds the Box2D physics engine.</td></tr>
<tr><td>DynamoDB</td><td>Accounts (scrypt-hashed passwords, daily quota, lockout) and songs.</td></tr>
<tr><td>S3</td><td>The site, the shared playlist's assets, the song catalogue, the live rules, voice samples and the cached neural voice audio.</td></tr>
<tr><td>SSM</td><td>The model key and the signing secrets. None are in the repository.</td></tr>
<tr><td>Strict CSP</td><td>The pages run no inline script or style and may only talk to their own domain.</td></tr></table>
<h2 id="learn">How it improves</h2>
<p>An offline "song factory" runs producer agents that pick raga, tala, tempo, lead instrument, theme, tonic and form. Critics score each song, a fair-credit rule splits the score among the agents, and each agent learns which choices work for each language. The best songs fill a catalogue of up to 100. The next page lists every agent. <a href="agents.html">See all the agents →</a></p>
<h2 id="limits">What it does not do</h2>
<ul><li>The instruments are physical models, not recordings of a real band.</li><li>The voice speaks the words; it does not sing them to the melody.</li><li>Composing and speech call paid hosted models, so they are capped per user and per day.</li><li>The critics are rules, not listeners. Please listen, and tell us what is wrong.</li></ul>
<p>Deeper reading: <a href="ARCHITECTURE.html">Architecture</a> · <a href="API.html">API</a> · <a href="SOUND.html">Sound</a> · <a href="VOICE.html">AI voice</a>.</p>'''


def page_agents() -> str:
    producers = [("raga", "classical · gopi · melakarta", "raga_fidelity, library_affinity"), ("tala", "teental, keherwa, dadra, rupak, jhaptal, ektal, adi", "cadence, rhythm"),
                 ("tempo", "54, 62, 70, 80, 92, 104 bpm", "rhythm, library_affinity"), ("lead", "bansuri, harmonium, veena", "contour, phrase_variety"),
                 ("theme", "dawn, krishna, rain, night", "lyrics_fit"), ("tonic", "183, 233, 234 Hz", "library_affinity, raga_fidelity"), ("form", "song or poem", "lyrics_fit, poem_form")]
    prod = "".join(f"<tr><td><code>{a}</code></td><td>{o}</td><td>{j}</td></tr>" for a, o, j in producers)
    critics = [("raga_fidelity", "Do the notes belong to the raga? Are vadi and samvadi stressed?"), ("cadence", "Does the final phrase land on sam?"), ("phrase_variety", "Are phrases varied, not copies?"),
               ("contour", "Does the melody rise and fall in a singable shape?"), ("rhythm", "Does the tabla keep the tala (songs only)?"), ("lyrics_fit", "Does the script match the language, and does the lyric pacing fit?"),
               ("library_affinity", "How close is the profile to the reference tunes?"), ("poem_form", "For poems: line shape and pauses (used instead of rhythm)")]
    crit = "".join(f"<tr><td><code>{a}</code></td><td>{b}</td></tr>" for a, b in critics)
    runtime = [("Brief planner", "brief.py", "Turns your prompt into raga, tala, tempo, mood, language and lyrics using a language model; falls back to keyword rules."),
               ("Composer", "compose.py", "Writes the alap, gat and tihai, the tabla bols and the lyric timing."),
               ("Physics", "physics.py", "Box2D rubato, note weight, meend glide and drift. A pure-Python solver if Box2D cannot load."),
               ("Phrase GAN", "gan.py", "A small generative network that invents phrases; rule checks decide whether to use them."),
               ("Auto-tune", "autotune.py", "Pulls pitch toward the shruti; snaps the last note to Sa."),
               ("Voice", "voice.py", "Neural speech for each lyric line, cached and shared; device voice as fallback; daily cost caps."),
               ("Translator", "handler.py /translate", "Translates text between the supported languages."),
               ("Story and pravachan writer", "studio.py", "Plans a long spoken piece as an outline, then writes each section."),
               ("Film planner", "studio.py", "Turns a story into scenes for the film studio."),
               ("Rules and learning", "studio.py", "Live rules in S3 and learned defaults per language, applied to each new song."),
               ("Team studio", "team.py", "Shared projects of up to 150 members and 300 layers, with roles and optimistic locking.")]
    rt = "".join(f"<tr><td><b>{a}</b></td><td><code>{b}</code></td><td>{c}</td></tr>" for a, b, c in runtime)
    return f'''<h1>All the agents</h1>
<p class="lead">"Agent" is used in three places in this project. They are different things, so they are listed separately.</p>
<div class="cards"><a class="card" href="#runtime"><b>1 · The live product</b><span>Services that run when you press Create</span></a><a class="card" href="#factory"><b>2 · The song factory</b><span>Offline producers and critics that improve the catalogue</span></a><a class="card" href="#kalkee"><b>3 · Kalkee</b><span>The fair credit split that lets the producers learn</span></a></div>
<h2 id="runtime">1 · The live product</h2><p>These run inside the Lambda or on your device when you create a song. They are ordinary code, not autonomous agents.</p>
<table><tr><th>Part</th><th>File</th><th>What it does</th></tr>{rt}</table>
<h2 id="factory">2 · The song factory (offline)</h2>
<p>Seven <b>producer agents</b> each choose one thing. They choose with Thompson sampling: each option has a Beta score per language, and the agent samples from it, so good options win more often and untried ones still get a turn. A composer renders the song, <b>critics</b> review it, and the reward is split fairly among the producers.</p>
<table><tr><th>Producer</th><th>Chooses from</th><th>Judged by</th></tr>{prod}</table>
<h3 id="critics">The critics</h3><p>Eight rule-based critics (seven judge a song, and <code>poem_form</code> replaces <code>rhythm</code> for a poem). They are rules, not listeners.</p>
<table><tr><th>Critic</th><th>Question</th></tr>{crit}</table>
<h3>Fair credit</h3><p>The reward is split with the <b>Shapley value</b> so an agent is credited for what it added, not just for being on a good song. This is the one function taken from Kalkee. If it is missing, a proportional split is used and the run records <code>local-fallback</code>.</p>
<p>The catalogue holds at most 100 songs (about 14 per language); a better song replaces the weakest. Details: <a href="AGENTIC_ARCHITECTURE.html">Song factory agents</a>.</p>
<h2 id="kalkee">3 · Kalkee: the credit split</h2>
<p>Kalkee is the name of the agent layer. It is the part that lets the seven producers learn from the critics: when a song is judged, Kalkee's Shapley function shares the reward fairly among the producers according to what each added, and each producer updates its belief about the options it chose. mhRaaga uses that one function from Kalkee's code; everything else in this project is its own. The live site, the API and the app do not run Kalkee.</p>
<p>Read more: <a href="kalkee/index.html">Kalkee in mhRaaga</a> · <a href="kalkee/AGENTS.html">The music agents</a> · <a href="kalkee/LEARNING.html">How the agents learn</a> · <a href="FILES.html">Every music file</a>.</p>'''


def page_index(groups) -> str:
    cards = ""
    pick = [("overview.html", "Overview", "What mhRaaga is and how to run it"), ("system.html", "How the system works", "From a sentence to a song, with diagrams"),
            ("agents.html", "All the agents", "The live services, the song factory, and Kalkee"), ("ARCHITECTURE.html", "Architecture", "Layers, data, security, deploy"),
            ("API.html", "API for developers", "Accounts, endpoints, the score format"), ("SOUND.html", "Sound", "How the instruments are modelled"),
            ("VOICE.html", "AI voice", "Neural speech, cost and caps"), ("kalkee/index.html", "Kalkee in mhRaaga", "The agents, how they learn"), ("FILES.html", "Every music file", "What each file holds")]
    for h, t, s in pick:
        cards += f'<a class="card" href="{h}"><b>{t}</b><span>{s}</span></a>'
    return f'<h1>mhRaaga documentation</h1><p class="lead">Compose raga music from a sentence. Everything about how it is built, written for people to read.</p><div class="cards">{cards}</div><h2>All pages</h2>' + "".join(
        f"<h3>{html.escape(g)}</h3><ul class=all>" + "".join(f'<li><a href="{r["out"]}">{html.escape(r["title"])}</a></li>' for r in rows) + "</ul>" for g, rows in groups)


# ------------------------------------------------------------------ assets
CSS = r'''
:root{--bg:#fbf8f3;--fg:#241c15;--mut:#6d6258;--card:#fff;--line:#e4dccf;--acc:#b4531a;--code:#f3ece0;--hi:#fff3e6;--sh:0 1px 2px rgba(0,0,0,.06)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15110d;--fg:#f0e8dc;--mut:#a89c8c;--card:#1f1913;--line:#382f26;--acc:#f0a15f;--code:#1b1611;--hi:#2a2118;--sh:none}}
:root[data-theme=dark]{--bg:#15110d;--fg:#f0e8dc;--mut:#a89c8c;--card:#1f1913;--line:#382f26;--acc:#f0a15f;--code:#1b1611;--hi:#2a2118;--sh:none}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans","Noto Sans Devanagari",sans-serif}
a{color:var(--acc)}a:hover{text-decoration:none}
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:10px;padding:8px 16px;background:var(--bg);border-bottom:1px solid var(--line)}
.brand{font-weight:700;font-size:1.1rem;color:var(--fg);text-decoration:none;white-space:nowrap}.brand span{color:var(--acc);font-weight:500}
.ibtn{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:5px 10px;font:inherit;font-size:.9rem;cursor:pointer;text-decoration:none;white-space:nowrap}
#navbtn{display:none}.search{position:relative;flex:1;max-width:520px;margin:0 auto}
#q{width:100%;padding:7px 12px;border:1px solid var(--line);border-radius:99px;background:var(--card);color:var(--fg);font:inherit;font-size:.92rem}
#res{position:absolute;left:0;right:0;top:100%;margin-top:6px;background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);max-height:60vh;overflow:auto;display:none}
#res a{display:block;padding:8px 12px;color:var(--fg);text-decoration:none;border-bottom:1px solid var(--line)}#res a:hover,#res a.on{background:var(--hi)}#res small{display:block;color:var(--mut)}
.shell{display:grid;grid-template-columns:270px minmax(0,1fr) 210px;max-width:1500px;margin:0 auto}
.side{position:sticky;top:53px;align-self:start;height:calc(100vh - 53px);overflow:auto;padding:14px 12px 40px 16px;border-right:1px solid var(--line);font-size:.9rem}
.side details{margin-bottom:6px}.side summary{cursor:pointer;font-weight:600;padding:5px 4px;color:var(--mut);text-transform:uppercase;font-size:.74rem;letter-spacing:.05em}
.side ul{list-style:none;margin:2px 0 8px;padding:0}.side a{display:block;padding:4px 10px;border-radius:7px;color:var(--fg);text-decoration:none}.side a:hover{background:var(--hi)}.side a.cur{background:var(--hi);color:var(--acc);font-weight:600}
.doc{padding:24px 28px 60px;min-width:0}.doc article{max-width:820px}
h1{font-size:2rem;line-height:1.25;margin:.2em 0 .5em}h2{font-size:1.45rem;margin:1.9em 0 .5em;padding-top:.7em;border-top:1px solid var(--line)}h3{font-size:1.15rem;margin:1.5em 0 .4em}h4{margin:1.2em 0 .3em}
.lead{font-size:1.12rem;color:var(--mut)}
p,li{overflow-wrap:anywhere}
pre,code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem}
code{background:var(--code);padding:1px 5px;border-radius:5px}pre{background:var(--code);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow:auto;line-height:1.45}pre code{background:none;padding:0}
table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%;margin:1em 0;font-size:.92rem}th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}th{background:var(--hi)}
blockquote{margin:1em 0;padding:.2em 1em;border-left:4px solid var(--acc);background:var(--hi);border-radius:0 8px 8px 0;color:var(--mut)}
img{max-width:100%;height:auto}.diagram{margin:1.2em 0;padding:12px;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:auto}.diagram img{display:block;margin:0 auto;max-width:100%;height:auto}
.plain{white-space:pre}.dg{width:100%;height:auto;margin:1em 0}.dg .box{fill:var(--card);stroke:var(--line);stroke-width:1.2}.dg .hot{stroke:var(--acc);stroke-width:1.8}.dg text{fill:var(--fg);font:13px system-ui,sans-serif}.dg .sub{fill:var(--mut);font-size:11px}.dg .ar path{stroke:var(--mut);stroke-width:1.4;fill:none}.dg marker path{fill:var(--mut)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin:1.2em 0}.card{display:block;padding:14px 16px;background:var(--card);border:1px solid var(--line);border-radius:12px;text-decoration:none;color:var(--fg);box-shadow:var(--sh)}.card:hover{border-color:var(--acc)}.card b{display:block;margin-bottom:3px}.card span{color:var(--mut);font-size:.9rem}
.steps{padding-left:1.3em}.steps li{margin:.6em 0}ul.all{columns:2;column-gap:28px;list-style:none;padding:0}ul.all li{break-inside:avoid;padding:2px 0}
.toc{position:sticky;top:53px;align-self:start;max-height:calc(100vh - 53px);overflow:auto;padding:18px 12px;font-size:.82rem;border-left:1px solid var(--line)}.toc b{display:block;margin-bottom:6px;color:var(--mut);text-transform:uppercase;font-size:.72rem;letter-spacing:.05em}.toc a{display:block;padding:2px 0;color:var(--mut);text-decoration:none}.toc a:hover{color:var(--acc)}.toc .l3{padding-left:12px}
.foot{margin-top:50px;padding-top:14px;border-top:1px solid var(--line);color:var(--mut);font-size:.85rem}
@media (max-width:1100px){.shell{grid-template-columns:250px minmax(0,1fr)}.toc{display:none}}
@media (max-width:820px){#navbtn{display:inline-block}.lnk{display:none}.shell{display:block}.side{display:none;position:fixed;inset:53px 0 0 0;z-index:15;height:auto;background:var(--bg);width:min(86vw,320px);box-shadow:4px 0 24px rgba(0,0,0,.25)}body.nav .side{display:block}.doc{padding:18px 16px 48px}h1{font-size:1.55rem}ul.all{columns:1}}
'''

JS = r'''(function(){
var root=document.body.getAttribute("data-root")||"";
try{var t=localStorage.getItem("mhdocs-theme");if(t)document.documentElement.setAttribute("data-theme",t)}catch(e){}
var tb=document.getElementById("theme");if(tb)tb.addEventListener("click",function(){var d=document.documentElement,cur=d.getAttribute("data-theme");if(!cur)cur=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";var n=cur==="dark"?"light":"dark";d.setAttribute("data-theme",n);try{localStorage.setItem("mhdocs-theme",n)}catch(e){}});
var nb=document.getElementById("navbtn");if(nb)nb.addEventListener("click",function(){document.body.classList.toggle("nav")});
var cur=document.querySelector(".side a.cur");if(cur&&cur.scrollIntoView)cur.scrollIntoView({block:"center"});
var q=document.getElementById("q"),res=document.getElementById("res"),idx=null,sel=-1;
function load(cb){if(idx)return cb();fetch(root+"search-index.json").then(function(r){return r.json()}).then(function(j){idx=j;cb()}).catch(function(){idx=[];cb()})}
function esc(s){return s.replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function run(){var v=q.value.trim().toLowerCase();if(v.length<2){res.style.display="none";return}
load(function(){var w=v.split(/\s+/),out=[];idx.forEach(function(d){var h=(d.t+" "+d.x).toLowerCase(),sc=0;for(var i=0;i<w.length;i++){var p=h.indexOf(w[i]);if(p<0){sc=-1;break}sc+=d.t.toLowerCase().indexOf(w[i])>=0?5:1}if(sc>0){var p0=h.indexOf(w[0]),s=d.x.substr(Math.max(0,p0-d.t.length-1-40),120);out.push({d:d,sc:sc,s:s})}});
out.sort(function(a,b){return b.sc-a.sc});out=out.slice(0,12);
res.innerHTML=out.length?out.map(function(o){return '<a href="'+root+o.d.u+'"><b>'+esc(o.d.t)+'</b><small>'+esc(o.s)+'…</small></a>'}).join(""):'<a><small>No page found.</small></a>';res.style.display="block";sel=-1})}
if(q){q.addEventListener("input",run);q.addEventListener("keydown",function(e){var a=res.querySelectorAll("a[href]");if(e.key==="ArrowDown"&&a.length){sel=Math.min(a.length-1,sel+1)}else if(e.key==="ArrowUp"&&a.length){sel=Math.max(0,sel-1)}else if(e.key==="Enter"&&a.length){location.href=a[Math.max(0,sel)].getAttribute("href");return}else if(e.key==="Escape"){res.style.display="none";return}else return;e.preventDefault();a.forEach(function(x,i){x.classList.toggle("on",i===sel)})});
document.addEventListener("click",function(e){if(!e.target.closest(".search"))res.style.display="none"});
document.addEventListener("keydown",function(e){if(e.key==="/"&&document.activeElement.tagName!=="INPUT"){e.preventDefault();q.focus()}})}
})();'''


def main():
    groups, smap = build_tree()
    blocks, pages = {}, []
    # pass 1: markdown -> html, collect diagrams
    for g, rows in groups:
        for r in rows:
            if r["src"]:
                prefix = "../" * r["out"].count("/")
                body, toc, title = render_md(r["src"], blocks, smap, prefix)
                if r["src"].startswith("docs/kalkee/") and "README_" in r["src"]:
                    r["title"] = pretty(Path(r["src"]).name)
                pages.append((r, body, toc, title))
    # diagrams
    have = set()
    mm, ws = os.environ.get("MERMAID_JS"), os.environ.get("WS_MODULE_DIR")
    (OUT / "diagrams").mkdir(parents=True, exist_ok=True)
    if mm and ws and blocks:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "blocks.json").write_text(json.dumps(blocks))
        r = subprocess.run(["node", str(ROOT / "tools/render_mermaid.mjs"), mm, str(CACHE / "blocks.json"), str(OUT / "diagrams")], env={**os.environ, "WS_MODULE_DIR": ws}, capture_output=True, text=True, timeout=600)
        print(r.stdout.strip(), r.stderr.strip()[:300])
    have = {p.stem for p in (OUT / "diagrams").glob("*.svg")}
    for h in list(have):
        if h not in blocks:
            (OUT / "diagrams" / f"{h}.svg").unlink()
    have &= set(blocks)
    # pass 2: write pages
    index_rows = []
    for r, body, toc, title in pages:
        prefix = "../" * r["out"].count("/")
        body = diagrams(body, prefix, have, blocks)
        p = OUT / r["out"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(shell(title, body, groups, r["out"], toc), encoding="utf-8")
        text = re.sub(r"<[^>]+>", " ", body)
        index_rows.append({"t": title, "u": r["out"], "x": re.sub(r"\s+", " ", html.unescape(text))[:3000]})
    for name, fn in (("system.html", page_system), ("agents.html", page_agents)):
        body = fn()
        toc = [(2, m.group(1), re.sub(r"<[^>]+>", "", m.group(2))) for m in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', body)]
        (OUT / name).write_text(shell({"system.html": "How the system works", "agents.html": "All the agents"}[name], body, groups, name, toc), encoding="utf-8")
        index_rows.append({"t": {"system.html": "How the system works", "agents.html": "All the agents"}[name], "u": name, "x": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))[:3000]})
    (OUT / "index.html").write_text(shell("Documentation", page_index(groups), groups, "index.html"), encoding="utf-8")
    pyg = HtmlFormatter(style="default", cssclass="hl").get_style_defs(".hl")
    pyd = HtmlFormatter(style="monokai", cssclass="hl").get_style_defs(".hl")
    dark = "@media (prefers-color-scheme:dark){:root:not([data-theme=light]) " + pyd.replace("\n", " ").replace(".hl", ".hl").replace("}", "}\n:root:not([data-theme=light]) ").rsplit(":root", 1)[0] + "}"
    dark2 = "\n".join(":root[data-theme=dark] " + l for l in pyd.splitlines() if l.strip().startswith(".hl"))
    dark_media = "@media (prefers-color-scheme:dark){\n" + "\n".join(":root:not([data-theme=light]) " + l for l in pyd.splitlines() if l.strip().startswith(".hl")) + "\n}"
    (OUT / "docs.css").write_text(CSS + "\n/* code colours */\n" + pyg + "\n" + dark_media + "\n" + dark2 + "\n.hl{background:var(--code)!important}\n.hl pre{background:transparent;border:0;margin:0;padding:0}\n.hl{border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow:auto;margin:1em 0}\n", encoding="utf-8")
    (OUT / "docs.js").write_text(JS, encoding="utf-8")
    (OUT / "search-index.json").write_text(json.dumps(index_rows, ensure_ascii=False), encoding="utf-8")
    print(f"pages: {len(index_rows) + 1}, diagrams: {len(have)}/{len(blocks)} -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
