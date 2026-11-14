// mhRaaga synth: renders a score (from the API) with Web Audio. Same code drives live playback and offline WAV export.

export function reverbIR(ctx, seconds = 2.6) {
  const n = Math.floor(ctx.sampleRate * seconds), b = ctx.createBuffer(2, n, ctx.sampleRate);
  for (let c = 0; c < 2; c++) { const d = b.getChannelData(c); for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 2.6); }
  return b;
}
function noiseBuf(ctx) {
  const b = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return b;
}
function wave(ctx, kind) {
  const N = 24, re = new Float32Array(N), im = new Float32Array(N);
  for (let n = 1; n < N; n++) {
    if (kind === "tanpura") im[n] = (1 / Math.pow(n, 0.75)) * (n >= 4 && n <= 7 ? 1.7 : 1); // jawari: bright 4th-7th partials
    else if (kind === "veena") im[n] = 1 / Math.pow(n, 1.1);
    else im[n] = 1 / n; // sawtooth-like
  }
  return ctx.createPeriodicWave(re, im);
}
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

export function master(ctx, volume = 0.8) {
  const out = ctx.createGain(); out.gain.value = volume;
  const comp = ctx.createDynamicsCompressor(); comp.threshold.value = -16; comp.ratio.value = 3;
  const dry = ctx.createGain(), wet = ctx.createGain(), conv = ctx.createConvolver();
  dry.gain.value = 0.78; wet.gain.value = 0.3; conv.buffer = reverbIR(ctx);
  const bus = ctx.createGain();
  bus.connect(dry); bus.connect(conv); conv.connect(wet); dry.connect(comp); wet.connect(comp); comp.connect(out); out.connect(ctx.destination);
  return { bus, out };
}

function tanpura(ctx, dest, f, t, vol, life) {
  const o = ctx.createOscillator(), o2 = ctx.createOscillator(), g = ctx.createGain(), lp = ctx.createBiquadFilter();
  o.setPeriodicWave(wave(ctx, "tanpura")); o2.setPeriodicWave(wave(ctx, "tanpura"));
  o.frequency.value = f; o2.frequency.value = f * 1.0016; // slight beating = the shimmer
  lp.type = "lowpass"; lp.frequency.setValueAtTime(5200, t); lp.frequency.exponentialRampToValueAtTime(900, t + life);
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.015); g.gain.exponentialRampToValueAtTime(0.0002, t + life);
  o.connect(lp); o2.connect(lp); lp.connect(g); g.connect(dest);
  o.start(t); o2.start(t); o.stop(t + life + 0.1); o2.stop(t + life + 0.1);
}

function bansuri(ctx, dest, nz, f, t, d, orn, prev, vol, gl) {
  const a = 0.07, rel = 0.14, end = t + d;
  const o1 = ctx.createOscillator(), o2 = ctx.createOscillator(), o3 = ctx.createOscillator(), g = ctx.createGain();
  o1.type = "sine"; o2.type = "triangle"; o3.type = "sine";
  const g2 = ctx.createGain(), g3 = ctx.createGain(); g2.gain.value = 0.16; g3.gain.value = 0.06;
  const start = orn === 1 && prev ? prev : orn === 2 ? f * 1.0595 : f;
  const glide = orn === 1 ? (gl || Math.min(0.16, d * 0.45)) : orn === 2 ? 0.07 : 0;
  for (const [o, m] of [[o1, 1], [o2, 2], [o3, 3]]) {
    if (glide) { o.frequency.setValueAtTime(start * m, t); o.frequency.exponentialRampToValueAtTime(f * m, t + glide); } else o.frequency.setValueAtTime(f * m, t);
  }
  const lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = 5.2; lg.gain.setValueAtTime(0, t); lg.gain.linearRampToValueAtTime(f * 0.006, t + 0.4);
  lfo.connect(lg); lg.connect(o1.frequency); lfo.start(t); lfo.stop(end + rel);
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol, t + a); g.gain.setValueAtTime(vol * 0.9, Math.max(t + a, end - 0.02)); g.gain.exponentialRampToValueAtTime(0.0002, end + rel);
  o1.connect(g); o2.connect(g2); g2.connect(g); o3.connect(g3); g3.connect(g);
  // breath
  const n = ctx.createBufferSource(); n.buffer = nz; n.loop = true;
  const bp = ctx.createBiquadFilter(), ng = ctx.createGain(); bp.type = "bandpass"; bp.frequency.value = clamp(f * 2.2, 500, 4500); bp.Q.value = 1.2;
  ng.gain.setValueAtTime(0.0001, t); ng.gain.linearRampToValueAtTime(vol * 0.2, t + 0.03); ng.gain.exponentialRampToValueAtTime(vol * 0.05, t + 0.25); ng.gain.exponentialRampToValueAtTime(0.0002, end + rel);
  n.connect(bp); bp.connect(ng); ng.connect(g);
  g.connect(dest);
  for (const o of [o1, o2, o3]) { o.start(t); o.stop(end + rel + 0.05); }
  n.start(t); n.stop(end + rel + 0.05);
}

function harmonium(ctx, dest, f, t, d, orn, prev, vol, gl) {
  const end = t + d, rel = 0.1;
  const g = ctx.createGain(), lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 2300; lp.Q.value = 0.9;
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(vol * 0.8, t + 0.05); g.gain.setValueAtTime(vol * 0.8, Math.max(t + 0.05, end - 0.02)); g.gain.exponentialRampToValueAtTime(0.0002, end + rel);
  const start = orn === 1 && prev ? prev : f, glide = orn === 1 ? (gl || Math.min(0.12, d * 0.4)) : 0;
  for (const [type, m, det] of [["sawtooth", 1, 5], ["sawtooth", 1, -5], ["square", 2, 0]]) {
    const o = ctx.createOscillator(), og = ctx.createGain(); o.type = type; o.detune.value = det; og.gain.value = m === 2 ? 0.12 : 0.5;
    if (glide) { o.frequency.setValueAtTime(start * m, t); o.frequency.exponentialRampToValueAtTime(f * m, t + glide); } else o.frequency.value = f * m;
    o.connect(og); og.connect(lp); o.start(t); o.stop(end + rel + 0.05);
  }
  lp.connect(g); g.connect(dest);
}

function veena(ctx, dest, f, t, d, orn, prev, vol, gl) {
  const life = clamp(d * 1.5, 0.7, 2.6), o = ctx.createOscillator(), g = ctx.createGain(), lp = ctx.createBiquadFilter();
  o.setPeriodicWave(wave(ctx, "veena"));
  const start = orn === 1 && prev ? prev : f;
  if (start !== f) { o.frequency.setValueAtTime(start, t); o.frequency.exponentialRampToValueAtTime(f, t + (gl || Math.min(0.1, d * 0.4))); } else o.frequency.value = f;
  lp.type = "lowpass"; lp.frequency.setValueAtTime(4200, t); lp.frequency.exponentialRampToValueAtTime(700, t + life);
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.008); g.gain.exponentialRampToValueAtTime(0.0002, t + life);
  o.connect(lp); lp.connect(g); g.connect(dest); o.start(t); o.stop(t + life + 0.05);
}

function tabla(ctx, dest, nz, sa, bol, cls, t, vol) {
  const day = clamp(sa, 150, 300), bay = clamp(sa / 2, 70, 140), low = bol.toLowerCase();
  const tone = (f0, f1, dur, v, type = "sine") => {
    const o = ctx.createOscillator(), g = ctx.createGain(); o.type = type;
    o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + dur * 0.4);
    g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.0002, t + dur); o.connect(g); g.connect(dest); o.start(t); o.stop(t + dur + 0.02);
  };
  const click = (freq, dur, v) => {
    const n = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), g = ctx.createGain(); n.buffer = nz;
    bp.type = "bandpass"; bp.frequency.value = freq; bp.Q.value = 1.4; g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.0002, t + dur);
    n.connect(bp); bp.connect(g); g.connect(dest); n.start(t, Math.random() * 0.5); n.stop(t + dur + 0.01);
  };
  if (cls === "left" || cls === "both") { // bayan: pitch rises as the heel presses
    const muted = low === "ka" || low === "kat";
    tone(bay * (muted ? 1.1 : 1.6), bay, muted ? 0.09 : 0.32, 0.9 * vol); click(250, 0.03, 0.12 * vol);
  }
  if (cls === "right" || cls === "both") { // dayan: tuned to Sa; 'na/ti' rim strokes are short, 'tin/ta/dha' ring
    const rim = ["na", "ti", "ra", "ki", "tu"].includes(low), len = rim ? 0.16 : 0.55;
    tone(day * 1.04, day, len, 0.55 * vol); tone(day * 2.01, day * 2, len * 0.6, 0.18 * vol); click(rim ? 4200 : 2800, 0.025, 0.22 * vol);
  }
}

// Schedule the whole score on ctx. `from` seconds skips ahead (seeking). Returns the audible end time.
export function schedule(ctx, bus, score, t0, from = 0, opts = {}) {
  const nz = noiseBuf(ctx), voice = score.lead_voice, dr = score.drone, rel = (t) => t0 + t - from;
  const tp = clamp(dr.pluck, 0.9, 1.7);
  const strings = [dr.second, dr.sa, dr.sa, dr.low_sa];
  for (let k = 0, t = 0; t < score.duration + 2; k++, t += tp) {
    if (t < from - 3) continue;
    tanpura(ctx, bus, strings[k % 4], rel(t), (k % 4 === 3 ? 0.13 : 0.1), 4.2);
  }
  let prev = null;
  for (const [t, f, d, orn, vel, gl] of score.lead) {
    if (t + d < from) { prev = f; continue; }
    const st = Math.max(rel(t), t0), dd = d;
    if (voice === "harmonium") harmonium(ctx, bus, f, st, dd, orn, prev, 0.2 * (vel || 1), gl);
    else if (voice === "veena") veena(ctx, bus, f, st, dd, orn, prev, 0.34 * (vel || 1), gl);
    else bansuri(ctx, bus, nz, f, st, dd, orn, prev, 0.3 * (vel || 1), gl);
    prev = f;
  }
  for (const [t, bol, cls, vol] of score.tabla) if (t >= from) tabla(ctx, bus, nz, score.sa, bol, cls, rel(t), vol * 0.8);
  return t0 + score.duration - from;
}
