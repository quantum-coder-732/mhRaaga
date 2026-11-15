// Sound engine: renders a mhRaaga score (from the API) to a 16-bit mono WAV.
// A Dart port of the web synth: tanpura (jawari shimmer), bansuri / harmonium / veena lead, tabla, reverb.
import 'dart:math' as m;
import 'dart:typed_data';

const int sr = 22050;
const double _twoPi = 2 * m.pi;

double _num(dynamic v) => (v as num).toDouble();
double _clamp(double x, double a, double b) => x < a ? a : (x > b ? b : x);

class _Rng {
  int s = 987654321;
  double next() {
    s = (s * 1664525 + 1013904223) & 0xFFFFFFFF;
    return s / 2147483648.0 - 1.0;
  }
}

Float64List _table(List<double> amps, {int n = 2048}) {
  final t = Float64List(n);
  for (var k = 1; k <= amps.length; k++) {
    final a = amps[k - 1];
    for (var i = 0; i < n; i++) {
      t[i] += a * m.sin(_twoPi * k * i / n);
    }
  }
  var peak = 0.0;
  for (final v in t) {
    if (v.abs() > peak) peak = v.abs();
  }
  for (var i = 0; i < n; i++) {
    t[i] /= peak == 0 ? 1 : peak;
  }
  return t;
}

double _read(Float64List t, double ph) {
  final n = t.length;
  final x = ph * n;
  final i = x.floor();
  final f = x - i;
  return t[i % n] * (1 - f) + t[(i + 1) % n] * f;
}

class _BP {
  _BP(double f, double q) {
    final w = _twoPi * f / sr, alpha = m.sin(w) / (2 * q), a0 = 1 + alpha;
    b0 = alpha / a0;
    b2 = -alpha / a0;
    a1 = -2 * m.cos(w) / a0;
    a2 = (1 - alpha) / a0;
  }
  late double b0, b2, a1, a2;
  double x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  double p(double x) {
    final y = b0 * x + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1;
    x1 = x;
    y2 = y1;
    y1 = y;
    return y;
  }
}

double _lpA(double fc) => 1 - m.exp(-_twoPi * fc / sr);

class _Synth {
  _Synth(this.sa, int len) : buf = Float64List(len);
  final double sa;
  final Float64List buf;
  final _Rng rng = _Rng();
  final banTab = _table(const [1, 0.32, 0.1, 0.045, 0.02]);
  final harmTab = _table([for (var n = 1; n <= 22; n++) 1 / m.pow(n, 0.95) * (n.isOdd ? 1.0 : 0.8)]);

  // Karplus-Strong plucked string (a delay loop with loss), rendered once per pitch. Gives the tanpura and veena a real
  // string attack, highs that die first and, with `buzz`, the jawari bridge. Cached by pitch.
  final Map<String, Float64List> _pl = {};
  Float64List _pluck(double f, double secs, double rho, double bright, double buzz, int seed) {
    final key = '${(f * 8).round()}|$secs|$rho|$bright|$buzz';
    final hit = _pl[key];
    if (hit != null) return hit;
    final len = (secs * sr).floor(), want = sr / f - 0.5, n = m.max(2, want.floor()), frac = want - n;
    final ap = (1 - frac) / (1 + frac), line = Float64List(n + 1), out = Float64List(len);
    final r = _Rng()..s = seed.abs() + 12345;
    var lp = 0.0;
    for (var i = 0; i <= n; i++) {
      lp += (r.next() - lp) * bright;
      line[i] = lp * (0.5 - 0.5 * m.cos(m.pi * m.min(1.0, i / (n * 0.25))));
    }
    var idx = 0, prev = 0.0, apx = 0.0, apy = 0.0, peak = 1e-9;
    for (var i = 0; i < len; i++) {
      final a0 = line[idx], b0 = line[(idx + 1) % (n + 1)];
      var y = rho * (0.5 * a0 + 0.5 * b0);
      final ay = ap * (y - apy) + apx;
      apx = y;
      apy = ay;
      y = ay;
      line[idx] = y;
      idx = (idx + 1) % (n + 1);
      final o = buzz > 0 ? (m.exp(2 * buzz * y) - 1) / (m.exp(2 * buzz * y) + 1) : y;
      out[i] = o - prev * 0.995;
      prev = o;
      if (out[i].abs() > peak) peak = out[i].abs();
    }
    final fade = (sr * 0.05).floor();
    for (var i = 0; i < len; i++) {
      out[i] /= peak;
      if (i >= len - fade) out[i] *= (len - 1 - i) / fade;
    }
    return _pl[key] = out;
  }

  void _play(Float64List w, double t, double gain, double life, {double rate = 1.0, double from = 1.0, double slide = 0.0}) {
    final s0 = (t * sr).round(), n = m.min((life * sr).floor(), (w.length / rate).floor());
    var pos = 0.0;
    final mul = m.pow(0.0002 / gain, 1 / (life * sr)).toDouble();
    var env = gain;
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      final tau = i / sr;
      final r = (slide > 0 && tau < slide) ? from * m.pow(1 / from, tau / slide) : 1.0;
      pos += rate * r;
      final k = pos.floor();
      if (k + 1 >= w.length) break;
      final fr = pos - k;
      if (idx >= 0) buf[idx] += (w[k] * (1 - fr) + w[k + 1] * fr) * env;
      env *= mul;
    }
  }

  void tanpura(double f, double t, double vol, double life) {
    _play(_pluck(f, 5, 0.9992, 0.5, 2.6, (f * 3).round()), t, vol * 7, life + 0.8, rate: 1 + rng.next() * 0.0003);
  }

  // vibrato + glide shared by the sustained voices
  double _freq(double f, double start, double glide, double tau, double vib) {
    var ff = (glide > 0 && tau < glide) ? start * m.pow(f / start, tau / glide) : f;
    if (vib > 0) ff += f * 0.006 * _clamp(tau / 0.4, 0, 1) * m.sin(_twoPi * 5.2 * tau);
    return ff;
  }

  void bansuri(double f, double t, double d, int orn, double? prev, double vol) {
    final att = 0.09 + 0.015 * (rng.next() + 1), rel = 0.18;
    final s0 = (t * sr).round(), n = ((d + rel) * sr).floor();
    final start = orn == 1 && prev != null ? prev : (orn == 2 ? f * 1.0595 : f * 0.985);
    final glide = orn == 1 ? m.min(0.16, d * 0.45) : (orn == 2 ? 0.07 : 0.05);
    final center = _clamp(f * 2.4, 700, 4200);
    final hi = _lpA(center * 1.5), lo = _lpA(center * 0.65), tone = _lpA(_clamp(f * 5.5, 1800, 6000));
    var ph = 0.0, nh = 0.0, nl = 0.0, lt = 0.0;
    final vr = 4.7 + 0.45 * (rng.next() + 1), dr = 0.4 + 0.25 * (rng.next() + 1);
    final hold = vol * 0.9, relStart = m.max(att + 0.12, d - 0.02);
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      if (idx < 0) continue;
      final tau = i / sr;
      var ff = (tau < glide) ? start * m.pow(f / start, tau / glide) : f;
      ff += f * 0.0065 * _clamp((tau - 0.22) / 0.48, 0, 1) * m.sin(_twoPi * vr * tau) + f * 0.0016 * m.sin(_twoPi * dr * tau);
      ph += ff / sr;
      if (ph >= 1) ph -= 1;
      var env = tau < att ? vol * 1.12 * tau / att : (tau < att + 0.12 ? vol * 1.12 - (vol * 0.22) * (tau - att) / 0.12 : hold);
      if (tau > relStart) env = hold * m.pow(0.0002 / hold, (tau - relStart) / (rel + 0.02));
      lt += tone * (_read(banTab, ph) - lt);
      final z = rng.next();
      nh += hi * (z - nh);
      nl += lo * (z - nl);
      final breath = (nh - nl) * 3.0 * (0.11 + 0.35 * m.exp(-tau / 0.06));
      buf[idx] += env * (lt * (1 + 0.05 * m.sin(_twoPi * vr * tau)) + breath * vol * 0.8);
    }
  }

  void harmonium(double f, double t, double d, int orn, double? prev, double vol) {
    const rel = 0.14;
    final s0 = (t * sr).round(), n = ((d + rel) * sr).floor();
    final start = orn == 1 && prev != null ? prev : f, glide = orn == 1 ? m.min(0.12, d * 0.4) : 0.0;
    final up = m.pow(2, 6 / 1200).toDouble(), dn = m.pow(2, -7 / 1200).toDouble(), a = _lpA(2600);
    var p1 = 0.0, p2 = 0.0, p3 = 0.0, l1 = 0.0, l2 = 0.0;
    final top = vol * 0.8, att = 0.07 + 0.015 * (rng.next() + 1), relStart = m.max(att, d - 0.02), bp = 0.35 + 0.1 * (rng.next() + 1);
    final w700 = _BP(700, 1.1), w2100 = _BP(2100, 1.4);
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      if (idx < 0) continue;
      final tau = i / sr, ff = _freq(f, start, glide, tau, 0);
      p1 = (p1 + ff * up / sr) % 1;
      p2 = (p2 + ff * dn / sr) % 1;
      p3 = (p3 + 0.5 * ff / sr) % 1;
      var env = tau < att ? top * tau / att : top * (1 + 0.04 * m.sin(_twoPi * bp * tau));
      if (tau > relStart) env = top * m.pow(0.0002 / top, (tau - relStart) / (rel + 0.02));
      final x = 0.42 * _read(harmTab, p1) + 0.42 * _read(harmTab, p2) + 0.2 * _read(harmTab, p3);
      l1 += a * (x - l1);
      l2 += a * (l1 - l2);
      final body = l2 + 1.6 * w700.p(l2) + 1.2 * w2100.p(l2);   // wooden body resonances
      buf[idx] += env * body * 0.8;
    }
  }

  void veena(double f, double t, double d, int orn, double? prev, double vol) {
    final life = _clamp(d * 1.6, 0.8, 3.2), from = orn == 1 && prev != null ? prev / f : 1.0;
    _play(_pluck(f, 3.4, 0.9987, 0.62, 1.6, (f * 7).round()), t, vol * 1.5, life, from: from, slide: from != 1.0 ? m.min(0.12, d * 0.4) : 0.0);
  }

  void _tone(double t, double f0, double f1, double dur, double v) {
    final s0 = (t * sr).round(), n = (dur * sr).floor();
    var ph = 0.0;
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      final tau = i / sr, k = _clamp(tau / (dur * 0.4), 0, 1);
      ph += f0 * m.pow(f1 / f0, k) / sr;
      if (idx >= 0) buf[idx] += m.sin(_twoPi * ph) * v * m.pow(0.0002 / v, tau / dur);
    }
  }

  void _click(double t, double freq, double dur, double v) {
    final bp = _BP(freq, 1.4), s0 = (t * sr).round(), n = (dur * sr).floor();
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      final y = bp.p(rng.next());
      if (idx >= 0) buf[idx] += y * v * m.pow(0.0002 / v, i / sr / dur) * 2;
    }
  }

  void tabla(String bol, String cls, double t, double vol) {
    final day = _clamp(sa, 150, 300), bay = _clamp(sa / 2, 70, 140), low = bol.toLowerCase();
    t += (rng.next() + 1) * 0.004;
    vol *= 0.9 + 0.1 * (rng.next() + 1);   // no two strokes are the same
    if (cls == 'left' || cls == 'both') {
      final muted = low == 'ka' || low == 'kat' || low == 'ke';
      if (muted) {
        _click(t, 900, 0.05, 0.15 * vol);
        _tone(t, bay * 1.2, bay, 0.07, 0.35 * vol);
      } else {
        _tone(t, bay * 1.7, bay * 0.92, 0.5, 0.9 * vol);
        _tone(t, bay * 2.6, bay * 1.9, 0.18, 0.18 * vol);
        _click(t, 320, 0.05, 0.11 * vol);
      }
    }
    if (cls == 'right' || cls == 'both') {
      final rim = const ['na', 'ti', 'ra', 'ki', 'tu', 'te'].contains(low), len = rim ? 0.2 : 0.7;
      final parts = rim ? const [[1.0, 0.5], [2.0, 0.34], [3.0, 0.2], [4.0, 0.1]] : const [[1.0, 0.52], [2.0, 0.3], [3.0, 0.2], [4.0, 0.1], [5.0, 0.06]];
      for (var i = 0; i < parts.length; i++) {
        _tone(t, day * parts[i][0] * 1.02, day * parts[i][0], len / (1 + i * 0.7), parts[i][1] * 0.8 * vol);
      }
      _click(t, rim ? 3800 : 2400, 0.03, 0.14 * vol);
      _click(t, 1500, 0.018, 0.08 * vol);
    }
  }
}

/// Reverb: a small Schroeder network mixed under the dry signal.
Float64List _reverb(Float64List x) {
  final out = Float64List(x.length), wet = Float64List(x.length);
  for (final (d, g) in [(1687, 0.88), (2053, 0.87), (2377, 0.86), (2833, 0.85)]) {
    final b = Float64List(d);
    var p = 0;
    var damp = 0.0;
    for (var i = 0; i < x.length; i++) {
      final y = b[p];
      damp += 0.45 * (y - damp);   // air absorbs the highs in the tail
      b[p] = x[i] + damp * g;
      p = (p + 1) % d;
      wet[i] += y * 0.25;
    }
  }
  for (final d in [110, 37]) {
    final b = Float64List(d);
    var p = 0;
    for (var i = 0; i < wet.length; i++) {
      final z = b[p], v = wet[i] + 0.7 * z;
      b[p] = v;
      wet[i] = z - 0.7 * v;
      p = (p + 1) % d;
    }
  }
  for (var i = 0; i < x.length; i++) {
    final v = x[i] * 0.74 + wet[i] * 0.6;
    out[i] = (m.exp(3 * v) - 1) / (m.exp(3 * v) + 1) / 1.5;   // soft tape-style saturation
  }
  return out;
}

Uint8List _wav(Float64List x) {
  var peak = 0.0;
  for (final v in x) {
    if (v.abs() > peak) peak = v.abs();
  }
  final g = peak == 0 ? 1.0 : 0.88 / peak;
  final data = ByteData(44 + x.length * 2);
  void s(int o, String t) {
    for (var i = 0; i < t.length; i++) {
      data.setUint8(o + i, t.codeUnitAt(i));
    }
  }
  s(0, 'RIFF');
  data.setUint32(4, 36 + x.length * 2, Endian.little);
  s(8, 'WAVEfmt ');
  data.setUint32(16, 16, Endian.little);
  data.setUint16(20, 1, Endian.little);
  data.setUint16(22, 1, Endian.little);
  data.setUint32(24, sr, Endian.little);
  data.setUint32(28, sr * 2, Endian.little);
  data.setUint16(32, 2, Endian.little);
  data.setUint16(34, 16, Endian.little);
  s(36, 'data');
  data.setUint32(40, x.length * 2, Endian.little);
  for (var i = 0; i < x.length; i++) {
    data.setInt16(44 + i * 2, (_clamp(x[i] * g, -1, 1) * 32767).round(), Endian.little);
  }
  return data.buffer.asUint8List();
}

/// Entry point for `compute`: score map in, WAV bytes out.
Uint8List renderScore(Map<String, dynamic> score) {
  final duration = _num(score['duration']);
  final sy = _Synth(_num(score['sa']), ((duration + 4) * sr).floor());
  final dr = score['drone'] as Map, tp = _clamp(_num(dr['pluck']), 0.9, 1.7);
  final strings = [_num(dr['second']), _num(dr['sa']), _num(dr['sa']), _num(dr['low_sa'])];
  var k = 0;
  for (var t = 0.0; t < duration + 2; k++, t += tp) {
    sy.tanpura(strings[k % 4], t, k % 4 == 3 ? 0.13 : 0.1, 4.2);
  }
  final voice = score['lead_voice'] as String;
  final secs = (score['sections'] as List?) ?? const [];
  double dyn(double t) {   // the music breathes: quiet alap that grows, a gat that swells and settles, a strong tihai
    Map? sec;
    for (final x in secs) {
      if (t >= _num(x['t0']) && t < _num(x['t1'])) sec = x as Map;
    }
    final name = sec?['name'], t0 = sec == null ? 0.0 : _num(sec['t0']), t1 = sec == null ? duration : _num(sec['t1']);
    final p = _clamp((t - t0) / m.max(1, t1 - t0), 0, 1);
    if (name == 'alap') return 0.5 + 0.38 * p + 0.1 * m.sin(t * 0.9);
    if (name == 'tihai') return 1.12;
    return 0.66 + 0.2 * m.sin(t * 0.38 + 1) + 0.12 * m.sin(t * 0.083) + 0.14 * m.sin(m.pi * p);
  }
  double? prev;
  for (final n in score['lead'] as List) {
    final t = _num(n[0]) + sy.rng.next() * 0.006, f = _num(n[1]), d = _num(n[2]), orn = (n[3] as num).toInt(), vel = (n.length > 4 ? _num(n[4]) : 1.0) * dyn(_num(n[0])) * (0.95 + 0.05 * (sy.rng.next() + 1));
    if (voice == 'harmonium') {
      sy.harmonium(f, t, d, orn, prev, 0.2 * vel);
    } else if (voice == 'veena') {
      sy.veena(f, t, d, orn, prev, 0.34 * vel);
    } else {
      sy.bansuri(f, t, d, orn, prev, 0.3 * vel);
    }
    prev = f;
  }
  for (final b in score['tabla'] as List) {
    sy.tabla(b[1] as String, b[2] as String, _num(b[0]), _num(b[3]) * 0.8 * (0.7 + 0.3 * dyn(_num(b[0]))));
  }
  return _wav(_reverb(sy.buf));
}

/// A short ascent-then-descent of a raga over the drone, for the Ragas browser.
Uint8List renderPreview(Map<String, dynamic> a) {
  final sa = _num(a['sa']);
  const ratio = [1, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2, 8 / 5, 5 / 3, 9 / 5, 15 / 8];
  double hz(int n) => sa * ratio[((n % 12) + 12) % 12] * m.pow(2, (n / 12).floor());
  final seq = [...(a['aroha'] as List), ...(a['avaroha'] as List).skip(1)].map((e) => (e as num).toInt()).toList();
  final lead = <List<dynamic>>[];
  for (var i = 0; i < seq.length; i++) {
    lead.add([0.8 + i * 0.62, hz(seq[i]), 0.6, i == 0 ? 0 : 1]);
  }
  final total = 0.8 + seq.length * 0.62 + 1.5;
  return renderScore({
    'sa': sa, 'duration': total, 'lead_voice': 'bansuri',
    'drone': {'sa': sa, 'second': sa * 1.5, 'low_sa': sa / 2, 'pluck': 1.5},
    'lead': lead, 'tabla': [],
  });
}
