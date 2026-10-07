import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../lib/main.dart';

void main() {
  testWidgets('BISNU-X builds', (tester) async {
    await tester.pumpWidget(const BisnuXApp());
    expect(find.byType(BisnuXApp), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 3));
  });
}
