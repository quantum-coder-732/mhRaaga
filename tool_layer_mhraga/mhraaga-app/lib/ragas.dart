import 'package:flutter/material.dart';
import 'api.dart';
import 'main.dart' show composeRaga;
import 'player.dart';
import 'ui.dart';

class RagasScreen extends StatefulWidget {
  const RagasScreen({super.key});
  @override
  State<RagasScreen> createState() => _RagasScreenState();
}

class _RagasScreenState extends State<RagasScreen> {
  late final Future<Map<String, dynamic>> f = Api.call('GET', '/ragas', auth: false).then((d) => Map<String, dynamic>.from(d));
  String q = '', time = '';
  final num = TextEditingController(text: '108');

  void _open(String spec) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => RagaDetail(spec: spec)));

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 3,
        child: Column(children: [
          const TabBar(
            indicatorColor: kGold, labelColor: kGold, unselectedLabelColor: kMute, dividerColor: kLine,
            tabs: [Tab(text: 'Classical'), Tab(text: 'Gopī'), Tab(text: 'Melakartas')],
          ),
          Expanded(
            child: FutureBuilder<Map<String, dynamic>>(
              future: f,
              builder: (c, snap) {
                if (snap.hasError) return Center(child: Text('${snap.error}', style: const TextStyle(color: kRose)));
                if (!snap.hasData) return const Center(child: CircularProgressIndicator());
                final cl = List<Map<String, dynamic>>.from((snap.data!['classical'] as List).map((e) => Map<String, dynamic>.from(e)));
                final mela = List<Map<String, dynamic>>.from((snap.data!['melakartas'] as List).map((e) => Map<String, dynamic>.from(e)));
                final times = {for (final r in cl) r['time'] as String};
                final shown = [for (final r in cl) if ((time.isEmpty || r['time'] == time) && (q.isEmpty || '${r['name']} ${r['mood']} ${r['time']}'.toLowerCase().contains(q.toLowerCase()))) r];
                return TabBarView(children: [
                  ListView(padding: const EdgeInsets.fromLTRB(16, 12, 16, 20), children: [
                    TextField(onChanged: (v) => setState(() => q = v), decoration: const InputDecoration(prefixIcon: Icon(Icons.search, color: kMute), hintText: 'Search a raga…')),
                    const SizedBox(height: 10),
                    SizedBox(height: 38, child: ListView(scrollDirection: Axis.horizontal, children: [
                      for (final t in ['', ...times])
                        Padding(padding: const EdgeInsets.only(right: 8), child: ChoiceChip(label: Text(t.isEmpty ? 'All' : t), selected: time == t, selectedColor: kGold, labelStyle: TextStyle(color: time == t ? const Color(0xFF1A1033) : kMute), onSelected: (_) => setState(() => time = t))),
                    ])),
                    const SizedBox(height: 10),
                    for (final r in shown)
                      Padding(padding: const EdgeInsets.only(bottom: 10), child: Glass(
                        onTap: () => _open(r['name']), padding: const EdgeInsets.all(14),
                        child: Row(children: [
                          OmBadge(size: 44, text: (r['name'] as String).substring(0, 1)),
                          const SizedBox(width: 14),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(r['name'], style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                            Text('${r['time']} · ${r['mood']}', style: const TextStyle(color: kMute, fontSize: 12)),
                          ])),
                          const Icon(Icons.chevron_right, color: kMute),
                        ]),
                      )),
                  ]),
                  ListView(padding: const EdgeInsets.all(16), children: [
                    Glass(glow: true, padding: const EdgeInsets.all(18), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      const Text('Krishna\'s sixteen thousand', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      const Text('One flute, a raga for every heart. Pick any number from 1 to 16,000.', style: TextStyle(color: kMute)),
                      const SizedBox(height: 14),
                      TextField(controller: num, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Gopī number')),
                      const SizedBox(height: 12),
                      Row(children: [
                        Expanded(child: FilledButton(onPressed: () => _open('gopi:${(int.tryParse(num.text) ?? 1).clamp(1, 16000)}'), child: const Text('Show'))),
                        const SizedBox(width: 10),
                        OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(minimumSize: const Size(0, 50), side: const BorderSide(color: kLine), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                          onPressed: () {
                            final n = 1 + DateTime.now().microsecondsSinceEpoch % 16000;
                            num.text = '$n';
                            _open('gopi:$n');
                          },
                          icon: const Icon(Icons.casino_outlined, color: kGold), label: const Text('Random', style: TextStyle(color: kInk)),
                        ),
                      ]),
                    ])),
                  ]),
                  GridView.count(
                    padding: const EdgeInsets.all(16), crossAxisCount: 2, mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 2.6,
                    children: [for (final m in mela) Glass(onTap: () => _open('mela:${m['number']}'), padding: const EdgeInsets.symmetric(horizontal: 12), child: Align(alignment: Alignment.centerLeft, child: Text('${m['number']}. ${m['name']}', maxLines: 1, overflow: TextOverflow.ellipsis)))],
                  ),
                ]);
              },
            ),
          ),
        ]),
      );
}

class RagaDetail extends StatefulWidget {
  const RagaDetail({super.key, required this.spec});
  final String spec;
  @override
  State<RagaDetail> createState() => _RagaDetailState();
}

class _RagaDetailState extends State<RagaDetail> {
  late final Future<Map<String, dynamic>> f = Api.call('GET', '/ragas/${Uri.encodeComponent(widget.spec)}', auth: false).then((d) => Map<String, dynamic>.from(d));
  double sa = 233;
  String _n(int n) => kSvara[((n % 12) + 12) % 12] + (n < 0 ? '·' : n >= 12 ? '′' : '');

  @override
  void dispose() {
    if (Player.i.previewing != null) Player.i.preview(Player.i.previewing!, {}, 0);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Night(
          child: SafeArea(
            child: FutureBuilder<Map<String, dynamic>>(
              future: f,
              builder: (c, snap) {
                if (snap.hasError) return Center(child: Text('${snap.error}', style: const TextStyle(color: kRose)));
                if (!snap.hasData) return const Center(child: CircularProgressIndicator());
                final r = snap.data!;
                final aroha = [for (final x in r['aroha']) (x as num).toInt()], avaroha = [for (final x in r['avaroha']) (x as num).toInt()], pakad = [for (final x in r['pakad']) (x as num).toInt()];
                final used = {for (final n in [...aroha, ...avaroha]) ((n % 12) + 12) % 12};
                final vadi = (r['vadi'] as num).toInt(), sam = (r['samvadi'] as num).toInt();
                if (r['tonic'] != null && [183, 233, 234].contains((r['tonic'] as num).round()) && sa == 233) sa = (r['tonic'] as num).round().toDouble();
                return ListenableBuilder(
                  listenable: Player.i,
                  builder: (c, _) => ListView(padding: const EdgeInsets.fromLTRB(20, 4, 20, 28), children: [
                    Row(children: [IconButton(onPressed: () => Navigator.pop(c), icon: const Icon(Icons.arrow_back_rounded))]),
                    Text(r['name'], style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 8),
                    Wrap(spacing: 6, runSpacing: 6, children: [Chipx('${r['time']}', gold: true), Chipx('${r['mood']}'), Chipx('${r['tala']}'), if (r['melakarta_names'] != null) Chipx((r['melakarta_names'] as List).join(' → '))]),
                    const SizedBox(height: 18),
                    Ladder(used: used, vadi: vadi, samvadi: sam),
                    const SizedBox(height: 8),
                    const Text('red: vādī (king)   gold: samvādī (minister)   blue: other notes', style: TextStyle(color: kMute, fontSize: 12)),
                    const SizedBox(height: 18),
                    Glass(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      _kv('Aroha', aroha.map(_n).join(' ')), _kv('Avaroha', avaroha.map(_n).join(' ')),
                      _kv('Vādī · Samvādī', '${kSvara[vadi]} · ${kSvara[sam]}  (${((sam - vadi) % 12 + 12) % 12} semitones)'), _kv('Pakaḍ', pakad.map(_n).join(' ')),
                    ])),
                    const SizedBox(height: 18),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: () => Player.i.preview(widget.spec, r, sa),
                      icon: Icon(Player.i.previewing == widget.spec ? Icons.stop_rounded : Icons.play_arrow_rounded),
                      label: Text(Player.i.previewing == widget.spec ? 'Playing… tap to stop' : 'Listen to the raga'),
                    ),
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(minimumSize: const Size(0, 50), side: const BorderSide(color: kGold), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                      onPressed: () {
                        composeRaga.value = widget.spec;
                        Navigator.pop(c);
                      },
                      icon: const Icon(Icons.auto_awesome, color: kGold), label: const Text('Compose in this raga', style: TextStyle(color: kGold)),
                    ),
                  ]),
                );
              },
            ),
          ),
        ),
      );

  Widget _kv(String k, String v) => Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(k, style: const TextStyle(color: kMute, fontSize: 12)), Text(v, style: const TextStyle(fontSize: 16, letterSpacing: .5))]));
}
