import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/animations/motion.dart';
import '../../core/api/models.dart';
import '../../core/config/config_controller.dart';
import '../../core/data_providers.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/figures.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../../core/widgets/status_chip.dart';
import 'countdown.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _celebrationChecked = false;

  Future<void> _refresh() async {
    ref.invalidate(dashboardProvider);
    await ref.read(configProvider.notifier).reload();
    await ref.read(dashboardProvider.future);
  }

  void _maybeCelebrate(ConfigState state) {
    if (_celebrationChecked) return;
    _celebrationChecked = true;
    final prefs = ref.read(prefsProvider);
    if (!state.serverNow().isBefore(state.config.campaign.launchAt) && !prefs.launchCelebrated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.push('/celebration');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(configProvider).requireValue;
    final cfg = state.config;
    final dashboard = ref.watch(dashboardProvider);
    _maybeCelebrate(state);
    final now = state.serverNow();
    final launched = !now.isBefore(cfg.campaign.launchAt);
    final revealed = cfg.campaign.brandName != null;

    return AppScreen(
      particles: true,
      onRefresh: _refresh,
      children: [
        const SizedBox(height: Space.m),
        _Header(companyName: cfg.companyName, dashboard: dashboard.value),
        if (cfg.announcement case final a?) ...[const SizedBox(height: Space.l), _AnnouncementBanner(a)],
        const SizedBox(height: Space.xl),
        EntranceFade(
          child: Column(
            children: [
              Illustrations.launch(size: 170),
              const SizedBox(height: Space.xl),
              Semantics(
                header: true,
                child: Text(
                  'Your Referrals.\nYour Rewards.\nOur Big Launch.',
                  style: AppType.display.copyWith(fontSize: 34, height: 1.15),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: Space.m),
              Text(
                'Invite friends to ${cfg.companyName}. For each friend you invite who verifies, you earn '
                '${formatPaise(cfg.level1RewardPaise)}, under the campaign rules.',
                style: AppType.body,
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
        const SizedBox(height: Space.xl),
        _CampaignNotice(cfg.campaign),
        CountdownCard(
          target: launched ? cfg.campaign.endsAt : cfg.campaign.launchAt,
          title: launched ? 'Campaign ends in' : 'Launch in',
          doneText: launched ? 'The campaign has ended' : 'We’re live!',
        ),
        const SizedBox(height: Space.l),
        GlassCard(
          child: Column(
            children: [
              _DateRow(
                icon: Icons.auto_awesome_rounded,
                label: revealed ? 'Brand revealed' : 'Brand name reveal',
                value: revealed ? cfg.campaign.brandName! : formatIstDayMonth(cfg.campaign.brandRevealAt),
              ),
              const Divider(height: Space.xxl),
              _DateRow(
                icon: Icons.rocket_launch_rounded,
                label: 'Launch',
                value: formatIstDayMonth(cfg.campaign.launchAt),
              ),
              const Divider(height: Space.xxl),
              _DateRow(
                icon: Icons.account_balance_wallet_rounded,
                label: 'Rewards withdrawable from',
                value: formatIstDayMonth(cfg.campaign.payoutOpensAt),
              ),
            ],
          ),
        ),
        const SizedBox(height: Space.l),
        _MembershipCard(verified: cfg.verifiedCount, capacity: cfg.capacity),
        if (cfg.promotionAllocationPaise case final allocation?) ...[
          const SizedBox(height: Space.l),
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Promotional allocation', style: AppType.caption),
                const SizedBox(height: Space.xs),
                Text(formatPaise(allocation), style: AppType.figure),
                const SizedBox(height: Space.s),
                Text(
                  'The budget ${cfg.companyName} has set aside for referral rewards. '
                  'It is not a promise of any individual’s earnings.',
                  style: AppType.bodySmall,
                ),
              ],
            ),
          ),
        ],
        const SectionTitle('Your progress'),
        AsyncBody(
          value: dashboard,
          loadingBlocks: 1,
          onRetry: () => ref.invalidate(dashboardProvider),
          data: (d) => GlassCard(
            onTap: () => context.go('/wallet'),
            semanticLabel: 'Open wallet',
            child: Row(
              children: [
                Expanded(
                  child: _Stat(
                    label: 'Earned',
                    child: AnimatedCount(value: d.totalEarnedPaise, money: true, style: AppType.title),
                  ),
                ),
                Expanded(
                  child: _Stat(
                    label: 'Friends verified',
                    child: AnimatedCount(value: d.level1Count, style: AppType.title),
                  ),
                ),
                Expanded(
                  child: _Stat(
                    label: 'Still verifying',
                    child: AnimatedCount(value: d.level1PendingCount, style: AppType.title),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.xxl),
        PrimaryButton(label: 'Start Referring', icon: Icons.ios_share_rounded, onPressed: () => context.push('/share')),
        const SizedBox(height: Space.m),
        SecondaryButton(label: 'How It Works', onPressed: () => context.push('/how-it-works')),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.companyName, required this.dashboard});

  final String companyName;
  final Dashboard? dashboard;

  @override
  Widget build(BuildContext context) {
    final code = dashboard?.referralCode;
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Welcome', style: AppType.caption),
              Text(companyName, style: AppType.title),
            ],
          ),
        ),
        if (code != null)
          Semantics(
            button: true,
            label: 'Your referral code $code. Copy',
            excludeSemantics: true,
            child: InkWell(
              borderRadius: BorderRadius.circular(Radii.chip),
              onTap: () async {
                await Clipboard.setData(ClipboardData(text: code));
                if (context.mounted) showMessage(context, 'Referral code copied');
              },
              child: Padding(
                padding: const EdgeInsets.all(Space.xs),
                child: StatusChip(label: code, tone: StatusTone.neutral),
              ),
            ),
          ),
      ],
    );
  }
}

class _AnnouncementBanner extends StatelessWidget {
  const _AnnouncementBanner(this.announcement);

  final Announcement announcement;

  @override
  Widget build(BuildContext context) {
    final tone = switch (announcement.tone) {
      'success' => StatusTone.success,
      'warning' => StatusTone.pending,
      _ => StatusTone.info,
    };
    return GlassCard(
      padding: const EdgeInsets.all(Space.l),
      child: Row(
        children: [
          StatusChip(label: 'Update', tone: tone),
          const SizedBox(width: Space.m),
          Expanded(child: Text(announcement.text, style: AppType.bodySmall)),
        ],
      ),
    );
  }
}

class _CampaignNotice extends StatelessWidget {
  const _CampaignNotice(this.campaign);

  final CampaignInfo campaign;

  @override
  Widget build(BuildContext context) {
    final text = switch (campaign.status) {
      CampaignStatus.paused => 'The campaign is paused. New sign-ups and new rewards are on hold.',
      CampaignStatus.ended => 'The campaign has ended. No new rewards are being added.',
      CampaignStatus.notStarted => 'The campaign hasn’t started yet.',
      CampaignStatus.active when !campaign.rewardsOpen =>
        'New referral rewards are closed right now. Rewards you already earned are unaffected.',
      CampaignStatus.active => null,
    };
    if (text == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.l),
      child: GlassCard(
        padding: const EdgeInsets.all(Space.l),
        child: Row(
          children: [
            const Icon(Icons.info_outline_rounded, color: AppColors.warning),
            const SizedBox(width: Space.m),
            Expanded(child: Text(text, style: AppType.bodySmall)),
          ],
        ),
      ),
    );
  }
}

class _DateRow extends StatelessWidget {
  const _DateRow({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Row(
      children: [
        Icon(icon, color: AppColors.gold, size: 22),
        const SizedBox(width: Space.m),
        Expanded(child: Text(label, style: AppType.bodySmall)),
        const SizedBox(width: Space.s),
        Flexible(
          child: Text(value, style: AppType.label, textAlign: TextAlign.right),
        ),
      ],
    ),
  );
}

class _MembershipCard extends StatelessWidget {
  const _MembershipCard({required this.verified, required this.capacity});

  final int verified;
  final int capacity;

  @override
  Widget build(BuildContext context) => GlassCard(
    onTap: () => context.push('/membership'),
    semanticLabel: 'Verified members: ${groupIndian(verified)} of ${groupIndian(capacity)}. Open details',
    child: ExcludeSemantics(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Illustrations.crowd(size: 56),
              const SizedBox(width: Space.m),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Verified members so far', style: AppType.caption),
                    AnimatedCount(value: verified, style: AppType.figure.copyWith(fontSize: 28)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: Space.l),
          GoalProgress(value: verified, goal: capacity, label: 'Toward campaign capacity'),
          const SizedBox(height: Space.xs),
          Text('Campaign capacity: ${groupIndian(capacity)} members', style: AppType.caption),
        ],
      ),
    ),
  );
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft, child: child),
      const SizedBox(height: Space.xs),
      Text(label, style: AppType.caption),
    ],
  );
}
