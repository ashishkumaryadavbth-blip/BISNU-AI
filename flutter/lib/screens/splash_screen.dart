import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/animated_background.dart';
import '../widgets/brand_mark.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key, required this.api});

  final ApiService api;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 2100))
    ..forward();
  late final Animation<double> _fade =
      CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);
  late final Animation<double> _scale = Tween(begin: 0.78, end: 1.0)
      .animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutBack));

  @override
  void initState() {
    super.initState();
    _routeAfterSplash();
  }

  Future<void> _routeAfterSplash() async {
    await Future<void>.delayed(const Duration(milliseconds: 2200));
    if (!mounted) return;
    final session = await widget.api.token;
    if (session == null) {
      Navigator.of(context).pushReplacementNamed('/login');
      return;
    }
    try {
      final profile = await widget.api.getProfile();
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed('/chat', arguments: profile);
    } catch (_) {
      await widget.api.signOut();
      if (mounted) Navigator.of(context).pushReplacementNamed('/login');
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AnimatedBackground(
        particles: true,
        child: Center(
          child: FadeTransition(
            opacity: _fade,
            child: ScaleTransition(
              scale: _scale,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const BrandMark(size: 82),
                  const SizedBox(height: 26),
                  Text('INTELLIGENCE, IN YOUR HANDS',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          letterSpacing: 2.2, color: Colors.white70)),
                  const SizedBox(height: 30),
                  SizedBox(
                      width: 118,
                      child: LinearProgressIndicator(
                          value: _controller.value,
                          minHeight: 2,
                          color: Theme.of(context).colorScheme.primary,
                          backgroundColor: Colors.white12)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
