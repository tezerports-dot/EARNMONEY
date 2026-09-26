import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/api_exception.dart';
import '../../core/auth/session_controller.dart';
import '../../core/config/config_controller.dart';
import '../../core/config/support_contact.dart';
import '../../core/formatters/dates.dart';
import '../../core/widgets/app_background.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/illustrations.dart';

/// Retry everything the app needs to start.
void retryStartup(WidgetRef ref) {
  ref.invalidate(configProvider);
  ref.invalidate(sessionProvider);
}

class _SystemPage extends StatelessWidget {
  const _SystemPage({required this.art, required this.title, required this.message, required this.actions});

  final Widget art;
  final String title;
  final String message;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: AppBackground(
      child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Space.xxl),
            child: Column(
              children: [
                art,
                const SizedBox(height: Space.xxxl),
                Semantics(
                  header: true,
                  child: Text(title, style: AppType.headline, textAlign: TextAlign.center),
                ),
                const SizedBox(height: Space.m),
                Text(message, style: AppType.body, textAlign: TextAlign.center),
                const SizedBox(height: Space.xxxl),
                for (final action in actions) ...[action, const SizedBox(height: Space.m)],
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: AppBackground(
      particles: true,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Illustrations.launch(size: 180),
            const SizedBox(height: Space.xxl),
            Text('Future Fashion', style: AppType.display.copyWith(fontSize: 34)),
            const SizedBox(height: Space.s),
            const Text('Referral rewards for our launch', style: AppType.bodySmall),
            const SizedBox(height: Space.xxxl),
            const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2.5)),
          ],
        ),
      ),
    ),
  );
}

class OfflineScreen extends ConsumerWidget {
  const OfflineScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => _SystemPage(
    art: Illustrations.offline(),
    title: 'Connection unavailable',
    message:
        'The app needs the internet to securely sync your account and reward data. '
        'Nothing is lost: check your connection and try again.',
    actions: [PrimaryButton(label: 'Try again', icon: Icons.refresh_rounded, onPressed: () => retryStartup(ref))],
  );
}

class MaintenanceScreen extends ConsumerWidget {
  const MaintenanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final config = ref.watch(configProvider);
    final error = config.error;
    String? message;
    DateTime? until;
    if (config.value?.config case final cfg? when cfg.maintenanceActive) {
      message = cfg.maintenanceMessage;
      until = cfg.maintenanceUntil;
    } else if (error is MaintenanceException) {
      message = error.message;
      until = error.until;
    }
    return _SystemPage(
      art: Illustrations.maintenance(),
      title: "We'll be right back",
      message: [
        message ?? "We're improving things behind the scenes. Your account and rewards are safe.",
        if (until != null) 'Expected back by ${formatIstDateTime(until)}.',
      ].join('\n\n'),
      actions: [PrimaryButton(label: 'Try again', icon: Icons.refresh_rounded, onPressed: () => retryStartup(ref))],
    );
  }
}

class UpgradeScreen extends ConsumerWidget {
  const UpgradeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final config = ref.watch(configProvider);
    final error = config.error;
    final url = config.value?.config.apkDownloadUrl ?? (error is UpgradeRequiredException ? error.downloadUrl : null);
    return _SystemPage(
      art: Illustrations.launch(size: 150),
      title: 'Update required',
      message: 'A newer version of the app is needed to keep your account secure. Install it, then open the app again.',
      actions: [
        if (url != null)
          PrimaryButton(
            label: 'Download the update',
            icon: Icons.download_rounded,
            onPressed: () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
          ),
        SecondaryButton(label: 'Check again', onPressed: () => retryStartup(ref)),
      ],
    );
  }
}

class SuspendedScreen extends ConsumerWidget {
  const SuspendedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cfg = ref.watch(configProvider).value?.config;
    final contact = cfg == null ? null : supportContact(cfg);
    return _SystemPage(
      art: Illustrations.shield(size: 140),
      title: 'Account suspended',
      message: 'This account has been suspended. If you think this is a mistake, contact support.',
      actions: [
        if (contact != null)
          PrimaryButton(
            label: 'Contact support',
            onPressed: () => launchUrl(contact, mode: LaunchMode.externalApplication),
          ),
        SecondaryButton(
          label: 'Log out',
          color: AppColors.textSecondary,
          onPressed: () => ref.read(sessionProvider.notifier).logout(),
        ),
      ],
    );
  }
}
