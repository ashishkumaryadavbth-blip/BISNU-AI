import 'package:flutter/material.dart';

class AppTheme {
  static const Color ink = Color(0xFF080D13);
  static const Color panel = Color(0xFF101923);
  static const Color cyan = Color(0xFF43E4E8);
  static const Color blue = Color(0xFF5793FF);
  static const Color violet = Color(0xFF9A77F7);
  static const Color emerald = Color(0xFF50D6A2);
  static const Color gold = Color(0xFFE7C477);

  static ThemeData dark(Color accent, TextTheme textTheme) => _theme(
        accent,
        textTheme,
        Brightness.dark,
        const Color(0xFF090E14),
        const Color(0xFFF1F5F8),
      );

  static ThemeData light(Color accent, TextTheme textTheme) => _theme(
        accent,
        textTheme,
        Brightness.light,
        const Color(0xFFF2F7F8),
        const Color(0xFF132128),
      );

  static ThemeData _theme(Color accent, TextTheme textTheme,
      Brightness brightness, Color background, Color foreground) {
    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: brightness,
      surface: brightness == Brightness.dark ? panel : Colors.white,
      primary: accent,
      secondary: violet,
      tertiary: emerald,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      textTheme:
          textTheme.apply(bodyColor: foreground, displayColor: foreground),
      appBarTheme: AppBarTheme(
          backgroundColor: background,
          foregroundColor: foreground,
          elevation: 0),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: brightness == Brightness.dark
            ? Colors.white.withValues(alpha: 0.045)
            : Colors.black.withValues(alpha: 0.035),
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: BorderSide.none),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      cardTheme: CardThemeData(
        color: brightness == Brightness.dark
            ? panel.withValues(alpha: 0.88)
            : Colors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      ),
    );
  }
}
