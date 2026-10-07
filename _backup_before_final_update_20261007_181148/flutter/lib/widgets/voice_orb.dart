import 'package:flutter/material.dart';

class VoiceOrb extends StatefulWidget {
  const VoiceOrb({super.key, required this.active});

  final bool active;

  @override
  State<VoiceOrb> createState() => _VoiceOrbState();
}

class _VoiceOrbState extends State<VoiceOrb>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1900))
    ..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final pulse = widget.active ? _controller.value : 0.18;
        return Container(
          width: 224,
          height: 224,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(colors: [
              const Color(0xFF76EEEC).withValues(alpha: 0.18 + pulse * 0.12),
              Colors.transparent
            ], stops: const [
              0.6,
              1
            ]),
          ),
          child: Container(
            width: 154 + pulse * 13,
            height: 154 + pulse * 13,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0xFF53E4E5),
                    Color(0xFF668DFF),
                    Color(0xFF9A75F2)
                  ]),
              boxShadow: [
                BoxShadow(
                    color: const Color(0xFF55DDE8)
                        .withValues(alpha: 0.2 + pulse * 0.2),
                    blurRadius: 36 + pulse * 20,
                    spreadRadius: 2 + pulse * 5)
              ],
            ),
            child: Icon(
                widget.active
                    ? Icons.graphic_eq_rounded
                    : Icons.auto_awesome_rounded,
                size: 48,
                color: const Color(0xFF081216)),
          ),
        );
      },
    );
  }
}
