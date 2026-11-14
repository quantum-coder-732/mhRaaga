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
  final tanTab = _table([for (var n = 1; n < 24; n++) (1 / m.pow(n, 0.75)) * (n >= 4 && n <= 7 ? 1.7 : 1.0)]);
  final veeTab = _table([for (var n = 1; n < 24; n++) 1 / m.pow(n, 1.1)]);

  void tanpura(double f, double t, double vol, double life) {
    final n = (life * sr).floor(), s0 = (t * sr).round();
    final mul = m.pow(0.0002 / vol, 1 / ((life - 0.015) * sr)).toDouble();
    var env = vol, p1 = 0.0, p2 = 0.0, lp = 0.0, a = _lpA(5200);
    var decaying = false;
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      final tau = i / sr;
      if (i % 64 == 0) a = _lpA(5200 * m.pow(900 / 5200, tau / life).toDouble());
      if (tau < 0.015) {
        env = vol * tau / 0.015;
      } else {
        if (!decaying) {
          decaying = true;
          env = vol;
        }
        env *= mul;
      }
      final x = _read(tanTab, p1) + _read(tanTab, p2);
      lp += a * (x - lp);
      if (idx >= 0) buf[idx] += lp * env;
      p1 += f / sr;
      if (p1 >= 1) p1 -= 1;
      p2 += f * 1.0016 / sr;
      if (p2 >= 1) p2 -= 1;
    }
  }

  // vibrato + glide shared by the sustained voices
  double _freq(double f, double start, double glide, double tau, double vib) {
    var ff = (glide > 0 && tau < glide) ? start * m.pow(f / start, tau / glide) : f;
    if (vib > 0) ff += f * 0.006 * _clamp(tau / 0.4, 0, 1) * m.sin(_twoPi * 5.2 * tau);
    return ff;
  }

  void bansuri(double f, double t, double d, int orn, double? prev, double vol) {
    const a = 0.07, rel = 0.14;
    final s0 = (t * sr).round(), n = ((d + rel) * sr).floor();
    final start = orn == 1 && prev != null ? prev : (orn == 2 ? f * 1.0595 : f);
    final glide = orn == 1 ? m.min(0.16, d * 0.45) : (orn == 2 ? 0.07 : 0.0);
    final center = _clamp(f * 2.2, 500, 4500);
    final hi = _lpA(center * 1.6), lo = _lpA(center * 0.6);
    var ph = 0.0, nh = 0.0, nl = 0.0;
    final hold = vol * 0.9, relStart = m.max(a, d - 0.02);
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      if (idx < 0) continue;
      final tau = i / sr;
      final ff = _freq(f, start, glide, tau, 1);
      ph += ff / sr;
      if (ph >= 1) ph -= 1;
      var env = tau < a ? vol * tau / a : hold;
      if (tau > relStart) env = hold * m.pow(0.0002 / hold, (tau - relStart) / (rel + 0.02));
      final tri = 4 * ((2 * ph) % 1 - 0.5).abs() - 1;
      final tone = m.sin(_twoPi * ph) + 0.16 * tri + 0.06 * m.sin(_twoPi * 3 * ph);
      final z = rng.next();
      nh += hi * (z - nh);
      nl += lo * (z - nl);
      final breath = (nh - nl) * 2.6 * (0.05 + 0.15 * m.exp(-tau / 0.08));
      buf[idx] += env * (tone + breath);
    }
  }

  void harmonium(double f, double t, double d, int orn, double? prev, double vol) {
    const rel = 0.1;
    final s0 = (t * sr).round(), n = ((d + rel) * sr).floor();
    final start = orn == 1 && prev != null ? prev : f, glide = orn == 1 ? m.min(0.12, d * 0.4) : 0.0;
    final up = m.pow(2, 5 / 1200).toDouble(), dn = 1 / up, a = _lpA(2300);
    var p1 = 0.0, p2 = 0.0, p3 = 0.0, l1 = 0.0, l2 = 0.0;
    final top = vol * 0.8, relStart = m.max(0.05, d - 0.02);
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      if (idx < 0) continue;
      final tau = i / sr, ff = _freq(f, start, glide, tau, 0);
      p1 = (p1 + ff * up / sr) % 1;
      p2 = (p2 + ff * dn / sr) % 1;
      p3 = (p3 + 2 * ff / sr) % 1;
      var env = tau < 0.05 ? top * tau / 0.05 : top;
      if (tau > relStart) env = top * m.pow(0.0002 / top, (tau - relStart) / (rel + 0.02));
      final x = 0.5 * (2 * p1 - 1) + 0.5 * (2 * p2 - 1) + 0.12 * (p3 < 0.5 ? 1 : -1);
      l1 += a * (x - l1);
      l2 += a * (l1 - l2);
      buf[idx] += env * l2 * 0.8;
    }
  }

  void veena(double f, double t, double d, int orn, double? prev, double vol) {
    final life = _clamp(d * 1.5, 0.7, 2.6), n = (life * sr).floor(), s0 = (t * sr).round();
    final start = orn == 1 && prev != null ? prev : f, glide = start != f ? m.min(0.1, d * 0.4) : 0.0;
    final mul = m.pow(0.0002 / vol, 1 / ((life - 0.008) * sr)).toDouble();
    var ph = 0.0, lp = 0.0, a = _lpA(4200), env = vol;
    var decaying = false;
    for (var i = 0; i < n; i++) {
      final idx = s0 + i;
      if (idx >= buf.length) break;
      if (idx < 0) continue;
      final tau = i / sr;
      if (i % 64 == 0) a = _lpA(4200 * m.pow(700 / 4200, tau / life).toDouble());
      if (tau < 0.008) {
        env = vol * tau / 0.008;
      } else {
        if (!decaying) {
          decaying = true;
          env = vol;
        }
        env *= mul;
      }
      ph = (ph + _freq(f, start, glide, tau, 0) / sr) % 1;
      lp += a * (_read(veeTab, ph) - lp);
      buf[idx] += lp * env;
    }
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
    if (cls == 'left' || cls == 'both') {
      final muted = low == 'ka' || low == 'kat';
      _tone(t, bay * (muted ? 1.1 : 1.6), bay, muted ? 0.09 : 0.32, 0.9 * vol);
      _click(t, 250, 0.03, 0.12 * vol);
    }
    if (cls == 'right' || cls == 'both') {
      final rim = const ['na', 'ti', 'ra', 'ki', 'tu'].contains(low), len = rim ? 0.16 : 0.55;
      _tone(t, day * 1.04, day, len, 0.55 * vol);
      _tone(t, day * 2.01, day * 2, len * 0.6, 0.18 * vol);
      _click(t, rim ? 4200 : 2800, 0.025, 0.22 * vol);
    }
  }
}

/// Reverb: a small Schroeder network mixed under the dry signal.
Float64List _reverb(Float64List x) {
  final out = Float64List(x.length), wet = Float64List(x.length);
  for (final (d, g) in [(1687, 0.88), (2053, 0.87), (2377, 0.86), (2833, 0.85)]) {
    final b = Float64List(d);
    var p = 0;
    for (var i = 0; i < x.length; i++) {
      final y = b[p];
      b[p] = x[i] + y * g;
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
    out[i] = x[i] * 0.78 + wet[i] * 0.55;
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
  double? prev;
  for (final n in score['lead'] as List) {
    final t = _num(n[0]), f = _num(n[1]), d = _num(n[2]), orn = (n[3] as num).toInt();
    if (voice == 'harmonium') {
      sy.harmonium(f, t, d, orn, prev, 0.2);
    } else if (voice == 'veena') {
      sy.veena(f, t, d, orn, prev, 0.34);
    } else {
      sy.bansuri(f, t, d, orn, prev, 0.3);
    }
    prev = f;
  }
  for (final b in score['tabla'] as List) {
    sy.tabla(b[1] as String, b[2] as String, _num(b[0]), _num(b[3]) * 0.8);
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
