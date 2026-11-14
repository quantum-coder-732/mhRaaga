"""The self-improving loop.

producer agents (raga, tala, tempo, lead, lyrics) each pick an arm by Thompson sampling -> composer renders a score ->
critics review it -> Kalkee's Shapley module splits the reward across the agents (each agent's quality = mean of the
critics that judge its work) -> every agent's Beta posterior for the arm it picked is updated.
Songs live in a catalog capped at CAP songs with a per-language quota; a better song replaces the weakest one of its
language, and weak songs are also re-composed ("improve") with new seeds and one mutated gene."""
from __future__ import annotations

import importlib.util
import json
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..compose import compose
from ..lyrics_bank import BANK, MOOD_THEME, THEMES, make_lyrics
from ..ragas import _CLASS, get_raga
from ..tala import TALAS
from . import critics

HERE = Path(__file__).parent
STATE = HERE / "data" / "policy.json"
CAP = 100
LANGS = tuple(BANK)
QUOTA = {l: CAP // len(LANGS) + (1 if i < CAP % len(LANGS) else 0) for i, l in enumerate(LANGS)}
KALKEE = HERE.parents[2] / "orchestrator_framework_layer_kalkee/orchestrator_framework_layer/akanade/backend/app/framework/shapley.py"

CLASSICAL = [r["name"] for r in _CLASS.values()]
ARMS = {
    "raga": ["classical", "gopi", "mela"],
    "tala": ["teental", "keherwa", "dadra", "rupak", "jhaptal", "ektal", "adi"],
    "tempo": [54, 62, 70, 80, 92, 104],
    "lead": ["bansuri", "harmonium", "veena"],
    "theme": list(THEMES),
    "tonic": [183.0, 233.0, 234.0],
}
# which critics judge which agent's work
JUDGES = {"raga": ["raga_fidelity", "library_affinity"], "tala": ["cadence", "rhythm"], "tempo": ["rhythm", "library_affinity"],
          "lead": ["contour", "phrase_variety"], "theme": ["lyrics_fit"], "tonic": ["library_affinity", "raga_fidelity"]}
THEME_WORD = {
    "hindi": {"dawn": "भोर", "krishna": "मुरली", "rain": "बरखा", "night": "रात"}, "marathi": {"dawn": "पहाट", "krishna": "बासरी", "rain": "श्रावण", "night": "रात्र"},
    "english": {"dawn": "Dawn", "krishna": "Flute", "rain": "Rain", "night": "Night"}, "telugu": {"dawn": "ఉదయం", "krishna": "వేణువు", "rain": "వర్షం", "night": "రాత్రి"},
    "gujarati": {"dawn": "પ્રભાત", "krishna": "વાંસળી", "rain": "વરસાદ", "night": "રાત"}, "kannada": {"dawn": "ಮುಂಜಾನೆ", "krishna": "ಕೊಳಲು", "rain": "ಮಳೆ", "night": "ರಾತ್ರಿ"},
    "tamil": {"dawn": "விடியல்", "krishna": "குழல்", "rain": "மழை", "night": "இரவு"},
}


def _shapley():
    try:
        spec = importlib.util.spec_from_file_location("kalkee_shapley", KALKEE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.attribute_reward, "kalkee"
    except Exception:
        def fair(quality, total, seed=None):  # same efficiency property, proportional split
            z = sum(quality.values()) or 1.0
            return {a: total * q / z for a, q in quality.items()}
        return fair, "local-fallback"


attribute_reward, ATTRIBUTION = _shapley()


class Policy:
    """Per-language Beta posteriors for every (agent, arm). Persisted so each run starts where the last one stopped."""

    def __init__(self, path: Path = STATE):
        self.path = path
        self.s = json.loads(path.read_text()) if path.exists() else {"runs": 0, "n": 0, "arms": {}}

    def _ab(self, lang, agent, arm):
        return self.s["arms"].setdefault(lang, {}).setdefault(agent, {}).setdefault(str(arm), [1.0, 1.0])

    def pick(self, lang, agent, rng):
        arms = ARMS[agent]
        return max(arms, key=lambda a: rng.betavariate(*self._ab(lang, agent, a)))

    def update(self, lang, genes, review):
        q = {a: sum(review["scores"][c] for c in cs) / len(cs) for a, cs in JUDGES.items()}
        credit = attribute_reward(q, review["reward"])
        for agent, r in credit.items():
            p = max(0.0, min(1.0, r * len(q)))  # equal share == the song's own reward
            ab = self._ab(lang, agent, genes[agent])
            ab[0] += p
            ab[1] += 1 - p
        self.s["n"] += 1
        return credit

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.s, ensure_ascii=False, indent=1))

    def leaders(self, lang):
        out = {}
        for agent, arms in self.s["arms"].get(lang, {}).items():
            best = max(arms.items(), key=lambda kv: kv[1][0] / (kv[1][0] + kv[1][1]))
            out[agent] = {"arm": best[0], "mean": round(best[1][0] / (best[1][0] + best[1][1]), 3), "trials": round(sum(a + b for a, b in arms.values()) - 2 * len(arms))}
        return out


def render(lang: str, genes: dict, seed: int, duration: int = 96) -> dict:
    rng = random.Random(seed)
    kind = genes["raga"]
    spec = rng.choice(CLASSICAL) if kind == "classical" else f"gopi:{rng.randint(1, 16000)}" if kind == "gopi" else f"mela:{rng.randint(1, 72)}"
    raga = get_raga(spec, genes["tonic"])
    lyrics, theme = make_lyrics(lang, genes["theme"], rng)
    score = compose(raga, genes["tala"], genes["tempo"], duration, lyrics, seed=seed, sa=genes["tonic"], lead=genes["lead"])
    title = f"{THEME_WORD[lang][theme]} · {raga['name']}"
    brief = {"title": title, "raga": spec, "tala": genes["tala"], "tempo_bpm": genes["tempo"], "mood": theme, "language": lang,
             "lead": genes["lead"], "lyrics": lyrics, "source": "agentic"}
    return {"title": title, "raga": raga["name"], "spec": spec, "brief": brief, "score": score}


def make_song(lang: str, genes: dict, seed: int, parent: dict | None = None, gen: int = 0) -> dict:
    s = render(lang, genes, seed)
    rv = critics.review(s["score"], s["brief"])
    sc = s["score"]
    sid = f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:6]}"
    sc["meta"]["agentic"] = {"genes": genes, "seed": seed, "reward": rv["reward"], "scores": rv["scores"], "generation": gen}
    return {"id": sid, "title": s["title"], "raga": s["raga"], "tala": sc["meta"]["tala"], "tempo": sc["meta"]["tempo"], "mood": s["brief"]["mood"],
            "language": lang, "duration": sc["duration"], "created": datetime.now(timezone.utc).isoformat(), "source": "agentic",
            "prompt": f"{lang} · {s['brief']['mood']} · agentic gen {gen}", "brief": s["brief"], "score": sc,
            "reward": rv["reward"], "review": rv, "genes": genes, "seed": seed, "generation": gen, "parent": parent["id"] if parent else None}


class Catalog:
    def __init__(self, folder: Path):
        self.dir = folder
        self.dir.mkdir(parents=True, exist_ok=True)
        self.songs = {}
        for f in self.dir.glob("*.json"):
            if f.name not in ("index.json", "report.json"):
                d = json.loads(f.read_text())
                self.songs[d["id"]] = d

    def of(self, lang):
        return sorted((s for s in self.songs.values() if s["language"] == lang), key=lambda s: -s["reward"])

    def offer(self, song: dict, replaces: str | None = None) -> str | None:
        """Add `song` (or swap it for the song it improves). Returns the id it displaced, '' if it only filled a slot, None if rejected."""
        lang = song["language"]
        if replaces and replaces in self.songs:
            if song["reward"] > self.songs[replaces]["reward"] + 0.003:
                self._drop(replaces)
                self._put(song)
                return replaces
            return None
        have = self.of(lang)
        if len(have) < QUOTA[lang]:
            self._put(song)
            return ""
        if song["reward"] > have[-1]["reward"] + 0.003:
            self._drop(have[-1]["id"])
            self._put(song)
            return have[-1]["id"]
        return None

    def _put(self, s):
        self.songs[s["id"]] = s
        (self.dir / f"{s['id']}.json").write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")))

    def _drop(self, sid):
        self.songs.pop(sid, None)
        (self.dir / f"{sid}.json").unlink(missing_ok=True)

    def index(self):
        rows = [{k: s[k] for k in ("id", "title", "raga", "tala", "tempo", "mood", "language", "duration", "created", "source", "prompt", "reward", "generation")}
                for s in sorted(self.songs.values(), key=lambda s: (s["language"], -s["reward"]))]
        (self.dir / "index.json").write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(), "cap": CAP, "songs": rows}, ensure_ascii=False))
        return rows


def run(catalog_dir: Path, rounds: int = 4, explore: int = 6, improve: int = 3, seed: int | None = None, log=print) -> dict:
    rng = random.Random(seed)
    pol, cat = Policy(), Catalog(catalog_dir)
    stats = {"made": 0, "accepted": 0, "improved": 0, "attribution": ATTRIBUTION}
    for rd in range(rounds):
        gen = pol.s["runs"] * 100 + rd
        for lang in LANGS:
            for _ in range(explore):  # explore/exploit: Thompson-sampled genes
                genes = {a: pol.pick(lang, a, rng) for a in ARMS}
                song = make_song(lang, genes, rng.randrange(1 << 30), gen=gen)
                pol.update(lang, genes, song["review"])
                stats["made"] += 1
                if cat.offer(song) is not None:
                    stats["accepted"] += 1
            for old in cat.of(lang)[-improve:]:  # improve the weakest: new seed, one gene re-sampled from the posterior
                for _ in range(2):
                    genes = dict(old["genes"])
                    a = rng.choice(list(ARMS))
                    genes[a] = pol.pick(lang, a, rng)
                    song = make_song(lang, genes, rng.randrange(1 << 30), parent=old, gen=gen + 1)
                    pol.update(lang, genes, song["review"])
                    stats["made"] += 1
                    if cat.offer(song, replaces=old["id"]) is not None:
                        stats["improved"] += 1
                        break
        mean = sum(s["reward"] for s in cat.songs.values()) / max(1, len(cat.songs))
        log(f"round {rd + 1}/{rounds}: catalog {len(cat.songs)}/{CAP}, mean reward {mean:.4f}")
        stats.setdefault("curve", []).append(round(mean, 4))
    pol.s["runs"] += 1
    pol.save()
    cat.index()
    stats["size"], stats["mean_reward"] = len(cat.songs), stats["curve"][-1]
    stats["leaders"] = {l: pol.leaders(l) for l in LANGS}
    return stats
