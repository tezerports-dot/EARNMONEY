import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/widgets/confetti.dart';
import '../../core/widgets/figures.dart';

/// "Your income": the user's total referral income across all four levels,
/// straight from the server's ledger (/v1/dashboard), never worked out on the
/// phone. Only level 1 pays, so level 1 is the whole total and levels 2–4
/// show ₹0. A short confetti burst celebrates income above zero (none when the
/// phone asks for reduced motion). Tapping opens the wallet.
class IncomeCard extends StatelessWidget {
  const IncomeCard({
    super.key,
    required this.dashboard,
    required this.payoutOpensAt,
    required this.payoutsOpen,
    required this.rewardPerFriendPaise,
    required this.onOpen,
    required this.onRetry,
  });

  final AsyncValue<Dashboard> dashboard;
  final DateTime payoutOpensAt;
  final bool payoutsOpen;
  final int rewardPerFriendPaise;
  final VoidCallback onOpen;
  final VoidCallback onRetry;

  static const _radius = BorderRadius.all(Radius.circular(Radii.card));

  @override
  Widget build(BuildContext context) {
    final d = dashboard.value;
    final total = d?.totalEarnedPaise ?? 0;
    final celebrate = d != null && total > 0;
    return Semantics(
      container: true,
      button: d != null,
      label: d == null ? null : _spoken(d),
      excludeSemantics: d != null,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: _radius,
          gradient: AppColors.goldGradient, // the gold rim
          boxShadow: [BoxShadow(color: AppColors.gold.withValues(alpha: 0.28), blurRadius: 36, spreadRadius: -6)],
        ),
        child: Padding(
          padding: const EdgeInsets.all(1.6),
          child: Material(
            color: AppColors.night,
            borderRadius: _radius,
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: d == null ? null : onOpen,
              child: Stack(
                children: [
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: RadialGradient(
                          center: const Alignment(0, -1.2),
                          radius: 1.3,
                          colors: [AppColors.gold.withValues(alpha: 0.22), AppColors.night.withValues(alpha: 0)],
                        ),
                      ),
                    ),
                  ),
                  Padding(padding: const EdgeInsets.all(Space.xl), child: _content(d)),
                  if (celebrate) const Positioned.fill(child: ConfettiBurst(pieces: 36)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _content(Dashboard? d) {
    if (d == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Title(),
          const SizedBox(height: Space.m),
          if (dashboard.hasError) ...[
            const Text('Couldn’t load your income just now.', style: AppType.bodySmall),
            TextButton(onPressed: onRetry, child: const Text('Try again')),
          ] else
            const SizedBox(height: 56, child: Center(child: LinearProgressIndicator())),
        ],
      );
    }
    final total = d.totalEarnedPaise;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _Title(),
        const SizedBox(height: Space.s),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: AnimatedCount(
            value: total,
            money: true,
            style: AppType.display.copyWith(fontSize: 46, height: 1.1, color: AppColors.goldBright),
          ),
        ),
        const SizedBox(height: Space.xs),
        const Text('Total from all 4 referral levels', style: AppType.caption),
        const SizedBox(height: Space.m),
        Wrap(
          spacing: Space.s,
          runSpacing: Space.s,
          children: [
            for (final level in [1, 2, 3, 4]) _LevelPill(level: level, paise: level == 1 ? total : 0),
          ],
        ),
        const SizedBox(height: Space.m),
        _status(d),
      ],
    );
  }

  Widget _status(Dashboard d) {
    final (icon, color, text) = switch ((d.totalEarnedPaise, payoutsOpen)) {
      (0, _) => (
        Icons.group_add_rounded,
        AppColors.textSecondary,
        'Invite friends: you earn ${formatPaise(rewardPerFriendPaise)} for each one who verifies.',
      ),
      (_, false) => (Icons.lock_clock_rounded, AppColors.warning, 'Pending until ${formatIstDate(payoutOpensAt)}'),
      (_, true) => (
        Icons.account_balance_wallet_rounded,
        AppColors.success,
        '${formatPaise(d.availablePaise)} available to withdraw',
      ),
    };
    return Row(
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: Space.s),
        Expanded(
          child: Text(text, style: AppType.bodySmall.copyWith(color: color)),
        ),
      ],
    );
  }

  String _spoken(Dashboard d) {
    final status = d.totalEarnedPaise == 0
        ? 'Invite friends to start earning.'
        : payoutsOpen
        ? '${formatPaise(d.availablePaise)} available to withdraw.'
        : 'Pending until ${formatIstDate(payoutOpensAt)}.';
    return 'Your income: ${formatPaise(d.totalEarnedPaise)}, from all four referral levels. $status Opens your wallet.';
  }
}

class _Title extends StatelessWidget {
  const _Title();

  @override
  Widget build(BuildContext context) => Row(
    children: [
      const Icon(Icons.celebration_rounded, color: AppColors.goldBright, size: 20),
      const SizedBox(width: Space.s),
      Text('YOUR INCOME', style: AppType.label.copyWith(color: AppColors.goldBright, letterSpacing: 1.6)),
    ],
  );
}

class _LevelPill extends StatelessWidget {
  const _LevelPill({required this.level, required this.paise});

  final int level;
  final int paise;

  @override
  Widget build(BuildContext context) {
    final paid = paise > 0;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: Space.xs),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Radii.chip),
        color: paid ? AppColors.gold.withValues(alpha: 0.16) : AppColors.glassFill,
        border: Border.all(color: paid ? AppColors.gold.withValues(alpha: 0.5) : AppColors.glassBorder),
      ),
      child: Text(
        'L$level ${formatPaise(paise)}',
        style: AppType.caption.copyWith(color: paid ? AppColors.goldBright : AppColors.textMuted),
      ),
    );
  }
}
