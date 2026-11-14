import 'dart:math' as m;
import 'dart:async';
import 'dart:io';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:path_provider/path_provider.dart';
import 'api.dart';
import 'synth.dart';

/// One player for the whole app: fetches a song, renders it, plays it, and recites the lyrics on cue.
class Player extends ChangeNotifier {
  Player._() {
    _tts.setCompletionHandler(() => _ap.setVolume(1.0));
    _tts.setCancelHandler(() => _ap.setVolume(1.0));
    _tts.setErrorHandler((_) => _ap.setVolume(1.0));
  }
  static final Player i = Player._();

  final AudioPlayer _ap = AudioPlayer();
  final AudioPlayer _pv = AudioPlayer();
  final FlutterTts _tts = FlutterTts();
  bool _ready = false;

  Map<String, dynamic>? song; // full song (with score)
  List<Map<String, dynamic>> queue = [];
  int index = -1;
  bool shared = false; // current queue is the community playlist
  bool loading = false, playing = false, voice = true;
  String? error;
  Duration pos = Duration.zero, total = Duration.zero;
  int _lyricIdx = -1;
  String? previewing;

  Future<void> _init() async {
    if (_ready) return;
    _ready = true;
    _ap.onPositionChanged.listen((p) {
      pos = p;
      _cue(p.inMilliseconds / 1000);
      notifyListeners();
    });
    _ap.onDurationChanged.listen((d) {
      total = d;
      notifyListeners();
    });
    _ap.onPlayerStateChanged.listen((s) {
      playing = s == PlayerState.playing;
      notifyListeners();
    });
    _ap.onPlayerComplete.listen((_) => next());
    _pv.onPlayerComplete.listen((_) {
      previewing = null;
      notifyListeners();
    });
  }

  String get _lang => switch (song?['language']) { 'marathi' => 'mr-IN', 'english' => 'en-IN', 'telugu' => 'te-IN', 'gujarati' => 'gu-IN', 'kannada' => 'kn-IN', 'tamil' => 'ta-IN', _ => 'hi-IN' };

  void _cue(double t) {
    if (!voice || song == null || !playing) return;
    final ly = (song!['score']['lyrics'] as List);
    for (var k = 0; k < ly.length; k++) {
      final l = ly[k] as Map;
      final s = (l['t'] as num).toDouble(), d = (l['dur'] as num).toDouble();
      if (d > 0 && (l['tag'] ?? '') == '' && t >= s && t < s + d) {
        if (k != _lyricIdx) {
          _lyricIdx = k;
          final text = l['text'] as String;
          // characters a voice speaks per second at normal rate: Indic scripts vs Latin. Fit the line to its slot, never rush it.
          final cps = RegExp(r'[\u0900-\u0D7F]').hasMatch(text) ? 11.0 : 14.0;
          final rate = (text.length / (m.max(1.0, d) * cps)).clamp(0.7, 1.1);
          _tts.setLanguage(_lang);
          _tts.setSpeechRate((0.5 * rate).clamp(0.3, 0.6));
          _ap.setVolume(0.55); // the music steps back while the voice speaks
          _tts.speak(text);
        }
        return;
      }
    }
  }

  String lyricNow() {
    if (song == null) return '';
    final t = pos.inMilliseconds / 1000;
    for (final l in (song!['score']['lyrics'] as List)) {
      final s = (l['t'] as num).toDouble(), d = (l['dur'] as num).toDouble();
      if (d > 0 && (l['tag'] ?? '') == '' && t >= s && t < s + d) return l['text'] as String;
    }
    return '';
  }

  Future<void> setQueue(List<Map<String, dynamic>> q, int at, {required bool isShared}) async {
    queue = q;
    shared = isShared;
    index = at;
    await _open(q[at]);
  }

  Future<void> _open(Map<String, dynamic> summary) async {
    await _init();
    await _pv.stop();
    previewing = null;
    loading = true;
    error = null;
    notifyListeners();
    try {
      await _ap.stop();
      _tts.stop();
      final full = summary.containsKey('score')
          ? summary
          : await Api.call('GET', (shared ? '/playlist/' : '/songs/') + summary['id'], auth: !shared) as Map<String, dynamic>;
      await _play(full);
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
    }
  }

  /// Play a freshly composed song (not part of a queue).
  Future<void> playFull(Map<String, dynamic> full) async {
    queue = [full];
    index = 0;
    shared = false;
    await _init();
    await _pv.stop();
    loading = true;
    error = null;
    notifyListeners();
    try {
      await _ap.stop();
      await _play(full);
    } catch (e) {
      error = e.toString();
      loading = false;
      notifyListeners();
    }
  }

  Future<void> _play(Map<String, dynamic> full) async {
    song = full;
    _lyricIdx = -1;
    pos = Duration.zero;
    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/mh_${full['id']}.wav');
    if (!f.existsSync()) {
      final bytes = await compute(renderScore, Map<String, dynamic>.from(full['score'] as Map));
      await f.writeAsBytes(bytes, flush: true);
    }
    loading = false;
    notifyListeners();
    await _ap.play(DeviceFileSource(f.path));
    if (shared) Api.call('POST', '/playlist/${full['id']}/play', auth: false, body: {}).catchError((_) => <String, dynamic>{});
  }

  Future<void> toggle() async {
    if (song == null) return;
    if (playing) {
      await _ap.pause();
      _tts.stop();
    } else {
      await _ap.resume();
    }
  }

  Future<void> seek(double seconds) async {
    _lyricIdx = -1;
    _tts.stop();
    await _ap.seek(Duration(milliseconds: (seconds * 1000).round()));
  }

  Future<void> next() async {
    if (queue.length > 1 && index + 1 < queue.length) {
      index++;
      await _open(queue[index]);
    } else {
      playing = false;
      notifyListeners();
    }
  }

  Future<void> prev() async {
    if (pos.inSeconds > 4 || index <= 0) return seek(0);
    index--;
    await _open(queue[index]);
  }

  void toggleVoice() {
    voice = !voice;
    if (!voice) _tts.stop();
    notifyListeners();
  }

  Future<void> stop() async {
    await _ap.stop();
    _tts.stop();
    song = null;
    notifyListeners();
  }

  /// Listen to a raga's notes (Ragas browser).
  Future<void> preview(String key, Map<String, dynamic> raga, double sa) async {
    await _init();
    if (previewing == key) {
      await _pv.stop();
      previewing = null;
      notifyListeners();
      return;
    }
    await _ap.pause();
    previewing = key;
    notifyListeners();
    final bytes = await compute(renderPreview, {'sa': sa, 'aroha': raga['aroha'], 'avaroha': raga['avaroha']});
    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/mh_prev.wav');
    await f.writeAsBytes(bytes, flush: true);
    if (previewing != key) return;
    await _pv.play(DeviceFileSource(f.path));
  }
}
