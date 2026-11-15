#!/usr/bin/env python3
"""Regenerate docs/FILES.md: every music-related file and what it holds, from each file's own header, plus hand-written lines (OV) where a file has none.
  python3 tools/gen_files_doc.py"""
import os, re, ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
SECTIONS = [("Music engine (`music_engine_framework_layer/mhraaga_engine/`)", "music_engine_framework_layer/mhraaga_engine"), ("Backend API (`tool_layer_mhraga/mhraaga-cloud/api/`)", "tool_layer_mhraga/mhraaga-cloud/api"),
            ("Website (`tool_layer_mhraga/mhraaga-cloud/web/`)", "tool_layer_mhraga/mhraaga-cloud/web"), ("Android app (`tool_layer_mhraga/mhraaga-app/lib/`)", "tool_layer_mhraga/mhraaga-app/lib"),
            ("AI singer worker (`tool_layer_mhraga/gpu-worker/`)", "tool_layer_mhraga/gpu-worker")]
OV = {
 "gan_weights.json": "The trained phrase-GAN weights (generator and discriminator matrices). Loaded by gan.py.",
 "poems_bank.json": "The bank of short rhymed spiritual-love poems per language, used by poems.py.",
 "library_profiles.json": "Pitch-class and tempo profiles of the reference tunes, used by the library_affinity critic. Only numbers, no audio.",
 "poems.json": "Candidate poems written offline by make_poems.py.",
 "policy.json": "The agents' learned beliefs: a Beta(alpha, beta) pair for every option of every agent, per language.",
 "compose.dart": "Create screen: prompt, styles, raga, tala, language, lead, tempo, length; sends /compose.", "library.dart": "My songs list.",
 "login.dart": "Sign in and create account screens.", "now_playing.dart": "The now-playing sheet: piano roll, lyrics, seek.", "ragas.dart": "Ragas browser with a Listen button.",
 "speech.dart": "Speech tab: type or dictate, translate, speak.", "main.dart": "App start, tabs and navigation.", "player.dart": "The one audio player: renders a song, plays it, ducks the music under the AI voice.",
 "playlist.dart": "The shared playlist tab.", "studio.dart": "Studio tab: the site's studio pages inside the app.", "synth.dart": "The Dart port of the synth: instruments, reverb and the WAV writer.",
 "ui.dart": "Shared look: the indigo background and widgets.", "api.dart": "The cloud client of the Android app.",
 "template.yaml": "CloudFormation: the S3 site bucket, CloudFront with the strict CSP, API Gateway with throttling, the Lambda and its least-privilege role, and the two DynamoDB tables.",
 "deploy.sh": "Builds the Lambda zip (handler, engine, Box2D wheel), updates the stack, syncs the site to S3, invalidates CloudFront, checks the raw API returns 403.",
 "test_agentic.py": "Producer agents, critics and the catalogue rules.", "test_engine_api.py": "The raga grammar, every tala landing on sam, lyrics, and the short-tala variety regression.",
 "test_physics_team.py": "Box2D physics, auto-tune, GAN and the shared studio.", "test_studio.py": "Rules, people and story routes.", "test_voice.py": "The neural voice endpoint: cache, caps, retries.",
 "test_admin.py": "The admin dashboard logic against an in-memory DynamoDB stand-in.", "test_jobs.py": "The AI-singer job queue and the Styles parser.", "test_poems.py": "Spoken poems: short rhymed lines, soft music, ending on Sa.",
 "dev.css": "Styles for the developers page.", "lame.min.js": "lamejs, the MP3 encoder used for downloads (third-party, vendored).", "login.js": "Sign in and sign up form logic.",
 "planck.LICENSE.txt": "Licence of planck.js.", "planck.mjs": "planck.js, the JavaScript Box2D engine used for film particles (third-party, vendored).", "ragas.js": "The Ragas page: catalogue, search and the Listen button.",
 "app.js": "The Create page and player: compose form, Styles box, song list, playback with instruments and voice, MP3 and WAV export.", "admin.css": "Styles for the admin dashboard.",
 "styles.css": "Base styles for the app pages.", "site.css": "Site-wide look: the Suno-style shell, sidebar, cards and motion.", "api.js": "Shared fetch helper: adds the token and sends you to sign in when the session ends.",
 "README.md": "How to set up and run the GPU worker.", "update_third_party.sh": "Checks the vendored upstream repos for new commits and can pull them.", "build_docs.py": "Builds the documentation site from the Markdown.",
 "gen_files_doc.py": "Regenerates this file.", "render_mermaid.mjs": "Pre-renders the Mermaid diagrams to SVG.", "publish_catalog.py": "Runs the song factory and publishes songs and reference tunes to S3 and the shared playlist.",
 "seed_playlist.py": "Composes the starter songs through the live API and publishes them to the shared playlist.", "mediakit.py": "Local media converter around ffmpeg.",
}
def sentence(t):
    t = " ".join(t.split()).replace(" ->", " to")
    parts, out = re.split(r"(?<=[.])\s+", t), ""
    for p in parts:                       # up to two sentences, at most 230 characters
        if out and len(out) + len(p) > 230: break
        out = (out + " " + p).strip()
        if out.count(". ") >= 1 and len(out) > 90: break
    return out[:230].rstrip(":") if out else t[:230]
def desc(fn, s):
    if fn in OV: return OV[fn]
    d = ""
    if fn.endswith(".py"):
        try: d = ast.get_docstring(ast.parse(s)) or ""
        except Exception: pass
        d = sentence(d.split("\n\n")[0])
    elif fn.endswith((".js", ".mjs", ".dart", ".sh", ".yaml", ".yml", ".css")):
        m = re.search(r"^(?://|#|/\*)\s*(.+?)\s*(?:\*/)?$", s, re.M); d = m.group(1) if m and not m.group(1).startswith(("!", "-")) else ""
        d = sentence(d.lstrip("/ "))
    elif fn.endswith(".html"):
        m = re.search(r"<title>(.*?)</title>", s); d = "The " + re.sub(r" · mhRaaga", "", m.group(1)) + " page." if m else ""
    return d
def walk(base):
    for dp, dn, fn in os.walk(base):
        dn[:] = sorted(d for d in dn if d not in ("__pycache__", "docs", "diagrams", "build", "node_modules", ".dart_tool", "catalog"))
        for f in sorted(fn):
            if not f.endswith((".svg", ".png", ".apk", ".pyc", ".ico", ".wav", ".mp3")): yield os.path.join(dp, f)
out = ["# Every music file, and what it holds\n", "Generated by `tools/gen_files_doc.py` from each file's own header line, with hand-written lines where a file has none. Folders of generated data are summarised in one row.\n"]
def rows(base, rel=True):
    r = []
    for p in walk(base):
        try: s = open(p, encoding="utf-8").read()
        except Exception: continue
        r.append((os.path.relpath(p, base) if rel else p, len(s.splitlines()), desc(os.path.basename(p), s)))
    return r
for title, base in SECTIONS:
    out.append(f"\n## {title}\n\n| File | Lines | What it holds |\n|---|---|---|")
    rs = rows(base)
    if base.endswith("mhraaga_engine"): rs.append(("agentic/data/catalog/", "~100 files", "Up to 100 generated songs (one JSON each: score, brief, review, genes), plus index.json and report.json."))
    for f, n, d in rs: out.append(f"| `{f}` | {n} | {d.replace('|', '/')} |")
out.append("\n## Infrastructure, tests, tools and CI\n\n| File | Lines | What it holds |\n|---|---|---|")
for base in ["tool_layer_mhraga/mhraaga-cloud/infra", "tool_layer_mhraga/mhraaga-cloud/tests", "tool_layer_mhraga/tools", "tools", ".github/workflows"]:
    for f, n, d in rows(base, rel=False):
        if f.endswith("ci.yml"): d = "GitHub Actions: tests and docs build on every push, installing ffmpeg with the vendored setup-ffmpeg action."
        if f.endswith("third-party-updates.yml"): d = "GitHub Actions: weekly check of the vendored upstream repos; opens a pull request when something moved."
        out.append(f"| `{f}` | {n} | {d.replace('|', '/')} |")
out.append("\n## Vendored upstream repos (`third_party/`)\nSee [THIRD_PARTY.md](THIRD_PARTY.md).")
open("docs/FILES.md", "w").write("\n".join(out) + "\n")
print(len(out), "lines;", sum(1 for l in out if l.endswith("|  |")), "rows without a description")
