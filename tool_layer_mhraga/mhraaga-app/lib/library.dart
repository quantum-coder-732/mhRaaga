import 'package:flutter/material.dart';
import 'api.dart';
import 'player.dart';
import 'ui.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});
  @override
  State<LibraryScreen> createState() => LibraryScreenState();
}

class LibraryScreenState extends State<LibraryScreen> {
  List<Map<String, dynamic>>? songs;
  String? err;
  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    try {
      final d = await Api.call('GET', '/songs');
      if (mounted) setState(() => songs = List<Map<String, dynamic>>.from((d['songs'] as List).map((e) => Map<String, dynamic>.from(e))));
    } catch (e) {
      if (mounted) setState(() => err = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (songs == null) return Center(child: err == null ? const CircularProgressIndicator() : Text(err!, style: const TextStyle(color: kRose)));
    return RefreshIndicator(
      color: kGold,
      onRefresh: reload,
      child: songs!.isEmpty
          ? ListView(children: const [SizedBox(height: 120), Center(child: OmBadge(size: 70)), SizedBox(height: 16), Center(child: Text('Nothing here yet.\nCompose your first raga.', textAlign: TextAlign.center, style: TextStyle(color: kMute, fontSize: 16)))])
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 20),
              itemCount: songs!.length,
              itemBuilder: (c, i) {
                final s = songs![i];
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Dismissible(
                    key: ValueKey(s['id']),
                    direction: DismissDirection.endToStart,
                    background: Container(alignment: Alignment.centerRight, padding: const EdgeInsets.only(right: 24), decoration: BoxDecoration(color: kRose.withValues(alpha: .25), borderRadius: BorderRadius.circular(20)), child: const Icon(Icons.delete_outline, color: kRose)),
                    confirmDismiss: (_) async => await showDialog<bool>(
                          context: context,
                          builder: (d) => AlertDialog(backgroundColor: kBg2, title: const Text('Delete this song?'), actions: [
                            TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Keep')),
                            TextButton(onPressed: () => Navigator.pop(d, true), child: const Text('Delete', style: TextStyle(color: kRose))),
                          ]),
                        ) ??
                        false,
                    onDismissed: (_) async {
                      setState(() => songs!.removeAt(i));
                      try {
                        await Api.call('DELETE', '/songs/${s['id']}');
                      } catch (e) {
                        if (mounted) snack(context, e.toString());
                      }
                    },
                    child: Glass(
                      onTap: () => Player.i.setQueue(songs!, i, isShared: false),
                      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                      child: Row(children: [
                        const OmBadge(size: 46),
                        const SizedBox(width: 14),
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(s['title'] ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                          Text('${s['raga']} · ${s['tala']} · ${fmt((s['duration'] as num?) ?? 0)}', style: const TextStyle(color: kMute, fontSize: 12)),
                        ])),
                        const Icon(Icons.play_circle_outline, color: kGold),
                      ]),
                    ),
                  ),
                );
              },
            ),
    );
  }
}
