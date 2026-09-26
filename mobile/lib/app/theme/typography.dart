import 'package:flutter/material.dart';

import 'colors.dart';

/// Type tokens from docs/APP.md. Sizes scale with the phone's text setting.
abstract final class AppType {
  static const _display = 'PlayfairDisplay';
  static const _body = 'Manrope';

  static const display = TextStyle(
    fontFamily: _display,
    fontWeight: FontWeight.w700,
    fontSize: 40,
    height: 46 / 40,
    color: AppColors.textPrimary,
  );
  static const headline = TextStyle(
    fontFamily: _display,
    fontWeight: FontWeight.w600,
    fontSize: 28,
    height: 34 / 28,
    color: AppColors.textPrimary,
  );
  static const title = TextStyle(
    fontFamily: _body,
    fontWeight: FontWeight.w700,
    fontSize: 20,
    height: 26 / 20,
    color: AppColors.textPrimary,
  );
  static const body = TextStyle(
    fontFamily: _body,
    fontWeight: FontWeight.w500,
    fontSize: 16,
    height: 24 / 16,
    color: AppColors.textSecondary,
  );
  static const bodySmall = TextStyle(
    fontFamily: _body,
    fontWeight: FontWeight.w500,
    fontSize: 14,
    height: 20 / 14,
    color: AppColors.textSecondary,
  );
  static const label = TextStyle(
    fontFamily: _body,
    fontWeight: FontWeight.w700,
    fontSize: 14,
    height: 18 / 14,
    letterSpacing: 0.2,
    color: AppColors.textPrimary,
  );
  static const caption = TextStyle(
    fontFamily: _body,
    fontWeight: FontWeight.w600,
    fontSize: 12,
    height: 16 / 12,
    letterSpacing: 0.3,
    color: AppColors.textMuted,
  );
  static const figure = TextStyle(
    fontFamily: _body,
    fontWeight: FontWeight.w800,
    fontSize: 32,
    height: 38 / 32,
    color: AppColors.textPrimary,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}
