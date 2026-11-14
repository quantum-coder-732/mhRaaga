import 'dart:math' as m;
import 'package:flutter/material.dart';

const kBg = Color(0xFF120F2E), kBg2 = Color(0xFF1B1646), kCard = Color(0xFF211B57), kLine = Color(0xFF3A3280);
const kGold = Color(0xFFF4B942), kPeacock = Color(0xFF2EC4B6), kRose = Color(0xFFFF6B8A), kMute = Color(0xFFB3A9D6), kInk = Color(0xFFF6EFE0);
const kSvara = ['Sa', 'Re♭', 'Re', 'Ga♭', 'Ga', 'Ma', 'Ma♯', 'Pa', 'Dha♭', 'Dha', 'Ni♭', 'Ni'];

ThemeData buildTheme() {
  final base = ThemeData(brightness: Brightness.dark, useMaterial3: true, colorSchemeSeed: kGold);
  return base.copyWith(
    scaffoldBackgroundColor: Colors.transparent,
    colorScheme: base.colorScheme.copyWith(primary: kGold, onPrimary: const Color(0xFF1A1033), surface: kBg2, secondary: kPeacock),
    textTheme: base.textTheme.apply(bodyColor: kInk, displayColor: kInk, fontFamilyFallback: const ['Noto Sans Devanagari', 'Roboto']),
    appBarTheme: const AppBarTheme(backgroundColor: Colors.transparent, elevation: 0, centerTitle: false, scrolledUnderElevation: 0),
    inputDecorationTheme: InputDecorationTheme(
      filled: true, fillColor: kBg, contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: kLine)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: kLine)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: kGold, width: 1.6)),
      labelStyle: const TextStyle(color: kMute),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: const Color(0xEE15113A), indicatorColor: kGold.withValues(alpha: .22),
      labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(fontSize: 12, color: s.contains(WidgetState.selected) ? kGold : kMute)),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(color: s.contains(WidgetState.selected) ? kGold : kMute)),
    ),
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
      backgroundColor: kGold, foregroundColor: const Color(0xFF1A1033), minimumSize: const Size(0, 50),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)), textStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16))),
    chipTheme: ChipThemeData(backgroundColor: kBg2, side: const BorderSide(color: kLine), labelStyle: const TextStyle(color: kMute, fontSize: 12)),
  );
}

/// Indigo night-sky background used behind every screen.
class Night extends StatelessWidget {
  const Night({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
        decoration: const BoxDecoration(
          gradient: RadialGradient(center: Alignment(.8, -1.1), radius: 1.5, colors: [Color(0xFF33267D), kBg], stops: [0, .6]),
        ),
        child: child,
      );
}

class Glass extends StatelessWidget {
  const Glass({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.onTap, this.glow = false});
  final Widget child;
  final EdgeInsets padding;
  final VoidCallback? onTap;
  final bool glow;
  @override
  Widget build(BuildContext context) => Material(
        color: Colors.transparent,
        child: Ink(
          decoration: BoxDecoration(
            gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [kCard, Color(0xFF1A1550)]),
            border: Border.all(color: glow ? kGold.withValues(alpha: .7) : kLine),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: .35), blurRadius: 18, offset: const Offset(0, 8))],
          ),
          child: InkWell(borderRadius: BorderRadius.circular(20), onTap: onTap, child: Padding(padding: padding, child: child)),
        ),
      );
}

class OmBadge extends StatelessWidget {
  const OmBadge({super.key, this.size = 48, this.text = 'ॐ'});
  final double size;
  final String text;
  @override
  Widget build(BuildContext context) => Container(
        width: size, height: size, alignment: Alignment.center,
        decoration: BoxDecoration(shape: BoxShape.circle, color: kBg2, border: Border.all(color: kLine),
            gradient: const RadialGradient(colors: [Color(0xFF3B2D95), kBg2])),
        child: Text(text, style: TextStyle(fontSize: size * .5, color: kGold, fontWeight: FontWeight.w700)),
      );
}

class Chipx extends StatelessWidget {
  const Chipx(this.text, {super.key, this.gold = false});
  final String text;
  final bool gold;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(color: kBg2, borderRadius: BorderRadius.circular(99), border: Border.all(color: gold ? const Color(0xFF7A5A22) : kLine)),
        child: Text(text, style: TextStyle(fontSize: 12, color: gold ? kGold : kMute)),
      );
}

void snack(BuildContext c, String msg) =>
    ScaffoldMessenger.of(c)..hideCurrentSnackBar()..showSnackBar(SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating, backgroundColor: kBg2));

String fmt(num s) => '${s ~/ 60}:${(s % 60).floor().toString().padLeft(2, '0')}';

/// The twelve svaras with the notes a raga uses lit up. Red = vadi, gold = samvadi.
class Ladder extends StatelessWidget {
  const Ladder({super.key, required this.used, required this.vadi, required this.samvadi});
  final Set<int> used;
  final int vadi, samvadi;
  @override
  Widget build(BuildContext context) => Wrap(spacing: 6, runSpacing: 6, children: [
        for (var i = 0; i < 12; i++)
          Container(
            width: 52, padding: const EdgeInsets.symmetric(vertical: 12), alignment: Alignment.center,
            decoration: BoxDecoration(
              color: i == vadi ? kRose : i == samvadi ? kGold : used.contains(i) ? const Color(0xFF2A2270) : kBg,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: i == vadi ? kRose : i == samvadi ? kGold : used.contains(i) ? const Color(0xFF5B4FC9) : kLine),
            ),
            child: Text(kSvara[i], style: TextStyle(fontSize: 13, fontWeight: used.contains(i) ? FontWeight.w700 : FontWeight.w400,
                color: i == samvadi ? const Color(0xFF1A1033) : used.contains(i) ? kInk : const Color(0xFF6F679F))),
          ),
      ]);
}

/// Notes of a song as bars on a pitch axis, with the tabla as ticks and a moving playhead.
class RollPainter extends CustomPainter {
  RollPainter(this.score, this.t);
  final Map score;
  final double t;
  @override
  void paint(Canvas c, Size s) {
    final dur = (score['duration'] as num).toDouble(), sa = (score['sa'] as num).toDouble();
    final lead = (score['lead'] as List);
    double semi(double f) => 12 * m.log(f / sa) / m.ln2;
    var lo = 99.0, hi = -99.0;
    for (final n in lead) {
      final v = semi((n[1] as num).toDouble());
      lo = m.min(lo, v);
      hi = m.max(hi, v);
    }
    if (lo > hi) {
      lo = 0;
      hi = 12;
    }
    lo -= 1.5;
    hi += 1.5;
    final rect = RRect.fromRectAndRadius(Offset.zero & s, const Radius.circular(16));
    c.drawRRect(rect, Paint()..color = const Color(0xFF0D0A24));
    c.save();
    c.clipRRect(rect);
    for (final sec in (score['sections'] as List)) {
      final x = (sec['t0'] as num) / dur * s.width;
      c.drawLine(Offset(x.toDouble(), 0), Offset(x.toDouble(), s.height), Paint()..color = kLine.withValues(alpha: .6));
      final tp = TextPainter(text: TextSpan(text: sec['name'], style: const TextStyle(color: Color(0xFF6F679F), fontSize: 10)), textDirection: TextDirection.ltr)..layout();
      tp.paint(c, Offset(x.toDouble() + 4, 4));
    }
    for (final b in (score['tabla'] as List)) {
      final x = (b[0] as num) / dur * s.width;
      c.drawRect(Rect.fromLTWH(x.toDouble(), s.height - 6, 1.4, 6), Paint()..color = kPeacock.withValues(alpha: .7));
    }
    for (final n in lead) {
      final x = (n[0] as num) / dur * s.width, w = m.max(3.0, (n[2] as num) / dur * s.width);
      final y = s.height - 12 - (semi((n[1] as num).toDouble()) - lo) / (hi - lo) * (s.height - 30);
      final on = t >= (n[0] as num) && t <= (n[0] as num) + (n[2] as num);
      c.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(x.toDouble(), y - 4, w, 8), const Radius.circular(4)),
          Paint()..color = on ? kRose : kGold.withValues(alpha: .85));
    }
    final px = t / dur * s.width;
    c.drawLine(Offset(px, 0), Offset(px, s.height), Paint()..color = kInk..strokeWidth = 1.6);
    c.restore();
  }

  @override
  bool shouldRepaint(RollPainter o) => o.t != t || o.score != score;
}
