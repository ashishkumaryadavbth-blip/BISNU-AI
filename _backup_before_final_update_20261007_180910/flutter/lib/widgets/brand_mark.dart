import 'package:flutter/material.dart';

class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 48, this.compact = false});

  final double size;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(size * 0.3),
            gradient: const LinearGradient(colors: [
              Color(0xFF42DEE8),
              Color(0xFF648BFF),
              Color(0xFF9874EF)
            ]),
            boxShadow: [
              BoxShadow(
                  color: const Color(0xFF42DEE8).withValues(alpha: 0.24),
                  blurRadius: size * 0.6)
            ],
          ),
          child: Text('B',
              style: TextStyle(
                  color: const Color(0xFF071014),
                  fontSize: size * 0.63,
                  fontWeight: FontWeight.w800)),
        ),
        if (!compact) ...[
          const SizedBox(width: 10),
          Text.rich(TextSpan(children: [
            const TextSpan(
                text: 'BISNU', style: TextStyle(fontWeight: FontWeight.w700)),
            TextSpan(
                text: '-X',
                style: TextStyle(
                    color: Theme.of(context).colorScheme.primary,
                    fontWeight: FontWeight.w700)),
            const TextSpan(
                text: '.1',
                style: TextStyle(
                    color: Color(0xFFE7C477), fontWeight: FontWeight.w700)),
          ])),
        ],
      ],
    );
  }
}
