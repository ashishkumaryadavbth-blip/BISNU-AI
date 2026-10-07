import 'dart:math' as math;

import 'package:flutter/material.dart';

class AnimatedBackground extends StatefulWidget {
  const AnimatedBackground({super.key, this.child, this.particles = false});

  final Widget? child;
  final bool particles;

  @override
  State<AnimatedBackground> createState() => _AnimatedBackgroundState();
}

class _AnimatedBackgroundState extends State<AnimatedBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 12),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Theme.of(context).scaffoldBackgroundColor,
                const Color(0xFF111827),
                const Color(0xFF081317)
              ],
            ),
          ),
        ),
        if (widget.particles)
          AnimatedBuilder(
            animation: _controller,
            builder: (context, _) =>
                CustomPaint(painter: _ParticlePainter(_controller.value)),
          ),
        if (widget.child != null) widget.child!,
      ],
    );
  }
}

class _ParticlePainter extends CustomPainter {
  _ParticlePainter(this.progress);

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..strokeWidth = 1;
    const points = 42;
    final positions = <Offset>[];
    for (var index = 0; index < points; index++) {
      final seed = index * 17.31;
      final x = (math.sin(seed * 2.7) * 0.5 + 0.5) * size.width;
      final phase = (progress + index / points) % 1;
      final y = size.height * (1 - phase);
      positions.add(Offset(x, y));
      paint.color =
          const Color(0xFF71E9EA).withValues(alpha: 0.12 + (index % 4) * 0.035);
      canvas.drawCircle(Offset(x, y), index % 7 == 0 ? 2.1 : 1.1, paint);
    }
    paint.color = const Color(0xFF7898FF).withValues(alpha: 0.09);
    for (var first = 0; first < positions.length; first++) {
      for (var second = first + 1; second < positions.length; second++) {
        if ((positions[first] - positions[second]).distance < 72) {
          canvas.drawLine(positions[first], positions[second], paint);
        }
      }
    }
  }

  @override
  bool shouldRepaint(covariant _ParticlePainter oldDelegate) =>
      oldDelegate.progress != progress;
}
