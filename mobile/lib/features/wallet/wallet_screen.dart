import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/data_providers.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/figures.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../../core/widgets/status_chip.dart';

/// Every figure is the server's ledger balance. The phone never adds up
/// rewards from referral counts (CLAUDE.md §12).
class WalletScreen extends ConsumerWidget {
  const WalletScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wallet = ref.watch(walletProvider);
    return AppScreen(
      onRefresh: () async {
        ref.invalidate(walletProvider);
        await ref.read(walletProvider.future);
      },
      children: [
        const SizedBox(height: Space.m),
        Semantics(header: true, child: const Text('Wallet', style: AppType.headline)),
        const SizedBox(height: Space.l),
        AsyncBody<Wallet>(
          value: wallet,
          onRetry: () => ref.invalidate(walletProvider),
          data: (w) => _WalletBody(wallet: w),
        ),
      ],
    );
  }
}

class _WalletBody extends StatelessWidget {
  const _WalletBody({required this.wallet});

  final Wallet wallet;

  @override
  Widget build(BuildContext context) {
    final w = wallet;
    final canWithdraw = w.payoutsOpen && w.availablePaise >= w.minWithdrawalPaise;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GlassCard(
          highlight: true,
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Total earned', style: AppType.caption),
                    const SizedBox(height: Space.xs),
                    AnimatedCount(value: w.totalEarnedPaise, money: true, semanticsLabel: 'Total earned'),
                    const SizedBox(height: Space.xs),
                    Text('${w.level1RewardCount} direct referral rewards', style: AppType.bodySmall),
                  ],
                ),
              ),
              Illustrations.wallet(size: 96),
            ],
          ),
        ),
        const SizedBox(height: Space.m),
        Row(
          children: [
            Expanded(
              child: _Figure(label: 'Available to withdraw', paise: w.availablePaise, color: AppColors.success),
            ),
            const SizedBox(width: Space.m),
            Expanded(
              child: _Figure(
                label: w.payoutsOpen ? 'Pending' : 'Pending until ${formatIstDayMonth(w.payoutOpensAt)}',
                paise: w.pendingPaise,
                color: AppColors.warning,
              ),
            ),
          ],
        ),
        const SizedBox(height: Space.m),
        Row(
          children: [
            Expanded(
              child: _Figure(label: 'Being paid out', paise: w.inWithdrawalPaise),
            ),
            const SizedBox(width: Space.m),
            Expanded(
              child: _Figure(label: 'Withdrawn', paise: w.withdrawnPaise),
            ),
          ],
        ),
        const SizedBox(height: Space.l),
        if (!w.payoutsOpen)
          GlassCard(
            padding: const EdgeInsets.all(Space.l),
            child: Row(
              children: [
                const Icon(Icons.event_rounded, color: AppColors.gold),
                const SizedBox(width: Space.m),
                Expanded(
                  child: Text(
                    'Rewards become withdrawable on ${formatIstDate(w.payoutOpensAt)}. Until then they stay pending.',
                    style: AppType.bodySmall,
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: Space.l),
        PrimaryButton(
          label: 'Withdraw',
          icon: Icons.account_balance_rounded,
          onPressed: canWithdraw ? () => context.push('/wallet/withdraw') : null,
        ),
        if (w.payoutsOpen && !canWithdraw)
          Padding(
            padding: const EdgeInsets.only(top: Space.s),
            child: Text(
              'The minimum withdrawal is ${formatPaise(w.minWithdrawalPaise)}.',
              style: AppType.caption,
              textAlign: TextAlign.center,
            ),
          ),
        const SizedBox(height: Space.m),
        Row(
          children: [
            Expanded(
              child: SecondaryButton(label: 'Bank details', onPressed: () => context.push('/wallet/bank')),
            ),
            const SizedBox(width: Space.m),
            Expanded(
              child: SecondaryButton(label: 'History', onPressed: () => context.push('/wallet/history')),
            ),
          ],
        ),
        const SectionTitle('Reward breakdown'),
        GlassCard(
          child: Column(
            children: [
              _BreakdownRow('Level 1 · direct referrals', '${w.level1RewardCount} × rewards', w.level1RewardPaise),
              const Divider(height: Space.xl),
              for (final level in [2, 3, 4]) ...[
                _BreakdownRow('Level $level', 'not paid', 0),
                if (level != 4) const Divider(height: Space.xl),
              ],
            ],
          ),
        ),
        const SectionTitle('Recent activity'),
        if (w.recentEntries.isEmpty)
          const EmptyView(
            title: 'No activity yet',
            message: 'Rewards appear here as soon as a friend you invited completes verification.',
          )
        else
          GlassCard(
            padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.s),
            child: Column(children: [for (final e in w.recentEntries) _EntryTile(entry: e)]),
          ),
      ],
    );
  }
}

class _Figure extends StatelessWidget {
  const _Figure({required this.label, required this.paise, this.color});

  final String label;
  final int paise;
  final Color? color;

  @override
  Widget build(BuildContext context) => GlassCard(
    padding: const EdgeInsets.all(Space.l),
    child: MergeSemantics(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppType.caption),
          const SizedBox(height: Space.xs),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Amount(paise, style: AppType.title.copyWith(color: color)),
          ),
        ],
      ),
    ),
  );
}

class _BreakdownRow extends StatelessWidget {
  const _BreakdownRow(this.label, this.detail, this.paise);

  final String label;
  final String detail;
  final int paise;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: AppType.label),
              Text(detail, style: AppType.caption),
            ],
          ),
        ),
        Amount(paise, style: AppType.label.copyWith(color: paise > 0 ? AppColors.goldBright : AppColors.textMuted)),
      ],
    ),
  );
}

class _EntryTile extends StatelessWidget {
  const _EntryTile({required this.entry});

  final WalletEntry entry;

  @override
  Widget build(BuildContext context) {
    final (title, icon) = switch (entry.kind) {
      EntryKind.referralReward => (
        'Reward for ${entry.counterpartyPublicId ?? 'a referral'}',
        Icons.card_giftcard_rounded,
      ),
      EntryKind.rewardsUnlocked => ('Rewards unlocked for withdrawal', Icons.lock_open_rounded),
      EntryKind.withdrawal => ('Withdrawal requested', Icons.north_east_rounded),
      EntryKind.withdrawalReturned => ('Withdrawal returned to wallet', Icons.undo_rounded),
    };
    final sign = entry.kind == EntryKind.rewardsUnlocked ? '' : (entry.credit ? '+' : '−');
    return MergeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.m),
        child: Row(
          children: [
            Icon(icon, color: AppColors.gold),
            const SizedBox(width: Space.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: AppType.label),
                  Text(formatIstDateTime(entry.createdAt), style: AppType.caption),
                ],
              ),
            ),
            Text(
              '$sign${formatPaise(entry.amountPaise)}',
              style: AppType.label.copyWith(color: entry.credit ? AppColors.success : AppColors.textPrimary),
            ),
          ],
        ),
      ),
    );
  }
}

class WithdrawalStatusChip extends StatelessWidget {
  const WithdrawalStatusChip(this.status, {super.key});

  final WithdrawalStatus status;

  @override
  Widget build(BuildContext context) => switch (status) {
    WithdrawalStatus.requested => const StatusChip(label: 'Requested', tone: StatusTone.info),
    WithdrawalStatus.processing => const StatusChip(label: 'Processing', tone: StatusTone.pending),
    WithdrawalStatus.paid => const StatusChip(label: 'Paid', tone: StatusTone.success),
    WithdrawalStatus.failed => const StatusChip(label: 'Failed', tone: StatusTone.danger),
  };
}
