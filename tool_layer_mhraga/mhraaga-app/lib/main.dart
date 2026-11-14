import 'package:flutter/material.dart';
import 'api.dart';
import 'compose.dart';
import 'library.dart';
import 'login.dart';
import 'now_playing.dart';
import 'player.dart';
import 'playlist.dart';
import 'ragas.dart';
import 'studio.dart';
import 'ui.dart';

/// Set by the Ragas browser to jump to Compose with a raga preselected.
final ValueNotifier<String?> composeRaga = ValueNotifier(null);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Api.restore();
  runApp(const MhRaaga());
}

class MhRaaga extends StatefulWidget {
  const MhRaaga({super.key});
  @override
  State<MhRaaga> createState() => _MhRaagaState();
}

class _MhRaagaState extends State<MhRaaga> {
  final _nav = GlobalKey<NavigatorState>();
  bool signedIn = Api.token != null;
  @override
  Widget build(BuildContext context) => MaterialApp(
        navigatorKey: _nav,
        title: 'mhRaaga',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        builder: (c, child) => Night(child: child!),
        home: signedIn ? Shell(onSignOut: _out) : LoginScreen(onDone: () => setState(() => signedIn = true)),
      );
  Future<void> _out() async {
    await Player.i.stop();
    await Api.signOut();
    setState(() => signedIn = false);
  }
}

class Shell extends StatefulWidget {
  const Shell({super.key, required this.onSignOut});
  final VoidCallback onSignOut;
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int tab = 0;
  final libKey = GlobalKey<LibraryScreenState>();
  @override
  void initState() {
    super.initState();
    composeRaga.addListener(() {
      if (composeRaga.value != null && mounted) setState(() => tab = 2);
    });
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      const PlaylistScreen(),
      LibraryScreen(key: libKey),
      ComposeScreen(onComposed: () {
        setState(() => tab = 1);
        libKey.currentState?.reload();
      }),
      const RagasScreen(),
      const StudioScreen(),
    ];
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 10, 8, 0),
            child: Row(children: [
              const OmBadge(size: 40),
              const SizedBox(width: 10),
              const Expanded(child: Text('mhRaaga', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: .3))),
              PopupMenuButton<String>(
                icon: const Icon(Icons.account_circle_outlined, color: kMute),
                color: kBg2,
                onSelected: (_) => widget.onSignOut(),
                itemBuilder: (_) => [
                  PopupMenuItem(enabled: false, child: Text(Api.user?['name'] ?? '', style: const TextStyle(color: kMute))),
                  const PopupMenuItem(value: 'out', child: Text('Sign out')),
                ],
              ),
            ]),
          ),
          Expanded(child: IndexedStack(index: tab, children: pages)),
          const MiniPlayer(),
        ]),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.queue_music_outlined), selectedIcon: Icon(Icons.queue_music), label: 'Playlist'),
          NavigationDestination(icon: Icon(Icons.library_music_outlined), selectedIcon: Icon(Icons.library_music), label: 'My songs'),
          NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), selectedIcon: Icon(Icons.auto_awesome), label: 'Compose'),
          NavigationDestination(icon: Icon(Icons.graphic_eq), selectedIcon: Icon(Icons.graphic_eq), label: 'Ragas'),
          NavigationDestination(icon: Icon(Icons.movie_creation_outlined), selectedIcon: Icon(Icons.movie_creation), label: 'Studio'),
        ],
      ),
    );
  }
}

class MiniPlayer extends StatelessWidget {
  const MiniPlayer({super.key});
  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: Player.i,
        builder: (c, _) {
          final p = Player.i;
          if (p.song == null && !p.loading) return const SizedBox.shrink();
          final s = p.song;
          return Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: Glass(
              glow: true,
              padding: const EdgeInsets.fromLTRB(12, 8, 8, 6),
              onTap: s == null ? null : () => Navigator.of(c).push(MaterialPageRoute(builder: (_) => const NowPlaying(), fullscreenDialog: true)),
              child: Column(children: [
                Row(children: [
                  const OmBadge(size: 40),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(p.loading ? 'Rendering the raga…' : (s?['title'] ?? ''), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
                      Text(p.error ?? (s == null ? '' : '${s['raga']} · ${s['tala']}'), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMute, fontSize: 12)),
                    ]),
                  ),
                  if (p.loading)
                    const Padding(padding: EdgeInsets.all(12), child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4)))
                  else ...[
                    IconButton(onPressed: p.toggle, icon: Icon(p.playing ? Icons.pause_circle_filled : Icons.play_circle_fill, size: 40, color: kGold)),
                    IconButton(onPressed: p.stop, icon: const Icon(Icons.close, color: kMute)),
                  ],
                ]),
                if (s != null)
                  LinearProgressIndicator(
                    value: p.total.inMilliseconds == 0 ? 0 : (p.pos.inMilliseconds / p.total.inMilliseconds).clamp(0, 1).toDouble(),
                    minHeight: 3, backgroundColor: kLine, color: kGold,
                  ),
              ]),
            ),
          );
        },
      );
}
