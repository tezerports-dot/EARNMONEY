import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';

/// The one strong call to action on a screen. While [loading] it shows a
/// spinner and can't be tapped again, so a request is never sent twice.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({super.key, required this.label, required this.onPressed, this.loading = false, this.icon});

  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !loading;
    return Semantics(
      button: true,
      enabled: enabled,
      label: loading ? '$label, in progress' : label,
      excludeSemantics: true,
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 150),
        opacity: enabled || loading ? 1 : 0.45,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: AppColors.goldGradient,
            borderRadius: BorderRadius.circular(Radii.button),
            boxShadow: enabled
                ? [BoxShadow(color: AppColors.gold.withValues(alpha: 0.28), blurRadius: 24, offset: const Offset(0, 8))]
                : null,
          ),
          child: Material(
            type: MaterialType.transparency,
            child: InkWell(
              borderRadius: BorderRadius.circular(Radii.button),
              onTap: enabled ? onPressed : null,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 56),
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.xl, vertical: Space.m),
                    child: loading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2.5, color: AppColors.ink),
                          )
                        : Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (icon != null) ...[Icon(icon, color: AppColors.ink, size: 20), const SizedBox(width: Space.s)],
                              Flexible(
                                child: Text(
                                  label,
                                  textAlign: TextAlign.center,
                                  style: AppType.label.copyWith(color: AppColors.ink, fontSize: 16),
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class SecondaryButton extends StatelessWidget {
  const SecondaryButton({super.key, required this.label, required this.onPressed, this.icon, this.color});

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tint = color ?? AppColors.textPrimary;
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        foregroundColor: tint,
        side: BorderSide(color: tint.withValues(alpha: 0.35)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.button)),
        textStyle: AppType.label,
        padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: Space.s)],
          Flexible(child: Text(label, textAlign: TextAlign.center)),
        ],
      ),
    );
  }
}

class LinkButton extends StatelessWidget {
  const LinkButton({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => TextButton(
    onPressed: onPressed,
    style: TextButton.styleFrom(
      minimumSize: const Size(Space.tapTarget, Space.tapTarget),
      foregroundColor: AppColors.goldBright,
      textStyle: AppType.label,
    ),
    child: Text(label),
  );
}
