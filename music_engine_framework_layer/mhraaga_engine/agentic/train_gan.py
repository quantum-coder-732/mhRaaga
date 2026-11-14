"""Train the phrase GAN (numpy). Offline tooling: python -m mhraaga_engine.agentic.train_gan
Data: 8-note phrases from the grammar (pakad, rise, fall) of every classical raga and a sample of melakartas and gopi ragas.
Writes mhraaga_engine/gan_weights.json (read by gan.py, no numpy needed at runtime)."""
import json, os, random
import numpy as np
from ..ragas import get_raga, catalog
from ..compose import _Phrases

ZD, H = 6, 16

def harvest(n_per=40, seed=1):
    rng = random.Random(seed); data = []
    cat = catalog()
    specs = [r["name"] for r in cat["classical"]] + [f"mela:{i}" for i in range(1, 73, 3)] + [f"gopi:{rng.randrange(1, 16000)}" for _ in range(40)]
    for sp in specs:
        try: r = get_raga(sp)
        except Exception: continue
        P = _Phrases(r, rng)
        for _ in range(n_per):
            seq = [n for n, _b in rng.choice([P.rise, P.fall])(rng.random() < .5)]
            if len(seq) < 4: continue
            seq = (seq + [seq[-1]] * 8)[:8]
            data.append([(n - 6) / 12 for n in seq])
    return np.array(data, dtype=np.float64)

def lrelu(x): return np.where(x > 0, x, 0.2 * x)
def dlrelu(x): return np.where(x > 0, 1.0, 0.2)
def sig(x): return 1 / (1 + np.exp(-np.clip(x, -30, 30)))

def main(steps=6000, bs=64, lr=0.02):
    rs = np.random.RandomState(0); X = harvest(); print("phrases", X.shape)
    P = {"G1": rs.randn(ZD, H) * .4, "g1": np.zeros(H), "G2": rs.randn(H, 8) * .4, "g2": np.zeros(8),
         "D1": rs.randn(8, H) * .4, "d1": np.zeros(H), "D2": rs.randn(H, 1) * .4, "d2": np.zeros(1)}
    def G(z): a = z @ P["G1"] + P["g1"]; h = np.tanh(a); o = np.tanh(h @ P["G2"] + P["g2"]); return a, h, o
    def D(x): a = x @ P["D1"] + P["d1"]; h = lrelu(a); o = sig(h @ P["D2"] + P["d2"]); return a, h, o
    for it in range(steps):
        real = X[rs.randint(0, len(X), bs)]; z = rs.randn(bs, ZD); _, _, fake = G(z)
        for x, y in ((real, 1.0), (fake, 0.0)):                      # discriminator step
            a, h, o = D(x); d = (o - y) / bs; gD2 = h.T @ d; gd2 = d.sum(0); dh = d @ P["D2"].T * dlrelu(a)
            P["D2"] -= lr * gD2; P["d2"] -= lr * gd2; P["D1"] -= lr * (x.T @ dh); P["d1"] -= lr * dh.sum(0)
        z = rs.randn(bs, ZD); ga, gh, fake = G(z); a, h, o = D(fake)   # generator step (non-saturating loss)
        d = (o - 1.0) / bs; dh = d @ P["D2"].T * dlrelu(a); dx = dh @ P["D1"].T
        do = dx * (1 - fake ** 2); gG2 = gh.T @ do; gg2 = do.sum(0); dgh = do @ P["G2"].T * (1 - gh ** 2)
        P["G2"] -= lr * gG2; P["g2"] -= lr * gg2; P["G1"] -= lr * (z.T @ dgh); P["g1"] -= lr * dgh.sum(0)
        if it % 1000 == 0: print(it, "D(real)=%.2f D(fake)=%.2f" % (D(real)[2].mean(), D(G(rs.randn(256, ZD))[2])[2].mean()))
    out = os.path.join(os.path.dirname(__file__), "..", "gan_weights.json")
    json.dump({k: np.round(v, 5).tolist() for k, v in P.items()}, open(out, "w")); print("wrote", os.path.abspath(out))

if __name__ == "__main__": main()
