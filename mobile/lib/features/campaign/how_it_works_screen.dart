import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/config/config_controller.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/screen.dart';
import '../ads/ads.dart';

class HowItWorksScreen extends ConsumerWidget {
  const HowItWorksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final reward = formatPaise(cfg.level1RewardPaise);
    final steps = [
      (
        Icons.person_add_alt_1_rounded,
        'Create your account',
        'Sign up with your mobile number and a password. It’s free.',
      ),
      (
        Icons.verified_user_rounded,
        'Verify with Telegram',
        'Send join requests to our channels and share your Telegram number so we know the account is yours.',
      ),
      (
        Icons.ios_share_rounded,
        'Invite friends',
        'Share your code or the app. You earn $reward for each friend who signs up with your code and verifies.',
      ),
      (
        Icons.account_balance_wallet_rounded,
        'Track and withdraw',
        'Watch your referrals and wallet. Withdraw to your bank from ${formatIstDate(cfg.campaign.payoutOpensAt)}.',
      ),
    ];
    return AppScreen(
      title: 'How it works',
      children: [
        for (var i = 0; i < steps.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.m),
            child: GlassCard(
              child: MergeSemantics(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: const BoxDecoration(shape: BoxShape.circle, gradient: AppColors.goldGradient),
                      child: Icon(steps[i].$1, color: AppColors.ink),
                    ),
                    const SizedBox(width: Space.l),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Step ${i + 1}', style: AppType.caption),
                          Text(steps[i].$2, style: AppType.label),
                          const SizedBox(height: Space.xs),
                          Text(steps[i].$3, style: AppType.bodySmall),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        const SizedBox(height: Space.l),
        const Text('Your referral tree', style: AppType.title),
        const SizedBox(height: Space.m),
        GlassCard(child: _TreeDiagram(reward: reward)),
        const SizedBox(height: Space.m),
        const Text(
          'Only people you invite directly earn you a reward. The table also shows how far your invitations '
          'spread (levels 2–4), which pay ₹0. Nothing beyond level 4 is counted.',
          style: AppType.bodySmall,
        ),
        const AdBanner(),
      ],
    );
  }
}

class _TreeDiagram extends StatelessWidget {
  const _TreeDiagram({required this.reward});

  final String reward;

  @override
  Widget build(BuildContext context) {
    final levels = [('You', null), ('Level 1', reward), ('Level 2', '₹0'), ('Level 3', '₹0'), ('Level 4', '₹0')];
    return Semantics(
      label: 'Referral tree: level 1 earns $reward per person; levels 2, 3 and 4 earn nothing.',
      excludeSemantics: true,
      child: Column(
        children: [
          for (var i = 0; i < levels.length; i++) ...[
            Row(
              children: [
                SizedBox(width: 96, child: Text(levels[i].$1, style: i == 0 ? AppType.label : AppType.bodySmall)),
                Expanded(
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (var n = 0; n < (i == 0 ? 1 : (i * 2).clamp(1, 6)); n++)
                        Container(
                          width: 18,
                          height: 18,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: i <= 1 ? AppColors.goldGradient : null,
                            color: i <= 1 ? null : AppColors.line,
                            border: Border.all(color: i <= 1 ? AppColors.goldBright : AppColors.textMuted),
                          ),
                        ),
                    ],
                  ),
                ),
                if (levels[i].$2 != null)
                  Text(
                    levels[i].$2!,
                    style: AppType.label.copyWith(color: i == 1 ? AppColors.goldBright : AppColors.textMuted),
                  ),
              ],
            ),
            if (i < levels.length - 1)
              Padding(
                padding: const EdgeInsets.only(left: 8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Container(width: 2, height: 14, color: AppColors.line),
                ),
              ),
          ],
        ],
      ),
    );
  }
}
