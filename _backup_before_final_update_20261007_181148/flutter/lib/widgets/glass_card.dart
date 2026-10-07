import 'package:flutter/material.dart';

class GlassCard extends StatelessWidget {
  const GlassCard(
      {super.key,
      required this.child,
      this.padding = const EdgeInsets.all(18),
      this.radius = 20});

  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: dark
            ? Colors.white.withValues(alpha: 0.055)
            : Colors.white.withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
            color: dark
                ? Colors.white.withValues(alpha: 0.09)
                : Colors.black.withValues(alpha: 0.06)),
      ),
      child: child,
    );
  }
}

class GradientButton extends StatelessWidget {
  const GradientButton(
      {super.key,
      required this.label,
      required this.onPressed,
      this.icon,
      this.busy = false});

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(15),
        gradient: LinearGradient(colors: [
          Theme.of(context).colorScheme.primary,
          const Color(0xFF6687F3)
        ]),
      ),
      child: FilledButton.icon(
        onPressed: busy ? null : onPressed,
        icon: busy
            ? const SizedBox.square(
                dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
            : Icon(icon ?? Icons.arrow_forward_rounded),
        label: Text(label),
        style: FilledButton.styleFrom(
          backgroundColor: Colors.transparent,
          disabledBackgroundColor: Colors.transparent,
          shadowColor: Colors.transparent,
          minimumSize: const Size.fromHeight(54),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
        ),
      ),
    );
  }
}
