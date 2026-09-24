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
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../../core/widgets/status_chip.dart';
import '../ads/ads.dart';

/// The four-level table (CLAUDE.md §9). Every figure comes from the
/// server's daily snapshot; nothing is multiplied out on the phone.
class ReferralsScreen extends ConsumerWidget {
  const ReferralsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(referralSummaryProvider);
    return AppScreen(
      onRefresh: () async {
        ref
          ..invalidate(referralSummaryProvider)
          ..invalidate(directPreviewProvider);
        await ref.read(referralSummaryProvider.future);
      },
      children: [
        const SizedBox(height: Space.m),
        Semantics(header: true, child: const Text('Your referrals', style: AppType.headline)),
        const SizedBox(height: Space.s),
        const Text('How far your invitations have spread.', style: AppType.body),
        const SizedBox(height: Space.l),
        Center(child: Illustrations.network(size: 130)),
        const SizedBox(height: Space.l),
        AsyncBody<ReferralSummary>(
          value: summary,
          onRetry: () => ref.invalidate(referralSummaryProvider),
          data: (s) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _LevelTable(summary: s),
              const SizedBox(height: Space.s),
              Text(
                s.refreshPending
                    ? 'Updated ${formatIstDateTime(s.generatedAt)}. A newer count is being prepared.'
                    : 'Updated ${formatIstDateTime(s.generatedAt)}. Counts refresh once a day.',
                style: AppType.caption,
              ),
              const SizedBox(height: Space.l),
              _LevelOneCard(summary: s),
            ],
          ),
        ),
        const SizedBox(height: Space.xxl),
        PrimaryButton(
          label: 'Invite more friends',
          icon: Icons.ios_share_rounded,
          onPressed: () => context.push('/share'),
        ),
        const SizedBox(height: Space.xl),
        const AdBanner(),
      ],
    );
  }
}

class _LevelTable extends StatelessWidget {
  const _LevelTable({required this.summary});

  final ReferralSummary summary;

  @override
  Widget build(BuildContext context) {
    Widget cell(String text, {bool header = false, TextAlign align = TextAlign.right, Color? color}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: Space.m, horizontal: Space.xs),
      child: Text(
        text,
        textAlign: align,
        style: (header ? AppType.caption : AppType.label).copyWith(color: color),
      ),
    );

    return GlassCard(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.l),
      child: Column(
        children: [
          Table(
            columnWidths: const {
              0: FlexColumnWidth(1.1),
              1: FlexColumnWidth(1),
              2: FlexColumnWidth(1.2),
              3: FlexColumnWidth(1.3),
            },
            defaultVerticalAlignment: TableCellVerticalAlignment.middle,
            children: [
              TableRow(
                decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: AppColors.line)),
                ),
                children: [
                  cell('Layer', header: true, align: TextAlign.left),
                  cell('Users', header: true),
                  cell('Reward / user', header: true),
                  cell('Total', header: true),
                ],
              ),
              for (final row in summary.levels)
                TableRow(
                  children: [
                    Semantics(
                      label:
                          'Level ${row.level}: ${groupIndian(row.userCount)} users, '
                          '${formatPaise(row.rewardPerUserPaise)} each, total ${formatPaise(row.totalRewardPaise)}',
                      excludeSemantics: true,
                      child: cell('Level ${row.level}', align: TextAlign.left),
                    ),
                    ExcludeSemantics(child: cell(groupIndian(row.userCount))),
                    ExcludeSemantics(
                      child: cell(
                        formatPaise(row.rewardPerUserPaise),
                        color: row.rewardPerUserPaise > 0 ? AppColors.goldBright : AppColors.textMuted,
                      ),
                    ),
                    ExcludeSemantics(
                      child: cell(
                        formatPaise(row.totalRewardPaise),
                        color: row.totalRewardPaise > 0 ? AppColors.goldBright : AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              TableRow(
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: AppColors.line)),
                ),
                children: [
                  cell('Total', align: TextAlign.left),
                  cell(groupIndian(summary.totalUserCount)),
                  cell(''),
                  cell(formatPaise(summary.totalRewardPaise), color: AppColors.goldBright),
                ],
              ),
            ],
          ),
          const SizedBox(height: Space.m),
          Row(
            children: [
              const Icon(Icons.info_outline_rounded, size: 18, color: AppColors.textSecondary),
              const SizedBox(width: Space.s),
              Expanded(
                child: Text(
                  'Only direct referrals (level 1) earn rewards. Levels 2–4 show how far your invitations spread; '
                  'they pay ₹0.',
                  style: AppType.caption.copyWith(color: AppColors.textSecondary),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LevelOneCard extends ConsumerWidget {
  const _LevelOneCard({required this.summary});

  final ReferralSummary summary;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final preview = ref.watch(directPreviewProvider);
    return GlassCard(
      highlight: true,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: EdgeInsets.zero,
          iconColor: AppColors.goldBright,
          collapsedIconColor: AppColors.textSecondary,
          title: const Text('Level 1 — your direct referrals', style: AppType.label),
          subtitle: Text(
            summary.level1PendingCount == 0
                ? '${groupIndian(summary.levels.first.userCount)} verified'
                : '${groupIndian(summary.levels.first.userCount)} verified · ${groupIndian(summary.level1PendingCount)} still verifying',
            style: AppType.caption,
          ),
          children: [
            AsyncBody<Paged<DirectReferral>>(
              value: preview,
              loadingBlocks: 1,
              onRetry: () => ref.invalidate(directPreviewProvider),
              data: (page) => page.items.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.symmetric(vertical: Space.l),
                      child: Text('No direct referrals yet. Share your code to get started.', style: AppType.bodySmall),
                    )
                  : Column(
                      children: [
                        for (final r in page.items) DirectReferralTile(referral: r),
                        const SizedBox(height: Space.s),
                        SecondaryButton(
                          label: 'See all direct referrals',
                          onPressed: () => context.push('/referrals/direct'),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class DirectReferralTile extends StatelessWidget {
  const DirectReferralTile({super.key, required this.referral});

  final DirectReferral referral;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: Space.s),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: AppColors.plum,
            child: Text(
              referral.publicId.substring(0, 2),
              style: AppType.caption.copyWith(color: AppColors.goldBright),
            ),
          ),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(referral.phoneMasked, style: AppType.label),
                Text('ID ${referral.publicId} · joined ${formatIstDate(referral.joinedAt)}', style: AppType.caption),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              StatusChip(
                label: referral.verified ? 'Verified' : 'Verifying',
                tone: referral.verified ? StatusTone.success : StatusTone.pending,
              ),
              const SizedBox(height: Space.xs),
              Text(formatPaise(referral.rewardPaise), style: AppType.caption.copyWith(color: AppColors.goldBright)),
            ],
          ),
        ],
      ),
    ),
  );
}
