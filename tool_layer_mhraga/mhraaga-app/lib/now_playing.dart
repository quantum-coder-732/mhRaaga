import 'package:flutter/material.dart';
import 'player.dart';
import 'ui.dart';

class NowPlaying extends StatelessWidget {
  const NowPlaying({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        body: Night(
          child: SafeArea(
            child: ListenableBuilder(
              listenable: Player.i,
              builder: (c, _) {
                final p = Player.i, s = p.song;
                if (s == null) return Center(child: FilledButton(onPressed: () => Navigator.pop(c), child: const Text('Close')));
                final score = s['score'] as Map, meta = score['meta'] as Map;
                final t = p.pos.inMilliseconds / 1000, dur = (score['duration'] as num).toDouble();
                final lyric = p.lyricNow();
                return ListView(padding: const EdgeInsets.fromLTRB(20, 4, 20, 24), children: [
                  Row(children: [
                    IconButton(onPressed: () => Navigator.pop(c), icon: const Icon(Icons.keyboard_arrow_down_rounded, size: 32)),
                    const Spacer(),
                    const Text('NOW PLAYING', style: TextStyle(letterSpacing: 2, fontSize: 12, color: kMute)),
                    const Spacer(),
                    IconButton(onPressed: p.toggleVoice, tooltip: 'Recite the lyrics', icon: Icon(p.voice ? Icons.record_voice_over : Icons.voice_over_off, color: p.voice ? kGold : kMute)),
                  ]),
                  const SizedBox(height: 8),
                  Center(child: Container(
                    width: 150, height: 150, alignment: Alignment.center,
                    decoration: BoxDecoration(shape: BoxShape.circle, gradient: const RadialGradient(colors: [Color(0xFF5A46D0), Color(0xFF1B1646)]),
                        border: Border.all(color: kGold.withValues(alpha: .6), width: 2), boxShadow: [BoxShadow(color: kGold.withValues(alpha: p.playing ? .35 : .12), blurRadius: 40)]),
                    child: const Text('ॐ', style: TextStyle(fontSize: 70, color: kGold)),
                  )),
                  const SizedBox(height: 18),
                  Text(s['title'] ?? '', textAlign: TextAlign.center, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  Wrap(alignment: WrapAlignment.center, spacing: 6, runSpacing: 6, children: [
                    Chipx('${s['raga']}', gold: true), Chipx('${s['tala']}'), Chipx('${s['tempo']} bpm'),
                    Chipx('${score['lead_voice']}'), Chipx('vādī ${kSvara[(meta['vadi'] as num).toInt()]} · samvādī ${kSvara[(meta['samvadi'] as num).toInt()]}'),
                  ]),
                  const SizedBox(height: 18),
                  SizedBox(height: 170, child: CustomPaint(painter: RollPainter(score, t), size: Size.infinite)),
                  Container(
                    height: 88, alignment: Alignment.center, padding: const EdgeInsets.symmetric(vertical: 8),
                    child: AnimatedSwitcher(duration: const Duration(milliseconds: 300),
                        child: Text(lyric, key: ValueKey(lyric), textAlign: TextAlign.center, style: const TextStyle(fontSize: 21, height: 1.35, color: kGold))),
                  ),
                  Slider(value: t.clamp(0, dur).toDouble(), max: dur, activeColor: kGold, inactiveColor: kLine, onChanged: (v) => p.seek(v)),
                  Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(fmt(t), style: const TextStyle(color: kMute)), Text(fmt(dur), style: const TextStyle(color: kMute))])),
                  const SizedBox(height: 6),
                  Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    IconButton(iconSize: 38, onPressed: p.prev, icon: const Icon(Icons.skip_previous_rounded)),
                    const SizedBox(width: 10),
                    Container(
                      decoration: const BoxDecoration(shape: BoxShape.circle, color: kGold),
                      child: IconButton(iconSize: 48, color: const Color(0xFF1A1033), onPressed: p.loading ? null : p.toggle, icon: Icon(p.playing ? Icons.pause_rounded : Icons.play_arrow_rounded)),
                    ),
                    const SizedBox(width: 10),
                    IconButton(iconSize: 38, onPressed: p.next, icon: const Icon(Icons.skip_next_rounded)),
                  ]),
                  const SizedBox(height: 14),
                  Glass(child: ExpansionTile(
                    tilePadding: EdgeInsets.zero, shape: const Border(), collapsedShape: const Border(),
                    title: const Text('Lyrics', style: TextStyle(fontWeight: FontWeight.w700)),
                    children: [Align(alignment: Alignment.centerLeft, child: Text(
                      (score['lyrics'] as List).map((l) => l['text']).join('\n'), style: const TextStyle(color: kInk, height: 1.5)))],
                  )),
                ]);
              },
            ),
          ),
        ),
      );
}
