import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'screens/chat_screen.dart';
import 'screens/login_screen.dart';
import 'screens/splash_screen.dart';
import 'services/api_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BisnuXApp());
}

class BisnuXApp extends StatefulWidget {
  const BisnuXApp({super.key});

  @override
  State<BisnuXApp> createState() => _BisnuXAppState();
}

class _BisnuXAppState extends State<BisnuXApp> {
  final ApiService api = ApiService();

  ThemeMode themeMode = ThemeMode.dark;
  Color accent = AppTheme.cyan;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BISNU-X.1',
      debugShowCheckedModeBanner: false,
      themeMode: themeMode,

      theme: AppTheme.light(
        accent,
        GoogleFonts.spaceGroteskTextTheme(),
      ),

      darkTheme: AppTheme.dark(
        accent,
        GoogleFonts.spaceGroteskTextTheme(
          ThemeData.dark().textTheme,
        ),
      ),

      home: SplashScreen(api: api),

      onGenerateRoute: (settings) {
        if (settings.name == '/login') {
          return MaterialPageRoute<void>(
            builder: (_) => LoginScreen(api: api),
          );
        }

        if (settings.name == '/chat') {
          final arguments = settings.arguments;

          final profile =
              arguments is Map<String, dynamic>
                  ? arguments
                  : <String, dynamic>{};

          return MaterialPageRoute<void>(
            builder: (_) => ChatScreen(
              api: api,
              profile: profile,
              themeMode: themeMode,
              accent: accent,

              onThemeChanged: (mode) {
                setState(() {
                  themeMode = mode;
                });
              },

              onAccentChanged: (color) {
                setState(() {
                  accent = color;
                });
              },

              onSignOut: () async {
                await api.signOut();

                if (!mounted) return;

                Navigator.of(context)
                    .pushNamedAndRemoveUntil(
                  '/login',
                  (_) => false,
                );
              },
            ),
          );
        }

        return null;
      },
    );
  }
}
