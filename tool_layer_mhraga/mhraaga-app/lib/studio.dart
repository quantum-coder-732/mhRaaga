import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'api.dart';
import 'ui.dart';

/// Studio tab: the site's one page (stories, pravachan, People, Film studio, rules) inside the app.
class StudioScreen extends StatefulWidget {
  const StudioScreen({super.key});
  @override
  State<StudioScreen> createState() => _StudioScreenState();
}

class _StudioScreenState extends State<StudioScreen> with AutomaticKeepAliveClientMixin {
  late final WebViewController c;
  int progress = 0;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    c = WebViewController(onPermissionRequest: (r) => r.grant())
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(kBg)
      ..setNavigationDelegate(NavigationDelegate(
        onProgress: (p) => setState(() => progress = p),
        onNavigationRequest: (r) => r.url.startsWith(kBase) ? NavigationDecision.navigate : NavigationDecision.prevent,
        onPageFinished: (_) {
          // hand the app's session to the page, so it opens already signed in
          final t = Api.token;
          if (t != null) c.runJavaScript('try{if(!localStorage.getItem("mh_token")){localStorage.setItem("mh_token",${_js(t)});location.reload();}}catch(e){}');
        },
      ))
      ..loadRequest(Uri.parse('$kBase/?app=1#film'));
  }

  String _js(String s) => '"${s.replaceAll(r'\', r'\\').replaceAll('"', r'\"')}"';

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Stack(children: [
      WebViewWidget(controller: c),
      if (progress < 100) LinearProgressIndicator(value: progress / 100, color: kGold, backgroundColor: kBg2),
    ]);
  }
}
