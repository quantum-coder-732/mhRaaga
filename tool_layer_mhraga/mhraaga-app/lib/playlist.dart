import 'package:flutter/material.dart';
import 'api.dart';
import 'player.dart';
import 'ui.dart';

/// The common playlist: songs everyone can hear, stored in the cloud.
class PlaylistScreen extends StatefulWidget {
  const PlaylistScreen({super.key});
  @override
  State<PlaylistScreen> createState() => _PlaylistScreenState();
}

class _PlaylistScreenState extends State<PlaylistScreen> {
  late Future<List<Map<String, dynamic>>> f = _load();
  Future<List<Map<String, dynamic>>> _load() async =>
      List<Map<String, dynamic>>.from(((await Api.call('GET', '/playlist', auth: false))['songs'] as List).map((e) => Map<String, dynamic>.from(e)));

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        color: kGold,
        onRefresh: () async {
          setState(() => f = _load());
          await f;
        },
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: f,
          builder: (c, snap) {
            final songs = snap.data ?? [];
            return ListenableBuilder(
              listenable: Player.i,
              builder: (c, _) => ListView(padding: const EdgeInsets.fromLTRB(16, 14, 16, 20), children: [
                Glass(
                  glow: true,
                  padding: const EdgeInsets.all(20),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Community playlist', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 6),
                    const Text('Ragas composed by the mhRaaga engine, stored in the cloud for everyone to hear.', style: TextStyle(color: kMute)),
                    const SizedBox(height: 16),
                    Row(children: [
                      Expanded(child: FilledButton.icon(onPressed: songs.isEmpty ? null : () => Player.i.setQueue(songs, 0, isShared: true), icon: const Icon(Icons.play_arrow_rounded), label: const Text('Play all'))),
                      const SizedBox(width: 10),
                      Chipx('${songs.length} songs', gold: true),
                    ]),
                  ]),
                ),
                const SizedBox(height: 16),
                if (snap.connectionState != ConnectionState.done) const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator())),
                if (snap.hasError) Padding(padding: const EdgeInsets.all(24), child: Text('${snap.error}', style: const TextStyle(color: kRose))),
                for (var i = 0; i < songs.length; i++) _Tile(songs, i),
              ]),
            );
          },
        ),
      );
}

class _Tile extends StatelessWidget {
  const _Tile(this.songs, this.i);
  final List<Map<String, dynamic>> songs;
  final int i;
  @override
  Widget build(BuildContext context) {
    final s = songs[i], p = Player.i;
    final active = p.shared && p.song?['id'] == s['id'];
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Glass(
        glow: active,
        padding: const EdgeInsets.fromLTRB(12, 10, 14, 10),
        onTap: () => p.setQueue(songs, i, isShared: true),
        child: Row(children: [
          Container(
            width: 52, height: 52, alignment: Alignment.center,
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(14), gradient: LinearGradient(colors: [Color.lerp(kGold, kRose, i / 6)!, const Color(0xFF3B2D95)])),
            child: active && p.playing ? const Icon(Icons.graphic_eq, color: Colors.white) : Text('${i + 1}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Colors.white)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(s['title'] ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: active ? kGold : kInk)),
              const SizedBox(height: 2),
              Text('${s['raga']} · ${s['tala']} · ${s['tempo']} bpm', style: const TextStyle(color: kMute, fontSize: 12)),
              Text('${s['mood']}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMute, fontSize: 12)),
            ]),
          ),
          Text(fmt((s['duration'] as num?) ?? 0), style: const TextStyle(color: kMute, fontSize: 12)),
        ]),
      ),
    );
  }
}
