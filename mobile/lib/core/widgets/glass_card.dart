import 'dart:ui';

import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';

/// Frosted, softly bordered card: the main surface of the design system.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(Space.xl),
    this.highlight = false,
    this.onTap,
    this.semanticLabel,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  /// A warmer, gold-tinted variant for the most important card on a screen.
  final bool highlight;
  final VoidCallback? onTap;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(Radii.card);
    final card = ClipRRect(
      borderRadius: radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: radius,
            border: Border.all(color: highlight ? AppColors.gold.withValues(alpha: 0.35) : AppColors.glassBorder),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: highlight
                  ? [AppColors.gold.withValues(alpha: 0.16), AppColors.violet.withValues(alpha: 0.08)]
                  : [Colors.white.withValues(alpha: 0.09), Colors.white.withValues(alpha: 0.04)],
            ),
          ),
          child: Material(
            type: MaterialType.transparency,
            child: InkWell(
              onTap: onTap,
              borderRadius: radius,
              child: Padding(padding: padding, child: child),
            ),
          ),
        ),
      ),
    );
    return semanticLabel == null ? card : Semantics(label: semanticLabel, button: onTap != null, child: card);
  }
}
