import 'package:flutter/material.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';

enum StatusTone { success, pending, danger, info, neutral }

/// Status is never colour alone: every chip has an icon and a word.
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.label, required this.tone});

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final (color, icon) = switch (tone) {
      StatusTone.success => (AppColors.success, Icons.check_circle_rounded),
      StatusTone.pending => (AppColors.warning, Icons.schedule_rounded),
      StatusTone.danger => (AppColors.danger, Icons.error_outline_rounded),
      StatusTone.info => (AppColors.electric, Icons.info_outline_rounded),
      StatusTone.neutral => (AppColors.textSecondary, Icons.circle_outlined),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(Radii.chip),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 6),
          Flexible(
            child: Text(label, style: AppType.caption.copyWith(color: color)),
          ),
        ],
      ),
    );
  }
}
