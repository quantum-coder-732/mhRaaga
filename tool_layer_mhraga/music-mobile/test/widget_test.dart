import 'package:flutter_test/flutter_test.dart';

import 'package:algo_music/api.dart';

void main() {
  test('Track.fromJson maps the backend payload', () {
    final t = Track.fromJson({
      'id': 'a1', 'title': 'Yaman', 'genre': 'bhajan', 'raga': 'yaman', 'language': 'hindi', 'mood': 'calm',
      'duration_seconds': 65, 'plays': 3, 'likes': 2, 'liked': true, 'audio_url': '/api/music/audio/a1.mp3',
      'peaks': [0.1, 1],
    });
    expect(t.audioUrl, '$musicBase/api/music/audio/a1.mp3');
    expect(t.tags, 'yaman · hindi · calm');
    expect(t.peaks, [0.1, 1.0]);
    expect(t.liked, isTrue);
  });
}
