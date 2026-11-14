import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'api.dart';
import 'main.dart' show composeRaga;
import 'player.dart';
import 'ui.dart';

class ComposeScreen extends StatefulWidget {
  const ComposeScreen({super.key, required this.onComposed});
  final VoidCallback onComposed;
  @override
  State<ComposeScreen> createState() => _ComposeScreenState();
}

class _ComposeScreenState extends State<ComposeScreen> {
  final prompt = TextEditingController(), lyrics = TextEditingController(), num = TextEditingController(text: '108');
  final stt = SpeechToText();
  List<String> classical = [];
  String raga = '', tala = '', language = '', lead = '', tonic = '';
  double duration = 90;
  bool instrumental = false, busy = false, listening = false;
  String? err;
  static const talas = ['teental', 'keherwa', 'dadra', 'rupak', 'jhaptal', 'ektal', 'adi'];

  @override
  void initState() {
    super.initState();
    Api.call('GET', '/ragas', auth: false).then((d) {
      if (mounted) setState(() => classical = [for (final r in d['classical']) r['name'] as String]);
    }).catchError((_) {});
    composeRaga.addListener(_jump);
  }

  void _jump() {
    final v = composeRaga.value;
    if (v == null) return;
    composeRaga.value = null;
    final m = RegExp(r'^(gopi|mela):(\d+)$').firstMatch(v);
    setState(() {
      if (m != null) {
        raga = m[1]!;
        num.text = m[2]!;
      } else {
        raga = v;
      }
    });
  }

  @override
  void dispose() {
    composeRaga.removeListener(_jump);
    super.dispose();
  }

  Future<void> _dictate(TextEditingController into) async {
    if (listening) {
      await stt.stop();
      setState(() => listening = false);
      return;
    }
    final ok = await stt.initialize(onError: (_) => setState(() => listening = false), onStatus: (s) {
      if (s == 'done' || s == 'notListening') setState(() => listening = false);
    });
    if (!ok) {
      if (mounted) snack(context, 'Speech recognition is not available. Check the microphone permission.');
      return;
    }
    final base = into.text.isEmpty ? '' : '${into.text} ';
    setState(() => listening = true);
    await stt.listen(
      listenOptions: SpeechListenOptions(localeId: switch (language) { 'marathi' => 'mr_IN', 'hindi' || 'sanskrit' => 'hi_IN', 'telugu' => 'te_IN', 'gujarati' => 'gu_IN', 'kannada' => 'kn_IN', 'tamil' => 'ta_IN', _ => null }),
      onResult: (r) => setState(() => into.text = base + r.recognizedWords),
    );
  }

  String get _ragaSpec => raga == 'gopi' ? 'gopi:${int.tryParse(num.text)?.clamp(1, 16000) ?? 1}' : raga == 'mela' ? 'mela:${int.tryParse(num.text)?.clamp(1, 72) ?? 1}' : raga;

  Future<void> _compose() async {
    if (prompt.text.trim().length < 3) {
      setState(() => err = 'Describe the song first.');
      return;
    }
    setState(() {
      busy = true;
      err = null;
    });
    try {
      final body = {
        'prompt': prompt.text.trim(), 'raga': _ragaSpec, 'tala': tala, 'language': language, 'lead': lead, 'instrumental': instrumental,
        'duration': duration.round(), if (tonic.isNotEmpty) 'tonic': int.parse(tonic), if (lyrics.text.trim().isNotEmpty) 'lyrics': lyrics.text.trim(),
      };
      final song = Map<String, dynamic>.from(await Api.call('POST', '/compose', body: body));
      if (!mounted) return;
      widget.onComposed();
      await Player.i.playFull(song);
    } catch (e) {
      setState(() => err = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Widget _drop(String label, String value, List<(String, String)> items, ValueChanged<String> on) => DropdownButtonFormField<String>(
        initialValue: value, isExpanded: true, dropdownColor: kBg2, decoration: InputDecoration(labelText: label),
        items: [for (final (v, t) in items) DropdownMenuItem(value: v, child: Text(t, overflow: TextOverflow.ellipsis))],
        onChanged: (v) => setState(() => on(v ?? '')),
      );

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(16, 14, 16, 24), children: [
        Glass(
          padding: const EdgeInsets.all(18),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('Compose a raga', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            const Text('Say it or type it. The planner picks raga, tāla and words; the engine follows the raga rules.', style: TextStyle(color: kMute)),
            const SizedBox(height: 14),
            TextField(
              controller: prompt, minLines: 3, maxLines: 5, maxLength: 800,
              decoration: InputDecoration(
                labelText: 'Describe the song', hintText: 'A Krishna bansuri bhajan for the dawn…', alignLabelWithHint: true,
                suffixIcon: IconButton(onPressed: () => _dictate(prompt), icon: Icon(listening ? Icons.mic : Icons.mic_none, color: listening ? kRose : kGold)),
              ),
            ),
            const SizedBox(height: 6),
            _drop('Raga', raga, [('', 'Let the AI choose'), for (final r in classical) (r, r), ('gopi', 'Krishna\'s gopī raga (1–16000)'), ('mela', 'Melakarta (1–72)')], (v) => raga = v),
            if (raga == 'gopi' || raga == 'mela') ...[
              const SizedBox(height: 12),
              TextField(controller: num, keyboardType: TextInputType.number, decoration: InputDecoration(labelText: raga == 'gopi' ? 'Gopī number' : 'Melakarta number')),
            ],
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: _drop('Tāla', tala, [('', 'Raga\'s own'), for (final t in talas) (t, t)], (v) => tala = v)),
              const SizedBox(width: 10),
              Expanded(child: _drop('Language', language, [('', 'Auto'), ('hindi', 'Hindi'), ('marathi', 'Marathi'), ('sanskrit', 'Sanskrit'), ('english', 'English'), ('telugu', 'Telugu'), ('gujarati', 'Gujarati'), ('kannada', 'Kannada'), ('tamil', 'Tamil')], (v) => language = v)),
            ]),
            const SizedBox(height: 14),
            const Text('Lead instrument', style: TextStyle(color: kMute, fontSize: 12)),
            const SizedBox(height: 6),
            SegmentedButton<String>(
              showSelectedIcon: false, emptySelectionAllowed: false,
              segments: const [ButtonSegment(value: '', label: Text('Auto')), ButtonSegment(value: 'bansuri', label: Text('Bansurī')), ButtonSegment(value: 'harmonium', label: Text('Harm.')), ButtonSegment(value: 'veena', label: Text('Vīṇā'))],
              selected: {lead}, onSelectionChanged: (s) => setState(() => lead = s.first),
            ),
            const SizedBox(height: 14),
            const Text('Sa (tonic)', style: TextStyle(color: kMute, fontSize: 12)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, children: [
              for (final (v, t) in [('', 'Raga\'s own'), ('183', '183 Hz'), ('233', '233 Hz'), ('234', '234 Hz')])
                ChoiceChip(label: Text(t), selected: tonic == v, selectedColor: kGold, labelStyle: TextStyle(color: tonic == v ? const Color(0xFF1A1033) : kMute), onSelected: (_) => setState(() => tonic = v)),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              Text('Length ${duration.round()} s', style: const TextStyle(color: kMute)),
              Expanded(child: Slider(value: duration, min: 40, max: 180, divisions: 14, activeColor: kGold, onChanged: (v) => setState(() => duration = v))),
            ]),
            SwitchListTile(contentPadding: EdgeInsets.zero, activeThumbColor: kGold, title: const Text('Instrumental (no lyrics)'), value: instrumental, onChanged: (v) => setState(() => instrumental = v)),
            ExpansionTile(
              tilePadding: EdgeInsets.zero, shape: const Border(), collapsedShape: const Border(), title: const Text('Write my own lyrics'),
              children: [TextField(controller: lyrics, minLines: 4, maxLines: 8, decoration: InputDecoration(hintText: '[Mukhda]\n…\n[Antara]\n…', suffixIcon: IconButton(onPressed: () => _dictate(lyrics), icon: Icon(Icons.mic_none, color: kGold))))],
            ),
            if (err != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(err!, style: const TextStyle(color: kRose))),
            const SizedBox(height: 14),
            FilledButton.icon(
              onPressed: busy ? null : _compose,
              icon: busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4)) : const Icon(Icons.auto_awesome),
              label: Text(busy ? 'Composing…' : 'Compose'),
            ),
          ]),
        ),
      ]);
}
