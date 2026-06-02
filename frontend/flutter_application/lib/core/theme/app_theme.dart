import 'package:flutter/material.dart';

class AppTheme {
  // Background layers
  static const Color bgDeep = Color(0xFF0A0E1A); // scaffold
  static const Color bgCard = Color(0xFF141829); // cards, dialogs
  static const Color bgSurface = Color(0xFF1C2137); // input bar, appbar

  // Accent palette
  static const Color accentPrimary = Color(0xFF7C6AFF); // primary indigo-violet
  static const Color accentSecondary = Color(0xFF38BDF8); // sky-blue for AI/drift
  static const Color accentTertiary = Color(0xFF34D399); // emerald for success
  static const Color accentWarm = Color(0xFFF59E0B); // amber for uploads
  static const Color accentCoral = Color(0xFFFB7185); // coral-rose for errors/code

  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: accentPrimary,
        brightness: Brightness.dark,
      ),
      scaffoldBackgroundColor: bgDeep,
      cardColor: bgCard,
      useMaterial3: true,
    );
  }
}
