import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/animations/motion.dart';
import '../../core/config/config_controller.dart';
import '../../core/formatters/dates.dart';
import '../../core/formatters/inr.dart';
import '../../core/providers.dart';
import '../../core/widgets/app_background.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/illustrations.dart';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _pages = PageController();
  int _index = 0;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  Future<void> _finish(String route) async {
    await ref.read(prefsProvider).setOnboardingSeen();
    if (mounted) context.go(route);
  }

  @override
  Widget build(BuildContext context) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final panels = [
      (
        Illustrations.launch(size: 190),
        'A new fashion label is coming',
        '${cfg.companyName} reveals its brand name on ${formatIstDayMonth(cfg.campaign.brandRevealAt)} '
            'and launches on ${formatIstDayMonth(cfg.campaign.launchAt)}.',
      ),
      (
        Illustrations.share(size: 180),
        'Invite your friends',
        'Share your referral code. For each friend you invite who signs up and verifies with Telegram, '
            'you earn ${formatPaise(cfg.level1RewardPaise)}, under the campaign rules.',
      ),
      (
        Illustrations.wallet(size: 180),
        'Track real rewards',
        'Your referral table and wallet show figures from our server, never estimates. '
            'Rewards can be withdrawn from ${formatIstDate(cfg.campaign.payoutOpensAt)}.',
      ),
    ];
    final last = _index == panels.length - 1;
    final motion = Motion.of(context);
    return Scaffold(
      body: AppBackground(
        particles: true,
        child: SafeArea(
          child: Column(
            children: [
              Align(
                alignment: Alignment.centerRight,
                child: LinkButton(label: 'Skip', onPressed: () => _finish('/signup')),
              ),
              Expanded(
                child: PageView(
                  controller: _pages,
                  onPageChanged: (i) => setState(() => _index = i),
                  children: [
                    for (final (art, title, body) in panels)
                      SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(horizontal: Space.xxl),
                        child: Column(
                          children: [
                            const SizedBox(height: Space.xxl),
                            art,
                            const SizedBox(height: Space.xxxl),
                            Semantics(
                              header: true,
                              child: Text(title, style: AppType.headline, textAlign: TextAlign.center),
                            ),
                            const SizedBox(height: Space.l),
                            Text(body, style: AppType.body, textAlign: TextAlign.center),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 0; i < panels.length; i++)
                    AnimatedContainer(
                      duration: motion.transition,
                      margin: const EdgeInsets.all(4),
                      width: i == _index ? 22 : 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: i == _index ? AppColors.gold : AppColors.line,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.all(Space.screen),
                child: Column(
                  children: [
                    PrimaryButton(
                      label: last ? 'Create account' : 'Next',
                      onPressed: last
                          ? () => _finish('/signup')
                          : () => _pages.nextPage(duration: motion.transition, curve: Motion.curve),
                    ),
                    const SizedBox(height: Space.s),
                    LinkButton(label: 'I already have an account', onPressed: () => _finish('/login')),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
