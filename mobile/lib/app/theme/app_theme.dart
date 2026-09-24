import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'colors.dart';
import 'spacing.dart';
import 'typography.dart';

abstract final class AppTheme {
  static ThemeData dark() {
    const scheme = ColorScheme.dark(
      primary: AppColors.gold,
      onPrimary: AppColors.ink,
      secondary: AppColors.violet,
      onSecondary: AppColors.textPrimary,
      surface: AppColors.plum,
      onSurface: AppColors.textPrimary,
      error: AppColors.danger,
      onError: AppColors.ink,
      outline: AppColors.line,
    );
    final inputBorder = OutlineInputBorder(
      borderRadius: BorderRadius.circular(Radii.input),
      borderSide: const BorderSide(color: AppColors.line),
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.ink,
      fontFamily: 'Manrope',
      textTheme: const TextTheme(
        displayLarge: AppType.display,
        headlineMedium: AppType.headline,
        titleLarge: AppType.title,
        bodyLarge: AppType.body,
        bodyMedium: AppType.bodySmall,
        labelLarge: AppType.label,
        bodySmall: AppType.caption,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: AppType.title,
        foregroundColor: AppColors.textPrimary,
        systemOverlayStyle: SystemUiOverlayStyle.light,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF15122A),
        labelStyle: AppType.bodySmall,
        floatingLabelStyle: AppType.bodySmall.copyWith(color: AppColors.gold),
        hintStyle: AppType.bodySmall.copyWith(color: AppColors.textMuted),
        errorStyle: AppType.caption.copyWith(color: AppColors.danger),
        contentPadding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.l),
        border: inputBorder,
        enabledBorder: inputBorder,
        focusedBorder: inputBorder.copyWith(borderSide: const BorderSide(color: AppColors.gold, width: 1.5)),
        errorBorder: inputBorder.copyWith(borderSide: const BorderSide(color: AppColors.danger)),
        focusedErrorBorder: inputBorder.copyWith(borderSide: const BorderSide(color: AppColors.danger, width: 1.5)),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: AppColors.plum,
        contentTextStyle: AppType.bodySmall.copyWith(color: AppColors.textPrimary),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.chip)),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: AppColors.plum,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.sheet)),
        titleTextStyle: AppType.title,
        contentTextStyle: AppType.body,
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AppColors.plum,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(Radii.sheet))),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AppColors.night.withValues(alpha: 0.92),
        indicatorColor: AppColors.gold.withValues(alpha: 0.18),
        surfaceTintColor: Colors.transparent,
        height: 72,
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => AppType.caption.copyWith(
            color: states.contains(WidgetState.selected) ? AppColors.goldBright : AppColors.textMuted,
          ),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) =>
              IconThemeData(color: states.contains(WidgetState.selected) ? AppColors.goldBright : AppColors.textMuted),
        ),
      ),
      dividerTheme: const DividerThemeData(color: AppColors.line, thickness: 1, space: 1),
      progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.gold),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {TargetPlatform.android: FadeForwardsPageTransitionsBuilder()},
      ),
    );
  }
}
