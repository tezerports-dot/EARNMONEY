import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/animations/motion.dart';
import '../../core/api/models.dart';
import '../../core/auth/session_controller.dart';
import '../../core/formatters/dates.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/figures.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../../core/widgets/status_chip.dart';

Future<void> confirmLogout(BuildContext context, WidgetRef ref) async {
  final yes = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Log out?'),
      content: const Text('You can log back in any time with your mobile number and password.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Log out')),
      ],
    ),
  );
  if (yes == true) await ref.read(sessionProvider.notifier).logout();
}

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider).value;
    if (session is! SignedIn) return const SizedBox.shrink();
    final user = session.user;
    return AppScreen(
      onRefresh: () => ref.read(sessionProvider.notifier).refreshUser(),
      children: [
        const SizedBox(height: Space.xl),
        Center(child: Illustrations.avatar(size: 110)),
        const SizedBox(height: Space.l),
        Center(child: Text(user.phoneMasked, style: AppType.title)),
        const SizedBox(height: Space.s),
        Center(
          child: StatusChip(
            label: user.status == AccountStatus.active ? 'Verified with Telegram' : 'Not verified',
            tone: user.status == AccountStatus.active ? StatusTone.success : StatusTone.pending,
          ),
        ),
        const SizedBox(height: Space.xl),
        GlassCard(
          child: Column(
            children: [
              _InfoRow(
                label: 'Your referral code',
                value: user.referralCode ?? '—',
                onCopy: user.referralCode == null
                    ? null
                    : () async {
                        await Clipboard.setData(ClipboardData(text: user.referralCode!));
                        if (context.mounted) showMessage(context, 'Referral code copied');
                      },
              ),
              const Divider(height: Space.xl),
              _InfoRow(label: 'Member ID', value: user.publicId),
              const Divider(height: Space.xl),
              _InfoRow(label: 'Referred by', value: user.referredBy ?? 'No one'),
              const Divider(height: Space.xl),
              _InfoRow(label: 'Member since', value: formatIstDate(user.createdAt)),
            ],
          ),
        ),
        const SizedBox(height: Space.xl),
        const _NavTile(icon: Icons.settings_outlined, label: 'Settings', route: '/settings'),
        const _NavTile(icon: Icons.lightbulb_outline_rounded, label: 'How it works', route: '/how-it-works'),
        const _NavTile(icon: Icons.rule_rounded, label: 'Reward rules', route: '/rules'),
        const _NavTile(icon: Icons.support_agent_rounded, label: 'Support', route: '/support'),
        const SizedBox(height: Space.xl),
        SecondaryButton(
          label: 'Log out',
          icon: Icons.logout_rounded,
          color: AppColors.danger,
          onPressed: () => confirmLogout(context, ref),
        ),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value, this.onCopy});

  final String label;
  final String value;
  final VoidCallback? onCopy;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: MergeSemantics(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [Text(label, style: AppType.caption), Text(value, style: AppType.label)],
          ),
        ),
      ),
      if (onCopy != null) IconButton(tooltip: 'Copy $label', icon: const Icon(Icons.copy_rounded), onPressed: onCopy),
    ],
  );
}

class _NavTile extends StatelessWidget {
  const _NavTile({required this.icon, required this.label, required this.route});

  final IconData icon;
  final String label;
  final String route;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: Space.s),
    child: GlassCard(
      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
      onTap: () => context.push(route),
      semanticLabel: label,
      child: ExcludeSemantics(
        child: Row(
          children: [
            Icon(icon, color: AppColors.gold),
            const SizedBox(width: Space.m),
            Expanded(child: Text(label, style: AppType.label)),
            const Icon(Icons.chevron_right_rounded, color: AppColors.textMuted),
          ],
        ),
      ),
    ),
  );
}

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final version = ref.watch(appVersionProvider);
    final reduced = Motion.of(context).reduced;
    return AppScreen(
      title: 'Settings',
      children: [
        const SectionTitle('Account security'),
        const GlassCard(
          child: Text(
            'Your password is never stored on this phone, only a secure session. Log out on phones you share. '
            'We will never ask for your password, OTP or UPI PIN by message.',
            style: AppType.bodySmall,
          ),
        ),
        const SectionTitle('Appearance'),
        GlassCard(
          child: Text(
            reduced
                ? 'Animations are reduced, following your phone’s accessibility setting.'
                : 'Animations follow your phone’s accessibility setting. Turn on “Remove animations” in Android '
                      'settings to reduce them.',
            style: AppType.bodySmall,
          ),
        ),
        const SectionTitle('Privacy and rules'),
        const _NavTile(icon: Icons.privacy_tip_outlined, label: 'Privacy notice', route: '/privacy'),
        const _NavTile(icon: Icons.description_outlined, label: 'Terms of use', route: '/terms'),
        const _NavTile(icon: Icons.rule_rounded, label: 'Reward rules', route: '/rules'),
        const _NavTile(icon: Icons.support_agent_rounded, label: 'Support', route: '/support'),
        const SizedBox(height: Space.xl),
        SecondaryButton(
          label: 'Log out',
          icon: Icons.logout_rounded,
          color: AppColors.danger,
          onPressed: () => confirmLogout(context, ref),
        ),
        const SizedBox(height: Space.xl),
        Center(child: Text('Version $version', style: AppType.caption)),
      ],
    );
  }
}
