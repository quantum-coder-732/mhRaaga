// mhRaaga synth: renders a score (from the API) with Web Audio. Same code drives live playback and offline WAV export.

export function reverbIR(ctx, seconds = 2.4) {
  // A room, not white noise: 20 ms pre-delay, a few early reflections, then a tail that darkens as it decays (air absorbs highs).
  const sr = ctx.sampleRate, n = Math.floor(sr * seconds), pre = Math.floor(sr * 0.02), b = ctx.createBuffer(2, n, sr);
  for (let c = 0; c < 2; c++) {
    const d = b.getChannelData(c); let lp = 0, seed = 12345 + c * 777;
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2147483648) - 1;
    for (let i = pre; i < n; i++) {
      const x = (i - pre) / (n - pre), a = 0.55 - 0.47 * Math.min(1, x * 1.6);      // low-pass gets heavier with time
      lp += (rnd() - lp) * a; d[i] = lp * Math.pow(1 - x, 2.4) * 2.2;
    }
    for (const [ms, g] of [[11, 0.5], [19, 0.38], [29, 0.3], [41, 0.22], [57, 0.16]]) d[Math.floor(sr * (ms + c * 2.3) / 1000)] += g * (c ? -1 : 1);
  }
  return b;
}
function noiseBuf(ctx) {
  const b = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return b;
}
// A set of harmonics as a periodic wave. amps[k-1] is partial k.
function harm(ctx, amps) {
  const re = new Float32Array(amps.length + 1), im = new Float32Array(amps.length + 1);
  amps.forEach((a, i) => { im[i + 1] = a; });
  return ctx.createPeriodicWave(re, im);
}

// Karplus-Strong plucked string, rendered once per pitch into a buffer: a real string model (a delay loop with loss), so the
// attack, the way highs die first, and the slow beating all happen the way they do on a tanpura or veena.
// `buzz` adds the jawari bridge: a soft clip that makes the early sound bright and lets it mellow as the string quietens.
const _pluck = new Map();
function pluckBuf(ctx, f, secs, rho, bright, buzz, seed) {
  const key = [ctx.sampleRate, Math.round(f * 8), secs, rho, bright, buzz].join("|");
  if (_pluck.has(key)) return _pluck.get(key);
  const sr = ctx.sampleRate, len = Math.floor(sr * secs), want = sr / f - 0.5, N = Math.max(2, Math.floor(want)), frac = want - N;
  const ap = (1 - frac) / (1 + frac), line = new Float32Array(N + 1), out = ctx.createBuffer(1, len, sr), d = out.getChannelData(0);
  let s = (seed || 1) >>> 0;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2147483648) - 1;
  let lp = 0;
  for (let i = 0; i <= N; i++) { lp += (rnd() - lp) * bright; line[i] = lp * (0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, i / (N * 0.25)))); }  // plucked near one end
  let idx = 0, prev = 0, apx = 0, apy = 0, peak = 1e-9;
  for (let i = 0; i < len; i++) {
    const a = line[idx], b2 = line[(idx + 1) % (N + 1)];
    let y = rho * (0.5 * a + 0.5 * b2);                                  // loss filter: highs fade first
    const ay = ap * (y - apy) + apx; apx = y; apy = ay; y = ay;           // fine tuning to the exact pitch
    line[idx] = y; idx = (idx + 1) % (N + 1);
    const o = buzz ? Math.tanh(buzz * y) : y;
    d[i] = o - prev * 0.995; prev = o;                                    // remove DC
    peak = Math.max(peak, Math.abs(d[i]));
  }
  for (let i = 0; i < len; i++) d[i] /= peak;
  const fade = Math.floor(sr * 0.05); for (let i = 0; i < fade; i++) d[len - 1 - i] *= i / fade;
  _pluck.set(key, out);
  return out;
}
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

export function master(ctx, volume = 0.8) {
  const out = ctx.createGain(); out.gain.value = volume;
  const comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 1.8; comp.attack.value = 0.02; comp.release.value = 0.25;
  const dry = ctx.createGain(), wet = ctx.createGain(), conv = ctx.createConvolver();
  dry.gain.value = 0.74; wet.gain.value = 0.34; conv.buffer = reverbIR(ctx);
  const bus = ctx.createGain(), duck = ctx.createGain(), voice = ctx.createGain(); bus.gain.value = 1.5;   // `duck` lets the music step back while someone speaks
  bus.connect(duck); duck.connect(dry); duck.connect(conv); conv.connect(wet); dry.connect(comp); wet.connect(comp);
  // Warmth: a soft tape-style saturation (unity for quiet sounds, rounds the peaks) and a gentle roll-off of the digital top end.
  const sat = ctx.createWaveShaper(), curve = new Float32Array(2049); for (let i = 0; i < 2049; i++) { const x = (i - 1024) / 1024; curve[i] = Math.tanh(1.5 * x) / 1.5; }
  sat.curve = curve; sat.oversample = "2x";
  const shelf = ctx.createBiquadFilter(); shelf.type = "highshelf"; shelf.frequency.value = 6500; shelf.gain.value = -4;
  const low = ctx.createBiquadFilter(); low.type = "lowshelf"; low.frequency.value = 160; low.gain.value = 4;
  comp.connect(sat); sat.connect(shelf); shelf.connect(low); low.connect(out);
  const lim = ctx.createDynamicsCompressor(); lim.threshold.value = -3; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.002; lim.release.value = 0.12;   // limiter: peaks never clip
  out.connect(lim); lim.connect(ctx.destination);
  voice.gain.value = 1.4; voice.connect(dry); voice.connect(conv);   // the voice joins after the duck, so it is never turned down, and shares the room reverb
  return { bus, out, duck, voice };
}

// Dip the music to `level` for `dur` seconds starting at ctx time `t`, then release slowly (sidechain-style ducking).
export function duckAt(m, t, dur, level = 0.45) {
  const g = m.duck.gain; g.setTargetAtTime(level, t, 0.1); g.setTargetAtTime(1, t + dur, 0.45);
}
export const duckNow = (ctx, m, level = 0.4) => m.duck.gain.setTargetAtTime(level, ctx.currentTime, 0.1);
export const releaseNow = (ctx, m) => m.duck.gain.setTargetAtTime(1, ctx.currentTime, 0.5);

// A soft sustained pad: Sa, Pa and the octave as slow detuned voices, so speech has a warm floor without a melody competing with it.
function pad(ctx, dest, sa, t, dur, vol) {
  const g = ctx.createGain(), lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 800;
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol, t + dur * 0.35); g.gain.linearRampToValueAtTime(0.0001, t + dur);
  for (const [m, det] of [[1, -5], [1, 6], [1.5, 0], [2, 3], [0.5, 0]]) {
    const o = ctx.createOscillator(); o.type = m === 0.5 ? "sine" : "triangle"; o.frequency.value = sa * m; o.detune.value = det;
    const lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = 0.13 + Math.random() * 0.2; lg.gain.value = 3; lfo.connect(lg); lg.connect(o.detune); lfo.start(t); lfo.stop(t + dur + 0.1);
    o.connect(g); o.start(t); o.stop(t + dur + 0.1);
  }
  g.connect(lp); lp.connect(dest);
}

// Background for speech (stories, pravachan, bhajan recitation, film narration): tanpura and pad only. No lead, no tabla.
// Returns { m, stop } ; call stop() or close the context to end it.
export function startBed(ctx, level = 0.5, sa = 233) {
  const m = master(ctx, level), t0 = ctx.currentTime + 0.1, tp = 1.5, strings = [sa * 1.5, sa, sa, sa / 2], total = 600;
  for (let k = 0, t = 0; t < total; k++, t += tp) tanpura(ctx, m.bus, strings[k % 4], t0 + t, k % 4 === 3 ? 0.13 : 0.1, 4.2);
  for (let t = 0; t < total; t += 9) pad(ctx, m.bus, sa, t0 + t, 14, 0.05);
  return { m, stop: () => { try { m.out.gain.setTargetAtTime(0, ctx.currentTime, 0.4); } catch {} } };
}

// Tanpura: four plucked strings with the jawari buzz. Each pluck is a real string model, and the strings overlap and ring together.
function tanpura(ctx, dest, f, t, vol, life) {
  const src = ctx.createBufferSource(), g = ctx.createGain();
  src.buffer = pluckBuf(ctx, f, 5, 0.9992, 0.5, 2.6, Math.round(f * 3));
  src.playbackRate.value = 1 + (Math.random() - 0.5) * 0.0006;
  g.gain.setValueAtTime(vol * 7, t); g.gain.exponentialRampToValueAtTime(0.0002, t + life + 0.8);
  src.connect(g); g.connect(dest); src.start(t); src.stop(t + life + 0.9);
}

// The low end that real recordings have and a bare flute does not: the tanpura's bass string ringing on, and the body of the room. Measured against
// recordings, the old mix had no energy below 200 Hz, which is what made it sound thin and "tinny".
function subBass(ctx, dest, f, t, dur, vol) {
  const g = ctx.createGain(), lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 340; lp.Q.value = 0.4;
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol, t + 2.5); g.gain.setValueAtTime(vol, Math.max(t + 2.5, t + dur - 3)); g.gain.linearRampToValueAtTime(0.0001, t + dur);
  for (const [type, m, det, lv] of [["triangle", 1, -3, 0.6], ["sine", 1, 4, 0.7], ["sine", 2, 0, 0.18], ["sine", 0.5, 0, 0.35]]) {
    const o = ctx.createOscillator(), og = ctx.createGain(); o.type = type; o.frequency.value = f * m; o.detune.value = det; og.gain.value = lv;
    const lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = 0.11 + Math.random() * 0.1; lg.gain.value = 0.12 * lv; lfo.connect(lg); lg.connect(og.gain); lfo.start(t); lfo.stop(t + dur + 0.1);
    o.connect(og); og.connect(g); o.start(t); o.stop(t + dur + 0.1);
  }
  g.connect(lp); lp.connect(dest);
}

// Bansuri: a bamboo flute. A blown tube has a strong fundamental, weak overtones, a puff of air at the start, breath noise all through
// the note, a slow vibrato that arrives after the note has begun, and pitch that is never perfectly still.
function bansuri(ctx, dest, nz, f, t, d, orn, prev, vol, gl) {
  const a = 0.09 + Math.random() * 0.03, rel = 0.18, end = t + d;
  const body = ctx.createOscillator(), g = ctx.createGain(), tone = ctx.createBiquadFilter();
  body.setPeriodicWave(harm(ctx, [1, 0.62 + Math.random() * 0.08, 0.3, 0.16, 0.08, 0.04]));
  tone.type = "lowpass"; tone.frequency.value = clamp(f * 6.5, 2200, 6500); tone.Q.value = 0.5;
  const start = orn === 1 && prev ? prev : orn === 2 ? f * 1.0595 : f * 0.985;           // an unslurred note is scooped up into pitch
  const glide = orn === 1 ? (gl || Math.min(0.16, d * 0.45)) : orn === 2 ? 0.07 : 0.05;
  body.frequency.setValueAtTime(start, t); body.frequency.exponentialRampToValueAtTime(f, t + glide);
  const vib = ctx.createOscillator(), vg = ctx.createGain(); vib.frequency.value = 4.7 + Math.random() * 0.9;
  vg.gain.setValueAtTime(0, t); vg.gain.setValueAtTime(0, t + 0.22); vg.gain.linearRampToValueAtTime(f * 0.0065, t + 0.7);
  vib.connect(vg); vg.connect(body.frequency); vib.start(t); vib.stop(end + rel);
  const drift = ctx.createOscillator(), dg = ctx.createGain(); drift.frequency.value = 0.4 + Math.random() * 0.5; dg.gain.value = f * 0.0016; drift.connect(dg); dg.connect(body.frequency); drift.start(t); drift.stop(end + rel);
  const trem = ctx.createOscillator(), tg = ctx.createGain(), tgain = ctx.createGain(); trem.frequency.value = vib.frequency.value; tg.gain.value = 0.05; tgain.gain.value = 1;   // breath pulses with the vibrato
  trem.connect(tg); tg.connect(tgain.gain); trem.start(t); trem.stop(end + rel);
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol * 1.12, t + a * 0.8); g.gain.linearRampToValueAtTime(vol * 0.9, t + a + 0.12);
  g.gain.setValueAtTime(vol * 0.92, Math.max(t + a + 0.12, end - 0.02)); g.gain.exponentialRampToValueAtTime(0.0002, end + rel);
  body.connect(tone); tone.connect(tgain); tgain.connect(g);
  const n = ctx.createBufferSource(); n.buffer = nz; n.loop = true;
  const bp = ctx.createBiquadFilter(), ng = ctx.createGain(); bp.type = "bandpass"; bp.frequency.value = clamp(f * 2.4, 700, 4200); bp.Q.value = 0.8;
  ng.gain.setValueAtTime(0.0001, t); ng.gain.linearRampToValueAtTime(vol * 0.46, t + 0.018); ng.gain.exponentialRampToValueAtTime(vol * 0.11, t + 0.2); ng.gain.setValueAtTime(vol * 0.11, Math.max(t + 0.2, end - 0.05)); ng.gain.exponentialRampToValueAtTime(0.0002, end + rel);
  n.connect(bp); bp.connect(ng); ng.connect(g);
  g.connect(dest);
  body.start(t); body.stop(end + rel + 0.05); n.start(t, Math.random() * 0.5); n.stop(end + rel + 0.05);
}

// Harmonium: free reeds driven by bellows. Two reed banks a hair out of tune (the chorus you hear), a lower octave bank, a slow
// uneven bellows pressure, a wooden body that boosts 700 and 2100 Hz, and the rattle of the reeds under the note.
function harmonium(ctx, dest, f, t, d, orn, prev, vol, gl) {
  const end = t + d, rel = 0.14, g = ctx.createGain();
  const body1 = ctx.createBiquadFilter(), body2 = ctx.createBiquadFilter(), lp = ctx.createBiquadFilter();
  body1.type = "peaking"; body1.frequency.value = 700; body1.Q.value = 1.1; body1.gain.value = 4;
  body2.type = "peaking"; body2.frequency.value = 2100; body2.Q.value = 1.4; body2.gain.value = 3;
  lp.type = "lowpass"; lp.frequency.value = 2600; lp.Q.value = 0.5;
  const reed = []; for (let k = 1; k <= 22; k++) reed.push(1 / Math.pow(k, 0.95) * (k % 2 ? 1 : 0.8));
  const wv = harm(ctx, reed);
  const att = 0.07 + Math.random() * 0.03;
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol * 0.8, t + att); g.gain.setValueAtTime(vol * 0.8, Math.max(t + att, end - 0.02)); g.gain.exponentialRampToValueAtTime(0.0002, end + rel);
  const start = orn === 1 && prev ? prev : f, glide = orn === 1 ? (gl || Math.min(0.12, d * 0.4)) : 0;
  const bell = ctx.createOscillator(), bg = ctx.createGain(); bell.frequency.value = 0.35 + Math.random() * 0.2; bg.gain.value = 0.035 * vol; bell.connect(bg); bg.connect(g.gain); bell.start(t); bell.stop(end + rel);
  for (const [m, det, lv] of [[1, 6, 0.42], [1, -7, 0.42], [0.5, 1, 0.2], [2, 3, 0.07]]) {
    const o = ctx.createOscillator(), og = ctx.createGain(); o.setPeriodicWave(wv); o.detune.value = det; og.gain.value = lv;
    if (glide) { o.frequency.setValueAtTime(start * m, t); o.frequency.exponentialRampToValueAtTime(f * m, t + glide); } else o.frequency.value = f * m;
    o.connect(og); og.connect(lp); o.start(t); o.stop(end + rel + 0.05);
  }
  lp.connect(body1); body1.connect(body2); body2.connect(g); g.connect(dest);
}

// Veena / sitar-like lead: a plucked string with the bridge buzz, so every note starts bright and sings down. A meend is a real
// pitch slide of the sounding string.
function veena(ctx, dest, f, t, d, orn, prev, vol, gl) {
  const life = clamp(d * 1.6, 0.8, 3.2), src = ctx.createBufferSource(), g = ctx.createGain(), lp = ctx.createBiquadFilter();
  src.buffer = pluckBuf(ctx, f, 3.4, 0.9987, 0.62, 1.6, Math.round(f * 7));
  const from = orn === 1 && prev ? prev / f : 1;
  if (from !== 1) { src.playbackRate.setValueAtTime(from, t); src.playbackRate.exponentialRampToValueAtTime(1, t + (gl || Math.min(0.12, d * 0.4))); }
  lp.type = "lowpass"; lp.frequency.setValueAtTime(5200, t); lp.frequency.exponentialRampToValueAtTime(1100, t + life);
  g.gain.setValueAtTime(vol * 1.5, t); g.gain.setValueAtTime(vol * 1.5, t + Math.min(d, life) * 0.5); g.gain.exponentialRampToValueAtTime(0.0002, t + life);
  src.connect(lp); lp.connect(g); g.connect(dest); src.start(t); src.stop(t + life + 0.05);
}

// Tabla by its modes. The dayan (right drum) rings at harmonic partials of Sa that decay at different rates, with a skin slap and a
// rim click at the start. The bayan (left drum) is a low boom whose pitch rises when the heel presses, with a wet thud.
function tabla(ctx, dest, nz, sa, bol, cls, t, vol) {
  const day = clamp(sa, 150, 300), bay = clamp(sa / 2, 70, 140), low = bol.toLowerCase();
  const jit = (Math.random() - 0.5) * 0.008; t += Math.max(0, jit); vol *= 0.9 + Math.random() * 0.2;       // no two strokes are the same
  const mode = (f0, f1, dur, v) => {
    const o = ctx.createOscillator(), g = ctx.createGain(); o.type = "sine";
    o.frequency.setValueAtTime(f0, t); if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(f1, t + Math.min(0.12, dur * 0.4));
    g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.0002, t + dur); o.connect(g); g.connect(dest); o.start(t); o.stop(t + dur + 0.02);
  };
  const hit = (freq, q, dur, v) => {
    const n = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), g = ctx.createGain(); n.buffer = nz;
    bp.type = "bandpass"; bp.frequency.value = freq; bp.Q.value = q; g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.0002, t + dur);
    n.connect(bp); bp.connect(g); g.connect(dest); n.start(t, Math.random() * 0.5); n.stop(t + dur + 0.01);
  };
  if (cls === "left" || cls === "both") {
    const muted = low === "ka" || low === "kat" || low === "ke";
    if (muted) { hit(900, 2, 0.05, 0.3 * vol); mode(bay * 1.2, bay, 0.07, 0.35 * vol); }
    else { mode(bay * 1.7, bay * 0.92, 0.62, 1.5 * vol); mode(bay * 2.6, bay * 1.9, 0.18, 0.18 * vol); hit(320, 1.2, 0.05, 0.22 * vol); }
  }
  if (cls === "right" || cls === "both") {
    const rim = ["na", "ti", "ra", "ki", "tu", "te"].includes(low), len = rim ? 0.2 : 0.7;
    const parts = rim ? [[1, 0.5], [2, 0.34], [3, 0.2], [4, 0.1]] : [[1, 0.52], [2, 0.3], [3, 0.2], [4, 0.1], [5, 0.06]];
    parts.forEach(([k, v], i) => mode(day * k * 1.02, day * k, len / (1 + i * 0.7), v * 0.8 * vol));
    hit(rim ? 3800 : 2400, 1.3, 0.03, 0.28 * vol); hit(1500, 0.9, 0.018, 0.15 * vol);
  }
}

// Manjira: a pair of small brass cymbals. Inharmonic metal partials that ring, played softly on the beat in devotional songs.
function manjira(ctx, dest, nz, t, vol) {
  for (const [f, v, dur] of [[2870, 1, 0.34], [4130, 0.7, 0.26], [5870, 0.5, 0.2], [7420, 0.3, 0.14]]) {
    const o = ctx.createOscillator(), g = ctx.createGain(); o.type = "sine"; o.frequency.value = f * (1 + (Math.random() - 0.5) * 0.004);
    g.gain.setValueAtTime(vol * v * 0.06, t); g.gain.exponentialRampToValueAtTime(0.0002, t + dur); o.connect(g); g.connect(dest); o.start(t); o.stop(t + dur + 0.02);
  }
  const n = ctx.createBufferSource(), hp = ctx.createBiquadFilter(), g = ctx.createGain(); n.buffer = nz; hp.type = "highpass"; hp.frequency.value = 5000;
  g.gain.setValueAtTime(vol * 0.05, t); g.gain.exponentialRampToValueAtTime(0.0002, t + 0.05); n.connect(hp); hp.connect(g); g.connect(dest); n.start(t, Math.random() * 0.5); n.stop(t + 0.06);
}

// Dholak: the two-headed hand drum of qawwali and bhajan. A deep boom from the bass head on strong beats and a dry slap from the treble head on the others.
function dholak(ctx, dest, nz, sa, t, vol, strong) {
  const bay = clamp(sa / 2, 70, 140) * 0.9, o = ctx.createOscillator(), g = ctx.createGain(); o.type = "sine";
  if (strong) {
    o.frequency.setValueAtTime(bay * 1.5, t); o.frequency.exponentialRampToValueAtTime(bay, t + 0.07); g.gain.setValueAtTime(vol * 0.3, t); g.gain.exponentialRampToValueAtTime(0.0002, t + 0.26);
    o.connect(g); g.connect(dest); o.start(t); o.stop(t + 0.28);
  }
  const n = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), ng = ctx.createGain(); n.buffer = nz; bp.type = "bandpass"; bp.frequency.value = strong ? 700 : 1900; bp.Q.value = 1.1;
  ng.gain.setValueAtTime(vol * (strong ? 0.35 : 0.55), t); ng.gain.exponentialRampToValueAtTime(0.0002, t + 0.07); n.connect(bp); bp.connect(ng); ng.connect(dest); n.start(t, Math.random() * 0.5); n.stop(t + 0.09);
}
// Hand claps: a few people clapping a hair apart, so it sounds like a room and not a click.
function clap(ctx, dest, nz, t, vol) {
  for (let k = 0; k < 4; k++) {
    const tt = t + k * 0.006 + Math.random() * 0.004, n = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), g = ctx.createGain(); n.buffer = nz;
    bp.type = "bandpass"; bp.frequency.value = 1300 + Math.random() * 700; bp.Q.value = 0.8; g.gain.setValueAtTime(vol * 0.16, tt); g.gain.exponentialRampToValueAtTime(0.0002, tt + 0.075);
    n.connect(bp); bp.connect(g); g.connect(dest); n.start(tt, Math.random() * 0.5); n.stop(tt + 0.09);
  }
}

// Schedule the whole score on ctx. `from` seconds skips ahead (seeking). Returns the audible end time.
export function schedule(ctx, bus, score, t0, from = 0, opts = {}) {
  const nz = noiseBuf(ctx), voice = score.lead_voice, dr = score.drone, rel = (t) => t0 + t - from;
  const tp = clamp(dr.pluck, 0.9, 1.7);
  const strings = [dr.second, dr.sa, dr.sa, dr.low_sa];
  for (let k = 0, t = 0; t < score.duration + 2; k++, t += tp) {
    if (t < from - 3) continue;
    tanpura(ctx, bus, strings[k % 4], rel(t), (k % 4 === 3 ? 0.17 : 0.1), 4.2);
  }
  // Music breathes: the alap opens quietly and grows, the gat swells and settles with each phrase and over longer arcs, the tihai is strongest.
  const secs = score.sections || [], dyn = (t) => {
    const sec = secs.find((x) => t >= x.t0 && t < x.t1) || secs[secs.length - 1] || { name: "gat", t0: 0, t1: score.duration };
    const p = clamp((t - sec.t0) / Math.max(1, sec.t1 - sec.t0), 0, 1);
    if (sec.name === "alap") return 0.5 + 0.38 * p + 0.1 * Math.sin(t * 0.9);
    if (sec.name === "tihai") return 1.12;
    return 0.66 + 0.2 * Math.sin(t * 0.38 + 1) + 0.12 * Math.sin(t * 0.083) + 0.14 * Math.sin(Math.PI * p);
  };
  let prev = null;
  for (const [t, f, d, orn, vel, gl] of score.lead) {
    if (t + d < from) { prev = f; continue; }
    const st = Math.max(rel(t) + (Math.random() - 0.5) * 0.012, t0), dd = d, v = (vel || 1) * dyn(t) * (0.95 + Math.random() * 0.1);   // a player is never exact
    if (voice === "harmonium") harmonium(ctx, bus, f, st, dd, orn, prev, 0.2 * v, gl);
    else if (voice === "veena") veena(ctx, bus, f, st, dd, orn, prev, 0.34 * v, gl);
    else bansuri(ctx, bus, nz, f, st, dd, orn, prev, 0.3 * v, gl);
    prev = f;
  }
  // Extra players come from the Styles box (meta.ensemble). Songs made before that existed keep the old rule: manjira in devotional moods.
  const meta = (score.meta || {}), ens = new Set(meta.ensemble || []);
  if (!meta.ensemble && (/devot|bhakti|bhajan|krishna|calm|peace|meditat/i.test(String(meta.mood || "")) || meta.kind === "devotional")) ens.add("manjira");
  { const st = Math.max(t0, rel(0)); subBass(ctx, bus, dr.low_sa, st, t0 + score.duration - from + 2 - st, ens.has("dholak") ? 0.03 : 0.075); }
  let bi = 0;
  for (const [t, bol, cls, vol] of score.tabla) {
    if (t < from) continue;
    const d = 0.7 + 0.3 * dyn(t);
    tabla(ctx, bus, nz, score.sa, bol, cls, rel(t), vol * 0.8 * d * (ens.has("dholak") ? 0.7 : 1));
    if (ens.has("manjira") && vol >= 0.7) manjira(ctx, bus, nz, rel(t), vol * (0.6 + 0.4 * dyn(t)));
    if (ens.has("dholak")) dholak(ctx, bus, nz, score.sa, rel(t) + 0.004, vol * 0.8 * d, vol >= 0.7 || cls !== "right");
    if (ens.has("clap") && (bi % 2 === 1 || vol >= 0.95)) clap(ctx, bus, nz, rel(t) + 0.002, vol * d);
    bi++;
  }
  return t0 + score.duration - from;
}
