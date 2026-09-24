import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/config/config_controller.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/confetti.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';

/// Shown once, when the launch countdown has ended.
class CelebrationScreen extends ConsumerStatefulWidget {
  const CelebrationScreen({super.key});

  @override
  ConsumerState<CelebrationScreen> createState() => _CelebrationScreenState();
}

class _CelebrationScreenState extends ConsumerState<CelebrationScreen> {
  @override
  void initState() {
    super.initState();
    ref.read(prefsProvider).setLaunchCelebrated();
  }

  @override
  Widget build(BuildContext context) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final brand = cfg.campaign.brandName;
    return Stack(
      children: [
        AppScreen(
          showBack: false,
          particles: true,
          bottom: PrimaryButton(label: 'Continue', onPressed: () => context.canPop() ? context.pop() : context.go('/home')),
          children: [
            const SizedBox(height: Space.huge),
            Center(child: Illustrations.launch(size: 220)),
            const SizedBox(height: Space.xxl),
            Semantics(
              header: true,
              child: Text(
                brand == null ? 'We’re live!' : 'Welcome to $brand',
                style: AppType.display.copyWith(fontSize: 36),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: Space.m),
            Text(
              'Thank you for being part of the ${cfg.companyName} launch. Your rewards and referral history '
              'are in your wallet.',
              style: AppType.body,
              textAlign: TextAlign.center,
            ),
          ],
        ),
        const Positioned.fill(child: ConfettiBurst(pieces: 90)),
      ],
    );
  }
}
