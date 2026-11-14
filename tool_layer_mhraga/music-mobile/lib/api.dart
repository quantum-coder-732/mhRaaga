// Client for the aRaaga service (../music-backend). Sessions are bearer tokens kept in shared_preferences.
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// 10.0.2.2 is the Android emulator's alias for the host; override for a real
/// device with --dart-define=MUSIC_BASE_URL=http://LAN_IP:9100
const musicBase = String.fromEnvironment('MUSIC_BASE_URL', defaultValue: 'http://10.0.2.2:9100');

class Track {
  Track({
    required this.id, required this.title, required this.genre, required this.raga, required this.language,
    required this.mood, required this.lyrics, required this.durationSeconds, required this.peaks,
    required this.plays, required this.likes, required this.liked, required this.audioUrl,
  });

  final String id, title, genre, raga, language, mood, lyrics, audioUrl;
  final int durationSeconds, plays, likes;
  final bool liked;
  final List<double> peaks;

  factory Track.fromJson(Map<String, dynamic> j) => Track(
        id: j['id'], title: j['title'], genre: j['genre'] ?? '', raga: j['raga'] ?? '',
        language: j['language'] ?? '', mood: j['mood'] ?? '', lyrics: j['lyrics'] ?? '',
        durationSeconds: j['duration_seconds'] ?? 0, plays: j['plays'] ?? 0, likes: j['likes'] ?? 0,
        liked: j['liked'] ?? false, audioUrl: '$musicBase${j['audio_url']}',
        peaks: [for (final p in (j['peaks'] ?? []) as List) (p as num).toDouble()],
      );

  String get tags => [raga.isNotEmpty ? raga : genre, language, mood].where((s) => s.isNotEmpty).join(' · ');
}

/// Thrown on a 401: the caller drops back to the sign-in screen.
class SignedOut implements Exception {}

class MusicApi {
  MusicApi({http.Client? client}) : _http = client ?? http.Client();
  final http.Client _http;
  String? _token;
  String name = '';

  Future<String> _tokenValue() async => _token ??= (await SharedPreferences.getInstance()).getString('raaga-token') ?? '';

  Future<void> _setToken(String t) async {
    _token = t;
    final prefs = await SharedPreferences.getInstance();
    t.isEmpty ? await prefs.remove('raaga-token') : await prefs.setString('raaga-token', t);
  }

  /// True when a stored session is still accepted by the server.
  Future<bool> restore() async {
    if ((await _tokenValue()).isEmpty) return false;
    try {
      name = (await _call('GET', '/api/auth/me'))['name'] as String;
      return true;
    } on SignedOut {
      return false;
    }
  }

  Future<void> signIn(String email, String password) async => _session(await _call('POST', '/api/auth/login', body: {'email': email, 'password': password}, authed: false));
  Future<void> signUp(String name, String email, String password) async =>
      _session(await _call('POST', '/api/auth/signup', body: {'name': name, 'email': email, 'password': password}, authed: false));
  Future<void> signOut() => _setToken('');

  Future<void> _session(Map<String, dynamic> r) async {
    name = (r['user'] as Map<String, dynamic>)['name'] as String;
    await _setToken(r['token'] as String);
  }

  Future<Map<String, dynamic>> _call(String method, String path, {Map<String, dynamic>? body, bool authed = true}) async {
    final req = http.Request(method, Uri.parse('$musicBase$path'))
      ..headers.addAll({'Content-Type': 'application/json', if ((await _tokenValue()).isNotEmpty) 'Authorization': 'Bearer ${await _tokenValue()}'});
    if (body != null) req.body = jsonEncode(body);
    final res = await http.Response.fromStream(await _http.send(req).timeout(const Duration(seconds: 30)));
    final data = res.body.isEmpty ? <String, dynamic>{} : jsonDecode(res.body) as Map<String, dynamic>;
    if (res.statusCode == 401 && authed) {
      await _setToken('');
      throw SignedOut();
    }
    if (res.statusCode >= 400) {
      final d = data['detail'];
      throw Exception(d is String ? d : d is List ? 'Please check the details you entered.' : 'Request failed (${res.statusCode})');
    }
    return data;
  }

  Future<List<Track>> tracks({String sort = 'trending', String genre = '', String q = '', bool mine = false, bool liked = false}) async {
    final qs = Uri(queryParameters: {
      'sort': sort, if (genre.isNotEmpty) 'genre': genre, if (q.isNotEmpty) 'q': q,
      if (mine) 'mine': 'true', if (liked) 'liked': 'true',
    }).query;
    final data = await _call('GET', '/api/music/tracks?$qs');
    return [for (final t in data['tracks'] as List) Track.fromJson(t as Map<String, dynamic>)];
  }

  Future<String> generate(String prompt, {String lyrics = '', bool instrumental = false, int duration = 60}) async =>
      (await _call('POST', '/api/music/generate', body: {
        'prompt': prompt, 'lyrics': lyrics, 'instrumental': instrumental, 'duration_seconds': duration,
      }))['job_id'] as String;

  /// Polls until the job completes; [onStatus] receives QUEUED / PROCESSING.
  Future<Track> waitForJob(String id, {void Function(String)? onStatus}) async {
    for (;;) {
      await Future<void>.delayed(const Duration(milliseconds: 1200));
      final job = await _call('GET', '/api/music/jobs/$id');
      final status = job['status'] as String;
      if (status == 'FAILED') throw Exception(job['error'] ?? 'Generation failed');
      if (status == 'COMPLETED') return Track.fromJson(job['track'] as Map<String, dynamic>);
      onStatus?.call(status);
    }
  }

  Future<Track> like(String id) async => Track.fromJson(await _call('POST', '/api/music/tracks/$id/like'));
  Future<Track> countPlay(String id) async => Track.fromJson(await _call('POST', '/api/music/tracks/$id/play'));
}
