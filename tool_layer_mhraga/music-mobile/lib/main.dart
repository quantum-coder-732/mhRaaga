import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api.dart';

void main() => runApp(const AlgoMusicApp());

class AlgoMusicApp extends StatelessWidget {
  const AlgoMusicApp({super.key, this.api});
  final MusicApi? api;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'aRaaga',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: const Color(0xFF0D0A22),
          colorScheme: const ColorScheme.dark(primary: Color(0xFFFFA63D), secondary: Color(0xFFE0457B), surface: Color(0xFF1A1540)),
          useMaterial3: true,
        ),
        home: Gate(api: api ?? MusicApi()),
      );
}

Color _hue(String s, [int shift = 0]) {
  var h = 0;
  for (final c in s.codeUnits) {
    h = (h * 31 + c) % 360;
  }
  return HSLColor.fromAHSL(1, ((h + shift) % 360).toDouble(), 0.7, shift == 0 ? 0.45 : 0.3).toColor();
}

BoxDecoration coverDecoration(Track t, {double radius = 12}) => BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [_hue(t.title), _hue(t.title, 70)]),
    );

String fmt(num s) => '${s ~/ 60}:${(s % 60).floor().toString().padLeft(2, '0')}';

/// Shows the sign-in screen until there is a valid session, then the studio.
class Gate extends StatefulWidget {
  const Gate({super.key, required this.api});
  final MusicApi api;
  @override
  State<Gate> createState() => _GateState();
}

class _GateState extends State<Gate> {
  bool? _in;

  @override
  void initState() {
    super.initState();
    widget.api.restore().then((ok) => mounted ? setState(() => _in = ok) : null).catchError((_) => mounted ? setState(() => _in = false) : null);
  }

  @override
  Widget build(BuildContext context) {
    if (_in == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (_in == false) return SignInScreen(api: widget.api, onDone: () => setState(() => _in = true));
    return Home(api: widget.api, onSignOut: () async {
      await widget.api.signOut();
      if (mounted) setState(() => _in = false);
    });
  }
}

class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key, required this.api, required this.onDone});
  final MusicApi api;
  final VoidCallback onDone;
  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _name = TextEditingController(), _email = TextEditingController(), _pw = TextEditingController();
  bool _up = false, _busy = false;
  String _error = '';

  Future<void> _submit() async {
    setState(() { _busy = true; _error = ''; });
    try {
      _up ? await widget.api.signUp(_name.text.trim(), _email.text.trim(), _pw.text) : await widget.api.signIn(_email.text.trim(), _pw.text);
      widget.onDone();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Container(
          decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF2B1C63), Color(0xFF0D0A22)])),
          child: SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 400),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    const Icon(Icons.music_note_rounded, size: 52, color: Color(0xFFFFA63D)),
                    const SizedBox(height: 8),
                    const Text('aRaaga', textAlign: TextAlign.center, style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800, color: Color(0xFFFFA63D))),
                    const Text('Songs, ragas and bhajans from a prompt', textAlign: TextAlign.center, style: TextStyle(color: Colors.white60)),
                    const SizedBox(height: 28),
                    Text(_up ? 'Create your account' : 'Sign in', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 14),
                    if (_up) ...[
                      TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name', border: OutlineInputBorder())),
                      const SizedBox(height: 12),
                    ],
                    TextField(controller: _email, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder())),
                    const SizedBox(height: 12),
                    TextField(controller: _pw, obscureText: true, onSubmitted: (_) => _submit(),
                        decoration: InputDecoration(labelText: 'Password', helperText: _up ? 'At least 8 characters' : null, border: const OutlineInputBorder())),
                    if (_error.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error, style: const TextStyle(color: Colors.redAccent))),
                    const SizedBox(height: 16),
                    FilledButton(onPressed: _busy ? null : _submit, child: Padding(padding: const EdgeInsets.all(12), child: Text(_busy ? 'Please wait…' : _up ? 'Create account' : 'Sign in'))),
                    TextButton(onPressed: () => setState(() { _up = !_up; _error = ''; }), child: Text(_up ? 'Already have an account? Sign in' : 'New here? Create an account')),
                  ]),
                ),
              ),
            ),
          ),
        ),
      );
}

class Home extends StatefulWidget {
  const Home({super.key, required this.api, required this.onSignOut});
  final MusicApi api;
  final VoidCallback onSignOut;
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  final _player = AudioPlayer();
  int _tab = 0;
  Track? _current;

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _play(Track t) async {
    if (_current?.id == t.id) {
      _player.playing ? await _player.pause() : await _player.play();
      return;
    }
    setState(() => _current = t);
    try {
      await _player.setUrl(t.audioUrl);
      _player.play();
      widget.api.countPlay(t.id).catchError((_) => t);
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not play this track')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      TrackList(key: const ValueKey('discover'), api: widget.api, discover: true, onPlay: _play, player: _player, current: _current),
      Create(api: widget.api, onDone: (t) {
        setState(() => _tab = 2);
        _play(t);
      }),
      TrackList(key: const ValueKey('mine'), api: widget.api, discover: false, onPlay: _play, player: _player, current: _current),
    ];
    return Scaffold(
      appBar: AppBar(title: const Text('aRaaga', style: TextStyle(fontWeight: FontWeight.w800, color: Color(0xFFFFA63D))), backgroundColor: Colors.transparent, actions: [
        IconButton(tooltip: 'Sign out (${widget.api.name})', icon: const Icon(Icons.logout), onPressed: widget.onSignOut),
      ]),
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: Column(mainAxisSize: MainAxisSize.min, children: [
        if (_current != null) MiniPlayer(track: _current!, player: _player),
        NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.explore_outlined), label: 'Discover'),
            NavigationDestination(icon: Icon(Icons.add_circle_outline), label: 'Create'),
            NavigationDestination(icon: Icon(Icons.library_music_outlined), label: 'Library'),
          ],
        ),
      ]),
    );
  }
}

class TrackList extends StatefulWidget {
  const TrackList({super.key, required this.api, required this.discover, required this.onPlay, required this.player, required this.current});
  final MusicApi api;
  final bool discover;
  final Future<void> Function(Track) onPlay;
  final AudioPlayer player;
  final Track? current;
  @override
  State<TrackList> createState() => _TrackListState();
}

class _TrackListState extends State<TrackList> {
  static const genres = ['bhajan', 'raga', 'devotional', 'ghazal', 'classical', 'folk', 'lofi', 'pop', 'ambient', 'cinematic'];
  List<Track> _tracks = [];
  String _sort = 'trending', _genre = '', _q = '';
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final t = await widget.api.tracks(
        sort: widget.discover ? _sort : 'new', genre: widget.discover ? _genre : '', q: widget.discover ? _q : '', mine: !widget.discover);
      if (mounted) setState(() { _tracks = t; _error = null; });
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not reach the music server ($musicBase).');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _like(Track t) async {
    final u = await widget.api.like(t.id);
    setState(() => _tracks = [for (final x in _tracks) x.id == u.id ? u : x]);
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 16), children: [
          if (widget.discover) ...[
            TextField(
              decoration: const InputDecoration(hintText: 'Search songs, ragas, moods', prefixIcon: Icon(Icons.search), border: OutlineInputBorder()),
              onSubmitted: (v) { _q = v.trim(); _load(); },
            ),
            const SizedBox(height: 10),
            SingleChildScrollView(scrollDirection: Axis.horizontal, child: Row(children: [
              for (final s in ['trending', 'new', 'top']) _chip(s, _sort == s, () { _sort = s; _load(); }),
              const SizedBox(width: 8),
              for (final g in genres) _chip(g, _genre == g, () { _genre = _genre == g ? '' : g; _load(); }),
            ])),
          ],
          if (_loading) const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator())),
          if (_error != null) Padding(padding: const EdgeInsets.all(16), child: Text(_error!, style: const TextStyle(color: Colors.redAccent))),
          if (!_loading && _error == null && _tracks.isEmpty)
            const Padding(padding: EdgeInsets.all(24), child: Text('Nothing here yet.', style: TextStyle(color: Colors.white54))),
          for (final t in _tracks) _tile(t),
        ]),
      );

  Widget _chip(String label, bool on, VoidCallback tap) => Padding(
        padding: const EdgeInsets.only(right: 6),
        child: ChoiceChip(label: Text(label), selected: on, onSelected: (_) => tap()),
      );

  Widget _tile(Track t) => ListTile(
        contentPadding: EdgeInsets.zero,
        onTap: () => widget.onPlay(t),
        leading: Container(width: 52, height: 52, decoration: coverDecoration(t, radius: 10),
            child: Icon(widget.current?.id == t.id ? Icons.graphic_eq : Icons.play_arrow, color: Colors.white)),
        title: Text(t.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text('${t.tags}\n${fmt(t.durationSeconds)} · ${t.plays} plays', style: const TextStyle(fontSize: 12)),
        isThreeLine: true,
        trailing: TextButton.icon(
          onPressed: () => _like(t),
          icon: Icon(t.liked ? Icons.favorite : Icons.favorite_border, color: t.liked ? Colors.pinkAccent : Colors.white54, size: 18),
          label: Text('${t.likes}'),
        ),
      );
}

class Create extends StatefulWidget {
  const Create({super.key, required this.api, required this.onDone});
  final MusicApi api;
  final void Function(Track) onDone;
  @override
  State<Create> createState() => _CreateState();
}

class _CreateState extends State<Create> {
  final _prompt = TextEditingController(), _lyrics = TextEditingController();
  bool _instrumental = false, _busy = false;
  double _duration = 60;
  String _status = '', _error = '';
  static const examples = [
    'A calm Yaman raga with flute and tabla',
    'Dawn Bhairav raga, meditative, sitar and tanpura',
    'Lofi study beat, rainy night, soft piano',
  ];

  Future<void> _submit() async {
    setState(() { _busy = true; _error = ''; _status = 'Queued…'; });
    try {
      final id = await widget.api.generate(_prompt.text.trim(), lyrics: _lyrics.text, instrumental: _instrumental, duration: _duration.round());
      final t = await widget.api.waitForJob(id, onStatus: (s) {
        if (mounted) setState(() => _status = s == 'PROCESSING' ? 'Composing and rendering…' : 'Queued…');
      });
      widget.onDone(t);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        TextField(controller: _prompt, maxLines: 3, maxLength: 1000, onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(labelText: 'Describe your song, raga or bhajan', border: OutlineInputBorder())),
        Wrap(spacing: 6, children: [for (final e in examples) ActionChip(label: Text(e, style: const TextStyle(fontSize: 12)), onPressed: () => setState(() => _prompt.text = e))]),
        const SizedBox(height: 12),
        TextField(controller: _lyrics, maxLines: 3, enabled: !_instrumental,
            decoration: const InputDecoration(labelText: 'Lyrics (optional)', border: OutlineInputBorder())),
        const SizedBox(height: 8),
        Text('Length: ${_duration.round()}s'),
        Slider(value: _duration, min: 20, max: 180, divisions: 16, onChanged: (v) => setState(() => _duration = v)),
        SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Instrumental'), value: _instrumental, onChanged: (v) => setState(() => _instrumental = v)),
        FilledButton(onPressed: _busy || _prompt.text.trim().length < 3 ? null : _submit, child: const Text('Create')),
        if (_busy) Padding(padding: const EdgeInsets.only(top: 12), child: Row(children: [const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)), const SizedBox(width: 10), Text(_status)])),
        if (_error.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error, style: const TextStyle(color: Colors.redAccent))),
        const Padding(padding: EdgeInsets.only(top: 12), child: Text('Rendered by an offline raga synthesizer: it plays the raga and taal but does not sing the lyrics.', style: TextStyle(color: Colors.white54, fontSize: 12))),
      ]);
}

class MiniPlayer extends StatelessWidget {
  const MiniPlayer({super.key, required this.track, required this.player});
  final Track track;
  final AudioPlayer player;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surface,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          StreamBuilder<Duration>(
            stream: player.positionStream,
            builder: (_, snap) {
              final pos = snap.data ?? Duration.zero;
              final total = (player.duration ?? Duration(seconds: track.durationSeconds)).inMilliseconds;
              return LinearProgressIndicator(value: total == 0 ? 0 : (pos.inMilliseconds / total).clamp(0, 1).toDouble(), minHeight: 2);
            },
          ),
          ListTile(
            dense: true,
            leading: Container(width: 40, height: 40, decoration: coverDecoration(track, radius: 8)),
            title: Text(track.title, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(track.tags, maxLines: 1),
            trailing: StreamBuilder<bool>(
              stream: player.playingStream,
              builder: (_, snap) => IconButton(
                icon: Icon(snap.data == true ? Icons.pause_circle_filled : Icons.play_circle_fill, size: 36),
                onPressed: () => snap.data == true ? player.pause() : player.play(),
              ),
            ),
          ),
        ]),
      );
}
