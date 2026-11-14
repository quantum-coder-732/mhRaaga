import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'api.dart';
import 'player.dart';
import 'ui.dart';

const _langs = <(String, String, String)>[
  ('hi-IN', 'Hindi', 'hindi'), ('mr-IN', 'Marathi', 'marathi'), ('te-IN', 'Telugu', 'telugu'), ('ta-IN', 'Tamil', 'tamil'), ('gu-IN', 'Gujarati', 'gujarati'),
  ('kn-IN', 'Kannada', 'kannada'), ('bn-IN', 'Bengali', 'bengali'), ('pa-IN', 'Punjabi', 'punjabi'), ('en-IN', 'English (India)', 'english'),
  ('en-US', 'English (US)', 'english'), ('en-GB', 'English (UK)', 'english'), ('es-ES', 'Spanish', 'spanish'), ('fr-FR', 'French', 'french'),
  ('de-DE', 'German', 'german'), ('it-IT', 'Italian', 'italian'), ('pt-BR', 'Portuguese', 'portuguese'), ('ru-RU', 'Russian', 'russian'),
  ('ja-JP', 'Japanese', 'japanese'), ('ko-KR', 'Korean', 'korean'), ('zh-CN', 'Chinese', 'chinese'), ('ar-SA', 'Arabic', 'arabic'),
];
const _tones = {'calm': (0.85, 0.95), 'warm': (0.95, 1.0), 'energetic': (1.1, 1.12), 'devotional': (0.8, 0.9), 'dramatic': (0.9, 0.8), 'bright': (1.0, 1.2)};
const _hello = {
  'hi': 'नमस्ते, यह मेरी आवाज़ है।', 'mr': 'नमस्कार, हा माझा आवाज आहे.', 'te': 'నమస్కారం, ఇది నా స్వరం.', 'ta': 'வணக்கம், இது என் குரல்.', 'gu': 'નમસ્તે, આ મારો અવાજ છે.',
  'kn': 'ನಮಸ್ಕಾರ, ಇದು ನನ್ನ ಧ್ವನಿ.', 'bn': 'নমস্কার, এটি আমার কণ্ঠ।', 'en': 'Hello, this is my voice.', 'es': 'Hola, esta es mi voz.', 'fr': 'Bonjour, ceci est ma voix.',
  'de': 'Hallo, das ist meine Stimme.', 'it': 'Ciao, questa è la mia voce.', 'pt': 'Olá, esta é a minha voz.', 'ru': 'Привет, это мой голос.', 'ja': 'こんにちは、これは私の声です。',
  'ko': '안녕하세요, 제 목소리입니다.', 'zh': '你好，这是我的声音。', 'ar': 'مرحبا، هذا صوتي.',
};
final _fem = RegExp(r'female|woman|-f-|zira|heera|swara|neerja|kalpana|lekha|aditi|priya|samantha|karen|susan|hazel|victoria', caseSensitive: false);
final _mal = RegExp(r'\bmale\b|-m-|hemant|ravi|prabhat|madhur|david|mark|daniel|alex|diego', caseSensitive: false);

class SpeechPane extends StatefulWidget {
  const SpeechPane({super.key});
  @override
  State<SpeechPane> createState() => _SpeechPaneState();
}

class _SpeechPaneState extends State<SpeechPane> {
  final text = TextEditingController();
  final tts = FlutterTts();
  final stt = SpeechToText();
  String sttLang = 'en-IN', toLang = 'hi-IN', tone = 'warm', gender = '', voiceName = '', status = '';
  bool bg = true, listening = false, speaking = false;
  double variety = 3;
  int _run = 0;
  List<Map<String, String>> voices = [];

  @override
  void initState() {
    super.initState();
    _loadVoices();
  }

  @override
  void dispose() {
    _stop();
    super.dispose();
  }

  Future<void> _loadVoices() async {
    try {
      final v = await tts.getVoices as List?;
      final list = [for (final e in v ?? []) {'name': '${e['name']}', 'locale': '${e['locale']}'.replaceAll('_', '-')}];
      list.sort((a, b) => (_indian(b) ? 1 : 0) - (_indian(a) ? 1 : 0) == 0 ? a['name']!.compareTo(b['name']!) : (_indian(b) ? 1 : 0) - (_indian(a) ? 1 : 0));
      if (mounted) setState(() => voices = list);
    } catch (_) {}
  }

  bool _indian(Map<String, String> v) => v['locale']!.endsWith('-IN');
  String _g(Map<String, String> v) => _fem.hasMatch(v['name']!) ? 'f' : _mal.hasMatch(v['name']!) ? 'm' : '';
  List<Map<String, String>> get _shown => [for (final v in voices) if (gender.isEmpty || _g(v) == gender || _g(v).isEmpty) v];

  Future<void> _translate() async {
    if (text.text.trim().isEmpty) return setState(() => status = 'Nothing to translate.');
    setState(() => status = 'Translating…');
    try {
      final to = _langs.firstWhere((l) => l.$1 == toLang).$3;
      final r = await Api.call('POST', '/translate', body: {'text': text.text.trim(), 'to': to});
      setState(() {
        text.text = '${r['text']}';
        sttLang = toLang;
        status = 'Translated. Press Speak.';
      });
    } catch (e) {
      setState(() => status = e.toString());
    }
  }

  Future<void> _dictate() async {
    if (listening) {
      await stt.stop();
      return setState(() => listening = false);
    }
    final ok = await stt.initialize(onStatus: (s) {
      if (s == 'done' || s == 'notListening') setState(() => listening = false);
    }, onError: (_) => setState(() => listening = false));
    if (!ok) return setState(() => status = 'Speech recognition is not available. Check the microphone permission.');
    final base = text.text.isEmpty ? '' : '${text.text} ';
    setState(() => listening = true);
    await stt.listen(listenOptions: SpeechListenOptions(localeId: sttLang.replaceAll('-', '_')), onResult: (r) => setState(() => text.text = base + r.recognizedWords));
  }

  Future<void> _speakText(String t, String lang, {Map<String, String>? voice, double rate = 1, double pitch = 1}) async {
    await tts.awaitSpeakCompletion(true);
    Map<String, String>? v = voice;
    v ??= voices.where((x) => x['name'] == voiceName).firstOrNull;
    v ??= voices.where((x) => x['locale'] == lang).firstOrNull;
    if (v != null) await tts.setVoice({'name': v['name']!, 'locale': v['locale']!.replaceAll('-', '_')});
    await tts.setLanguage(v?['locale'] ?? lang);
    await tts.setSpeechRate((0.5 * rate).clamp(0.2, 1.0));
    await tts.setPitch(pitch);
    await tts.speak(t);
  }

  Future<void> _go() async {
    final t = text.text.trim();
    if (t.isEmpty) return setState(() => status = 'Write or paste a script first.');
    _stop();
    final my = ++_run;
    setState(() {
      speaking = true;
      status = 'Speaking…';
    });
    if (bg) {
      try {
        final d = await Api.call('GET', '/playlist', auth: false);
        final songs = List<Map<String, dynamic>>.from((d['songs'] as List).map((e) => Map<String, dynamic>.from(e)));
        if (songs.isNotEmpty) {
          final pick = songs[(((variety - 1) / 6) * (songs.length - 1)).round()];
          final full = Map<String, dynamic>.from(await Api.call('GET', '/playlist/${pick['id']}', auth: false));
          if (Player.i.voice) Player.i.toggleVoice(); // the bed plays without its own sung lyrics
          await Player.i.playFull(full);
        }
      } catch (_) {
        status = 'Background music unavailable.';
      }
    }
    final (rate, pitch) = _tones[tone]!;
    for (final s in RegExp(r'[^.!?।\n]+[.!?।]?').allMatches(t).map((m) => m[0]!.trim()).where((s) => s.isNotEmpty)) {
      if (my != _run) return;
      await _speakText(s, sttLang, rate: rate, pitch: pitch);
    }
    if (my == _run) {
      if (bg) await Player.i.stop();
      if (mounted) {
        setState(() {
          speaking = false;
          status = 'Done.';
        });
      }
    }
  }

  void _stop() {
    _run++;
    tts.stop();
    if (speaking) Player.i.stop();
    speaking = false;
  }

  Widget _dd(String label, String value, List<(String, String)> items, ValueChanged<String> on) => DropdownButtonFormField<String>(
        initialValue: items.any((e) => e.$1 == value) ? value : items.first.$1, isExpanded: true, dropdownColor: kBg2, decoration: InputDecoration(labelText: label),
        items: [for (final (v, t) in items) DropdownMenuItem(value: v, child: Text(t, overflow: TextOverflow.ellipsis))],
        onChanged: (v) => setState(() => on(v ?? '')),
      );

  @override
  Widget build(BuildContext context) {
    final shown = _shown;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      TextField(
        controller: text, minLines: 5, maxLines: 9, maxLength: 2500,
        decoration: InputDecoration(
          labelText: 'Script', hintText: 'Write, dictate, or paste a transcript', alignLabelWithHint: true,
          suffixIcon: IconButton(onPressed: _dictate, icon: Icon(listening ? Icons.mic : Icons.mic_none, color: listening ? kRose : kGold)),
        ),
      ),
      const SizedBox(height: 6),
      Row(children: [
        Expanded(child: _dd("I'm speaking in", sttLang, [for (final l in _langs) (l.$1, l.$2)], (v) => sttLang = v)),
        const SizedBox(width: 10),
        Expanded(child: _dd('Translate to', toLang, [for (final l in _langs) (l.$1, l.$2)], (v) => toLang = v)),
      ]),
      const SizedBox(height: 8),
      OutlinedButton.icon(onPressed: _translate, icon: const Icon(Icons.translate, color: kGold), label: const Text('Translate', style: TextStyle(color: kInk))),
      const SizedBox(height: 14),
      const Text('Tone', style: TextStyle(color: kMute, fontSize: 12)),
      const SizedBox(height: 6),
      Wrap(spacing: 8, children: [
        for (final t in _tones.keys)
          ChoiceChip(label: Text(t), selected: tone == t, selectedColor: kGold, showCheckmark: false, labelStyle: TextStyle(color: tone == t ? const Color(0xFF1A1033) : kMute), onSelected: (_) => setState(() => tone = t)),
      ]),
      const SizedBox(height: 12),
      _dd('Vocal gender (best guess from voice names)', gender, const [('', 'Any'), ('f', 'Female'), ('m', 'Male')], (v) => gender = v),
      const SizedBox(height: 12),
      _dd('Voice', voiceName, [('', 'Best match for the language'), for (final v in shown) (v['name']!, '${_indian(v) ? "🇮🇳 " : ""}${v['name']} (${v['locale']})')], (v) => voiceName = v),
      SwitchListTile(contentPadding: EdgeInsets.zero, activeThumbColor: kGold, title: const Text('Background music (raga bed)'), value: bg, onChanged: (v) => setState(() => bg = v)),
      if (bg) Row(children: [
        Text('Variety ${variety.round()}', style: const TextStyle(color: kMute)),
        Expanded(child: Slider(value: variety, min: 1, max: 7, divisions: 6, activeColor: kGold, onChanged: (v) => setState(() => variety = v))),
      ]),
      const SizedBox(height: 6),
      Row(children: [
        Expanded(child: FilledButton.icon(onPressed: speaking ? null : _go, icon: const Icon(Icons.record_voice_over), label: const Text('Speak'))),
        const SizedBox(width: 10),
        OutlinedButton(onPressed: () => setState(_stop), style: OutlinedButton.styleFrom(minimumSize: const Size(0, 50), side: const BorderSide(color: kLine)), child: const Text('Stop', style: TextStyle(color: kInk))),
      ]),
      if (status.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(status, style: const TextStyle(color: kMute))),
      ExpansionTile(
        tilePadding: EdgeInsets.zero, shape: const Border(), collapsedShape: const Border(), title: const Text('Test the voices on this phone'),
        children: [
          if (voices.isEmpty) const Padding(padding: EdgeInsets.all(8), child: Text('This phone reports no voices.', style: TextStyle(color: kMute))),
          for (final v in voices.take(60))
            ListTile(
              dense: true, contentPadding: EdgeInsets.zero,
              title: Text('${_indian(v) ? "🇮🇳 " : ""}${v['name']}', overflow: TextOverflow.ellipsis), subtitle: Text(v['locale']!, style: const TextStyle(color: kMute)),
              trailing: IconButton(icon: const Icon(Icons.play_arrow_rounded, color: kGold), onPressed: () => _speakText(_hello[v['locale']!.substring(0, 2)] ?? _hello['en']!, v['locale']!, voice: v)),
            ),
        ],
      ),
    ]);
  }
}
