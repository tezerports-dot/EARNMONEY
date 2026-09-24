import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/api_exception.dart';
import '../../core/api/models.dart';
import '../../core/auth/session_controller.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/confetti.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../../core/widgets/status_chip.dart';

/// Telegram verification: instructions, then the pending state while the
/// user works through the bot. The server decides when it's complete.
class VerifyScreen extends ConsumerStatefulWidget {
  const VerifyScreen({super.key});

  static const pollEvery = Duration(seconds: 5);
  static const pollFor = Duration(minutes: 10);

  @override
  ConsumerState<VerifyScreen> createState() => _VerifyScreenState();
}

class _VerifyScreenState extends ConsumerState<VerifyScreen> with WidgetsBindingObserver {
  VerificationSession? _session;
  Object? _error;
  bool _busy = false;
  Timer? _timer;
  DateTime? _pollingSince;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _open();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Coming back from Telegram: check straight away.
    if (state == AppLifecycleState.resumed) {
      _check();
      _startPolling();
    } else if (state == AppLifecycleState.paused) {
      _timer?.cancel();
    }
  }

  void _startPolling() {
    _timer?.cancel();
    _pollingSince = DateTime.now();
    _timer = Timer.periodic(VerifyScreen.pollEvery, (_) {
      if (DateTime.now().difference(_pollingSince!) > VerifyScreen.pollFor) {
        _timer?.cancel(); // stop quietly; "Check again" still works
        return;
      }
      _check();
    });
  }

  Future<void> _open() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await ref.read(apiProvider).openVerification();
      if (!mounted) return;
      setState(() => _session = session);
      _startPolling();
    } on ServerRejection catch (e) {
      if (e.code == 'ALREADY_VERIFIED') {
        await _completed();
      } else if (mounted) {
        setState(() => _error = e);
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _check() async {
    try {
      final session = await ref.read(apiProvider).verificationStatus();
      if (!mounted) return;
      setState(() {
        _session = session;
        _error = null;
      });
      if (session.status == VerificationStatus.completed) await _completed();
    } on ApiException catch (e) {
      if (mounted && _session == null) setState(() => _error = e);
    }
  }

  /// Re-reading the account flips it to verified; the router then shows
  /// the success screen.
  Future<void> _completed() async {
    _timer?.cancel();
    try {
      await ref.read(sessionProvider.notifier).refreshUser();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _openTelegram() async {
    final link = _session?.deepLink;
    if (link == null) return;
    final opened = await launchUrl(Uri.parse(link), mode: LaunchMode.externalApplication);
    if (!opened && mounted) showMessage(context, 'Install Telegram, then tap “Open Telegram” again.');
  }

  String? _issueText(VerificationSession s, String phoneMasked) => switch (s.issue) {
    'CHANNELS_MISSING' =>
      'Some channels don’t have a join request yet. In Telegram, tap each JOIN button, send the request, '
          'then tap “I’ve sent the requests”.',
    'PHONE_MISMATCH' =>
      'The number shared in Telegram doesn’t match $phoneMasked. Use the Telegram account registered to that number.',
    'TELEGRAM_ALREADY_LINKED' =>
      'That Telegram account is already linked to another account. Use a different Telegram account.',
    'PHONE_MISMATCH_LIMIT' => 'Too many numbers didn’t match. Start again with a new link.',
    _ => null,
  };

  @override
  Widget build(BuildContext context) {
    final session = _session;
    final user = switch (ref.watch(sessionProvider).value) {
      SignedIn(:final user) => user,
      _ => null,
    };
    final phoneMasked = user?.phoneMasked ?? 'your number';
    final needsNewLink = session != null && !session.isOpen;
    final issue = session == null ? null : _issueText(session, phoneMasked);
    final waiting = session?.status == VerificationStatus.inProgress;

    return AppScreen(
      showBack: false,
      onRefresh: _check,
      actions: [
        TextButton(
          onPressed: () => ref.read(sessionProvider.notifier).logout(),
          child: const Text('Log out'),
        ),
      ],
      children: [
        Center(child: Illustrations.shield(size: 140)),
        const SizedBox(height: Space.xl),
        Semantics(header: true, child: const Text('Verify with Telegram', style: AppType.headline, textAlign: TextAlign.center)),
        const SizedBox(height: Space.s),
        Text(
          'This proves $phoneMasked is really yours. Your account unlocks when it’s done.',
          style: AppType.body,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: Space.xxl),
        if (_error != null && session == null)
          ErrorView(error: _error!, onRetry: _open)
        else ...[
          _Step(
            number: 1,
            title: 'Open our verification bot',
            body: session == null ? 'Preparing your personal link…' : 'Tap “Open Telegram” below. It opens @${session.botUsername}.',
          ),
          _Step(
            number: 2,
            title: 'Send the join requests',
            body: 'In Telegram, tap each small JOIN button and send the request, then tap “I’ve sent the requests”.',
            trailing: session == null || session.channelCount == 0
                ? null
                : Wrap(
                    spacing: Space.s,
                    runSpacing: Space.s,
                    children: [
                      for (var i = 1; i <= session.channelCount; i++)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: Space.m, vertical: 6),
                          decoration: BoxDecoration(
                            color: AppColors.telegram.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: AppColors.telegram.withValues(alpha: 0.5)),
                          ),
                          child: Text('JOIN $i', style: AppType.caption.copyWith(color: AppColors.telegram)),
                        ),
                    ],
                  ),
          ),
          const _Step(
            number: 3,
            title: 'Share your Telegram number',
            body: 'Tap “Share my phone number” in the bot. We only check it matches your signup number.',
          ),
          const SizedBox(height: Space.l),
          if (issue != null) ...[
            GlassCard(
              padding: const EdgeInsets.all(Space.l),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.info_outline_rounded, color: AppColors.warning),
                  const SizedBox(width: Space.m),
                  Expanded(child: Semantics(liveRegion: true, child: Text(issue, style: AppType.bodySmall))),
                ],
              ),
            ),
            const SizedBox(height: Space.l),
          ],
          if (waiting && issue == null)
            const Center(child: StatusChip(label: 'Waiting for Telegram…', tone: StatusTone.pending)),
          if (session?.status == VerificationStatus.expired)
            const Center(child: StatusChip(label: 'This link expired', tone: StatusTone.danger)),
          const SizedBox(height: Space.xl),
          if (needsNewLink)
            PrimaryButton(label: 'Get a new link', icon: Icons.refresh_rounded, loading: _busy, onPressed: _open)
          else
            PrimaryButton(
              label: 'Open Telegram',
              icon: Icons.send_rounded,
              loading: _busy || session == null,
              onPressed: _openTelegram,
            ),
          const SizedBox(height: Space.m),
          SecondaryButton(label: 'I’ve finished — check again', onPressed: session == null ? null : _check),
          const SizedBox(height: Space.xl),
          const Text(
            'We never ask for your Telegram password or login code. Join requests are reviewed by the channel admins.',
            style: AppType.caption,
            textAlign: TextAlign.center,
          ),
        ],
      ],
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({required this.number, required this.title, required this.body, this.trailing});

  final int number;
  final String title;
  final String body;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: Space.m),
    child: GlassCard(
      padding: const EdgeInsets.all(Space.l),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            alignment: Alignment.center,
            decoration: const BoxDecoration(shape: BoxShape.circle, gradient: AppColors.goldGradient),
            child: Text('$number', style: AppType.label.copyWith(color: AppColors.ink)),
          ),
          const SizedBox(width: Space.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppType.label),
                const SizedBox(height: Space.xs),
                Text(body, style: AppType.bodySmall),
                if (trailing != null) ...[const SizedBox(height: Space.m), trailing!],
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class VerifySuccessScreen extends StatefulWidget {
  const VerifySuccessScreen({super.key});

  @override
  State<VerifySuccessScreen> createState() => _VerifySuccessScreenState();
}

class _VerifySuccessScreenState extends State<VerifySuccessScreen> {
  void _continue() => context.go('/home');

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      AppScreen(
        showBack: false,
        particles: true,
        bottom: PrimaryButton(label: 'Continue', onPressed: _continue),
        children: [
          const SizedBox(height: Space.huge),
          Center(child: Illustrations.success(size: 200)),
          const SizedBox(height: Space.xxl),
          Semantics(
            header: true,
            child: const Text('Verification complete', style: AppType.headline, textAlign: TextAlign.center),
          ),
          const SizedBox(height: Space.m),
          const Text(
            'Your account is ready. You can now share your referral code and track your rewards.',
            style: AppType.body,
            textAlign: TextAlign.center,
          ),
        ],
      ),
      const Positioned.fill(child: ConfettiBurst()),
    ],
  );
}
