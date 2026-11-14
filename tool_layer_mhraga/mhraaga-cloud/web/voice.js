// Pick the best speech voice the device offers: exact language first, then neural / natural / online voices over the plain default.
export function bestVoice(voices, lang, preferred = "") {
  if (!voices || !voices.length) return null;
  const want = (lang || "en-IN").replace("_", "-"), pre = want.slice(0, 2).toLowerCase();
  if (preferred) { const p = voices.find((v) => v.voiceURI === preferred || v.name === preferred); if (p) return p; }
  const score = (v) => { const l = v.lang.replace("_", "-"); let s = 0;
    if (l.toLowerCase() === want.toLowerCase()) s += 10; else if (l.slice(0, 2).toLowerCase() === pre) s += 5; else return -1;
    if (/natural|neural|online|enhanced|premium|wavenet|studio/i.test(v.name)) s += 6;
    if (/google/i.test(v.name)) s += 3;
    if (v.localService === false) s += 2;
    if (/espeak|compact|mbrola/i.test(v.name)) s -= 6;
    return s; };
  return voices.map((v) => [score(v), v]).filter((x) => x[0] >= 0).sort((a, b) => b[0] - a[0])[0]?.[1] || null;
}
