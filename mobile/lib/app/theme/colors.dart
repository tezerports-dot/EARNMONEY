import 'package:flutter/material.dart';

/// Colour tokens from docs/APP.md. Contrast ratios are measured against [ink].
abstract final class AppColors {
  static const ink = Color(0xFF0B0A14);
  static const night = Color(0xFF141226);
  static const plum = Color(0xFF1F1A38);
  static const line = Color(0xFF2E2850);

  static const gold = Color(0xFFE8C07A);
  static const goldBright = Color(0xFFF6DDA8);
  static const goldDeep = Color(0xFFB8893F);
  static const violet = Color(0xFF7C5CFF);
  static const electric = Color(0xFF4C8DFF);
  static const telegram = Color(0xFF2AABEE);

  static const success = Color(0xFF3DDC97);
  static const warning = Color(0xFFF5B94C);
  static const danger = Color(0xFFFF7A7A);

  static const textPrimary = Color(0xFFF5F3FF); // 17.9:1
  static const textSecondary = Color(0xFFBEB8D6); // 10.3:1
  static const textMuted = Color(0xFF8E88AA); // 5.9:1

  static const glassFill = Color(0x12FFFFFF); // white 7%
  static const glassBorder = Color(0x1FFFFFFF); // white 12%

  static const goldGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [goldBright, gold, goldDeep],
  );

  static const backgroundGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFF1C1640), night, ink],
    stops: [0, 0.45, 1],
  );
}
