import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/animated_background.dart';
import '../widgets/brand_mark.dart';
import '../widgets/glass_card.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api});

  final ApiService api;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _creatingAccount = true;
  bool _obscurePassword = true;
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    final username = _usernameController.text.trim().toLowerCase();
    final password = _passwordController.text;
    if (!RegExp(r'^[a-zA-Z0-9_]{3,32}$').hasMatch(username)) {
      setState(() => _error =
          'Username must be 3–32 characters using letters, numbers, or _.');
      return;
    }
    if ((_creatingAccount && password.length < 10) ||
        password.length > 128 ||
        password.isEmpty) {
      setState(() => _error = _creatingAccount
          ? 'Password must be 10–128 characters.'
          : 'Enter your password.');
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_creatingAccount) {
        await widget.api.register(username, password);
      } else {
        await widget.api.login(username, password);
      }
      final profile = await widget.api.getProfile();
      if (!mounted) return;
      Navigator.pushReplacementNamed(
        context,
        '/chat',
        arguments: profile,
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      body: AnimatedBackground(
        particles: true,
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const BrandMark(size: 70),
                    const SizedBox(height: 30),
                    const Text(
                      'BISNU-X.1',
                      style: TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _creatingAccount
                          ? 'Create your free account'
                          : 'Welcome back',
                    ),
                    const SizedBox(height: 30),
                    GlassCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          SegmentedButton<bool>(
                            segments: const [
                              ButtonSegment(
                                value: true,
                                label: Text('Create account'),
                              ),
                              ButtonSegment(
                                value: false,
                                label: Text('Log in'),
                              ),
                            ],
                            selected: {_creatingAccount},
                            onSelectionChanged: _busy
                                ? null
                                : (selection) => setState(() {
                                      _creatingAccount = selection.first;
                                      _error = null;
                                    }),
                          ),
                          const SizedBox(height: 20),
                          TextField(
                            controller: _usernameController,
                            enabled: !_busy,
                            autocorrect: false,
                            textCapitalization: TextCapitalization.none,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: 'BISNU-X username',
                              suffixText: '#bisnu-x.com',
                              prefixIcon: Icon(Icons.alternate_email),
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _passwordController,
                            enabled: !_busy,
                            obscureText: _obscurePassword,
                            autocorrect: false,
                            enableSuggestions: false,
                            textInputAction: TextInputAction.done,
                            onSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline),
                              suffixIcon: IconButton(
                                tooltip: _obscurePassword
                                    ? 'Show password'
                                    : 'Hide password',
                                onPressed: () => setState(
                                  () => _obscurePassword = !_obscurePassword,
                                ),
                                icon: Icon(
                                  _obscurePassword
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined,
                                ),
                              ),
                            ),
                          ),
                          if (_creatingAccount) ...[
                            const SizedBox(height: 10),
                            Text(
                              'Your account ID will be username#bisnu-x.com. This is not an email inbox. Google sign-in and password recovery are not available. Use a password with at least 10 characters and keep it safe.',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ],
                          if (_error case final error?) ...[
                            const SizedBox(height: 14),
                            Text(
                              error,
                              textAlign: TextAlign.center,
                              style: TextStyle(color: colors.error),
                            ),
                          ],
                          const SizedBox(height: 18),
                          SizedBox(
                            height: 52,
                            child: FilledButton(
                              onPressed: _busy ? null : _submit,
                              child: _busy
                                  ? const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : Text(
                                      _creatingAccount
                                          ? 'Create free account'
                                          : 'Log in',
                                    ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
