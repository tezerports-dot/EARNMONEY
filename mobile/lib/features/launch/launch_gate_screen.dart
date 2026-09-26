// dart format off
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/config/config_controller.dart';
import '../../core/launch/launch_gate_controller.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';

class LaunchGateScreen extends ConsumerStatefulWidget {
  const LaunchGateScreen({super.key});

  @override
  ConsumerState<LaunchGateScreen> createState() => _LaunchGateScreenState();
}

class _LaunchGateScreenState extends ConsumerState<LaunchGateScreen> with WidgetsBindingObserver {
  LaunchChallenge? _challenge;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _check();
  }

  void _pass() => ref.read(gatePassedProvider.notifier).state = true;

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final challenge = await ref.read(apiProvider).launchChallenge();
      if (!mounted) return;
      if (!challenge.enabled || challenge.deepLink == null) {
        _pass();
        return;
      }
      setState(() => _challenge = challenge);
    } catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _check() async {
    try {
      final status = await ref.read(apiProvider).launchStatus();
      if (status.passed || !status.enabled) _pass();
    } catch (error) {
      if (mounted) showMessage(context, errorMessage(error));
    }
  }

  Future<void> _openTelegram() async {
    final link = _challenge?.deepLink;
    if (link == null) return;
    final opened = await launchUrl(Uri.parse(link), mode: LaunchMode.externalApplication);
    if (!opened && mounted) showMessage(context, 'Install Telegram, then try again.');
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const AppScreen(children: [LoadingView(blocks: 1)]);
    if (_error != null) {
      return AppScreen(children: [ErrorView(error: _error!, onRetry: _load)]);
    }
    final companyName = ref.watch(configProvider).valueOrNull?.config.companyName ?? 'Telegram';
    return AppScreen(
      children: [
        const SizedBox(height: Space.xxl),
        GlassCard(
          highlight: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Open $companyName', style: AppType.headline),
              const SizedBox(height: Space.m),
              const Text(
                'Continue from your verified Telegram account to unlock the app.',
                style: AppType.body,
              ),
              const SizedBox(height: Space.xl),
              PrimaryButton(
                label: 'Continue in Telegram',
                icon: Icons.send_rounded,
                onPressed: _openTelegram,
              ),
              const SizedBox(height: Space.m),
              SecondaryButton(label: 'I’ve done it — check again', onPressed: _check),
            ],
          ),
        ),
      ],
    );
  }
}
// dart format on
