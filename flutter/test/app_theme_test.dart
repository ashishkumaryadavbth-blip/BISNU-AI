import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bisnu_x_mobile/theme/app_theme.dart';

void main() {
  test('BISNU-X theme exposes the branded accent palette', () {
    final theme = AppTheme.dark(AppTheme.cyan, ThemeData.dark().textTheme);

    expect(theme.useMaterial3, isTrue);
    expect(theme.colorScheme.primary, AppTheme.cyan);
    expect(theme.colorScheme.secondary, AppTheme.violet);
  });
}
