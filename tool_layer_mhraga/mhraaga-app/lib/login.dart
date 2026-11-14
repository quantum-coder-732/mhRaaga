import 'package:flutter/material.dart';
import 'api.dart';
import 'ui.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.onDone});
  final VoidCallback onDone;
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final name = TextEditingController(), email = TextEditingController(), pass = TextEditingController();
  bool signup = false, busy = false, hide = true;
  String? err;

  Future<void> _go() async {
    setState(() {
      busy = true;
      err = null;
    });
    try {
      signup ? await Api.signup(name.text.trim(), email.text.trim(), pass.text) : await Api.login(email.text.trim(), pass.text);
      widget.onDone();
    } catch (e) {
      setState(() => err = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(22),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const OmBadge(size: 84),
                  const SizedBox(height: 14),
                  const Text('mhRaaga', style: TextStyle(fontSize: 34, fontWeight: FontWeight.w800, letterSpacing: .4)),
                  const SizedBox(height: 4),
                  const Text('Sixteen thousand ragas, one flute.', style: TextStyle(color: kMute)),
                  const SizedBox(height: 26),
                  Glass(
                    padding: const EdgeInsets.all(20),
                    child: AutofillGroup(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        SegmentedButton<bool>(
                          showSelectedIcon: false,
                          segments: const [ButtonSegment(value: false, label: Text('Sign in')), ButtonSegment(value: true, label: Text('Create account'))],
                          selected: {signup},
                          onSelectionChanged: (s) => setState(() {
                            signup = s.first;
                            err = null;
                          }),
                        ),
                        const SizedBox(height: 16),
                        if (signup) ...[
                          TextField(controller: name, textCapitalization: TextCapitalization.words, autofillHints: const [AutofillHints.name], decoration: const InputDecoration(labelText: 'Name')),
                          const SizedBox(height: 12),
                        ],
                        TextField(controller: email, keyboardType: TextInputType.emailAddress, autofillHints: const [AutofillHints.email], decoration: const InputDecoration(labelText: 'Email')),
                        const SizedBox(height: 12),
                        TextField(
                          controller: pass, obscureText: hide, autofillHints: const [AutofillHints.password], onSubmitted: (_) => _go(),
                          decoration: InputDecoration(labelText: 'Password', suffixIcon: IconButton(icon: Icon(hide ? Icons.visibility_off : Icons.visibility, color: kMute), onPressed: () => setState(() => hide = !hide))),
                        ),
                        if (err != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(err!, style: const TextStyle(color: kRose))),
                        const SizedBox(height: 18),
                        FilledButton(onPressed: busy ? null : _go, child: busy ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4)) : Text(signup ? 'Create account' : 'Sign in')),
                      ]),
                    ),
                  ),
                ]),
              ),
            ),
          ),
        ),
      );
}
