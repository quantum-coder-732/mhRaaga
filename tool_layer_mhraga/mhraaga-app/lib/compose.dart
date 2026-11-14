import 'dart:math';
import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'api.dart';
import 'main.dart' show composeRaga;
import 'player.dart';
import 'speech.dart';
import 'ui.dart';

class ComposeScreen extends StatefulWidget {
  const ComposeScreen({super.key, required this.onComposed});
  final VoidCallback onComposed;
  @override
  State<ComposeScreen> createState() => _ComposeScreenState();
}

class _ComposeScreenState extends State<ComposeScreen> {
  final prompt = TextEditingController(), lyrics = TextEditingController();
  final stt = SpeechToText();
  List<String> classical = [];
  String raga = '', tala = '', language = '', lead = '', forced = '';
  final title = TextEditingController();
  final tags = <String>{};
  int tab = 0;
  bool simple = false;
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
    setState(() {
      if (RegExp(r'^(gopi|mela):\d+$').hasMatch(v)) {
        forced = v;
        if (v.startsWith('gopi')) tags.add('krishna');
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

  String get _ragaSpec => forced.isNotEmpty ? forced : tags.contains('krishna') ? 'gopi:${1 + Random().nextInt(16000)}' : raga;

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
        'prompt': _promptWithStyle, 'raga': _ragaSpec, 'tala': tala, 'language': language, 'lead': _lead, 'instrumental': instrumental,
        'duration': tags.contains('poem') ? max(120, duration.round()) : duration.round(), if (tags.contains('poem')) 'poem': true, if (title.text.trim().isNotEmpty) 'title': title.text.trim(), if (lyrics.text.trim().isNotEmpty) 'lyrics': lyrics.text.trim(),
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

  String get _promptWithStyle {
    final bits = tags.where((t) => t != 'krishna' && t != 'poem' && !_leads.contains(t)).toList();
    return bits.isEmpty ? prompt.text.trim() : '${prompt.text.trim()}. Style: ${bits.join(", ")}';
  }

  String get _lead {
    final l = tags.firstWhere(_leads.contains, orElse: () => '');
    return l.isNotEmpty ? l : tags.contains('krishna') ? 'bansuri' : lead;
  }

  static const _leads = ['bansuri', 'veena', 'harmonium'];
  static const _styles = ['poem', 'krishna', 'devotional', 'dawn', 'rain', 'night', 'romantic', 'meditative', 'joyful', 'bhajan', 'bansuri', 'veena', 'harmonium'];

  Widget _tabs() => Container(
        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: kLine))),
        child: Row(children: [
          for (final (i, t) in [(0, 'Songs'), (1, 'Speech')])
            Expanded(
              child: InkWell(
                onTap: () => setState(() => tab = i),
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  decoration: BoxDecoration(border: Border(bottom: BorderSide(color: tab == i ? kInk : Colors.transparent, width: 2))),
                  child: Text(t, textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.w700, color: tab == i ? kInk : kMute)),
                ),
              ),
            ),
        ]),
      );

  Widget _styleChips() => Wrap(spacing: 8, runSpacing: 4, children: [
        for (final t in _styles)
          FilterChip(
            label: Text(t == 'krishna' ? '🪈 Krishna flute' : t == 'poem' ? '📜 Spoken poem' : t),
            selected: tags.contains(t),
            selectedColor: kGold,
            showCheckmark: false,
            labelStyle: TextStyle(color: tags.contains(t) ? const Color(0xFF1A1033) : t == 'krishna' ? kGold : kMute, fontWeight: tags.contains(t) ? FontWeight.w700 : FontWeight.w400),
            onSelected: (v) => setState(() {
              if (_leads.contains(t)) tags.removeAll(_leads);
              v ? tags.add(t) : tags.remove(t);
              if (t == 'krishna' && !v) forced = '';
            }),
          ),
      ]);

  Widget _songs() => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Align(
          alignment: Alignment.centerLeft,
          child: SegmentedButton<bool>(
            showSelectedIcon: false,
            segments: const [ButtonSegment(value: true, label: Text('Simple')), ButtonSegment(value: false, label: Text('Advanced'))],
            selected: {simple},
            onSelectionChanged: (s) => setState(() => simple = s.first),
          ),
        ),
        const SizedBox(height: 14),
        TextField(
          controller: prompt, minLines: 3, maxLines: 5, maxLength: 800,
          decoration: InputDecoration(
            labelText: 'Describe the song', hintText: 'A dawn bhajan, gentle and flowing…', alignLabelWithHint: true,
            suffixIcon: IconButton(onPressed: () => _dictate(prompt), icon: Icon(listening ? Icons.mic : Icons.mic_none, color: listening ? kRose : kGold)),
          ),
        ),
        if (!simple) ...[
          const SizedBox(height: 6),
          const Text('Styles', style: TextStyle(color: kMute, fontSize: 12)),
          const SizedBox(height: 6),
          _styleChips(),
          const SizedBox(height: 12),
          _drop('Raga', raga, [('', 'Let the AI choose'), for (final r in classical) (r, r)], (v) => raga = v),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: _drop('Tāla', tala, [('', 'Raga\'s own'), for (final t in talas) (t, t)], (v) => tala = v)),
            const SizedBox(width: 10),
            Expanded(child: _drop('Language', language, [('', 'Auto'), ('hindi', 'Hindi'), ('marathi', 'Marathi'), ('english', 'English'), ('telugu', 'Telugu'), ('gujarati', 'Gujarati'), ('kannada', 'Kannada'), ('tamil', 'Tamil'), ('sanskrit', 'Sanskrit')], (v) => language = v)),
          ]),
          const SizedBox(height: 12),
          TextField(controller: title, maxLength: 60, decoration: const InputDecoration(labelText: 'Song title (optional)')),
          Row(children: [
            Text('Length ${duration.round()} s', style: const TextStyle(color: kMute)),
            Expanded(child: Slider(value: duration, min: 40, max: 180, divisions: 14, activeColor: kGold, onChanged: (v) => setState(() => duration = v))),
          ]),
          SwitchListTile(contentPadding: EdgeInsets.zero, activeThumbColor: kGold, title: const Text('Instrumental (no lyrics)'), value: instrumental, onChanged: (v) => setState(() => instrumental = v)),
          ExpansionTile(
            tilePadding: EdgeInsets.zero, shape: const Border(), collapsedShape: const Border(), title: const Text('Write my own lyrics'),
            children: [TextField(controller: lyrics, minLines: 4, maxLines: 8, decoration: InputDecoration(hintText: '[Mukhda]\n…\n[Antara]\n…', suffixIcon: IconButton(onPressed: () => _dictate(lyrics), icon: const Icon(Icons.mic_none, color: kGold))))],
          ),
        ],
        if (err != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(err!, style: const TextStyle(color: kRose))),
        const SizedBox(height: 14),
        FilledButton.icon(
          onPressed: busy ? null : _compose,
          icon: busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4)) : const Icon(Icons.auto_awesome),
          label: Text(busy ? 'Composing…' : 'Create'),
        ),
      ]);

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(16, 10, 16, 24), children: [
        Glass(padding: const EdgeInsets.fromLTRB(18, 0, 18, 18), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _tabs(),
          const SizedBox(height: 16),
          if (tab == 0) _songs() else const SpeechPane(),
        ])),
      ]);
}
