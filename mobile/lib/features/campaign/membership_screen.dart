import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/config/config_controller.dart';
import '../../core/formatters/inr.dart';
import '../../core/widgets/figures.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';

/// The published member count: a real statistic, not scarcity marketing.
class MembershipScreen extends ConsumerWidget {
  const MembershipScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cfg = ref.watch(configProvider).requireValue.config;
    return AppScreen(
      title: 'Members',
      onRefresh: () => ref.read(configProvider.notifier).reload(),
      children: [
        const SizedBox(height: Space.l),
        Center(child: Illustrations.crowd(size: 160)),
        const SizedBox(height: Space.xl),
        GlassCard(
          highlight: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Verified members', style: AppType.caption),
              const SizedBox(height: Space.xs),
              AnimatedCount(value: cfg.verifiedCount, semanticsLabel: 'Verified members'),
              const SizedBox(height: Space.l),
              GoalProgress(value: cfg.verifiedCount, goal: cfg.capacity, label: 'Toward campaign capacity'),
              const SizedBox(height: Space.s),
              Text('Campaign capacity: ${groupIndian(cfg.capacity)} members', style: AppType.bodySmall),
            ],
          ),
        ),
        const SizedBox(height: Space.l),
        const GlassCard(
          child: Text(
            'This number is counted by our server: it goes up by one each time someone completes Telegram '
            'verification, and never otherwise. Sign-ups close when the campaign reaches its capacity.',
            style: AppType.bodySmall,
          ),
        ),
      ],
    );
  }
}
