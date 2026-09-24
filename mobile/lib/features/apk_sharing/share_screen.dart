import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme/colors.dart';
import '../../app/theme/spacing.dart';
import '../../app/theme/typography.dart';
import '../../core/api/models.dart';
import '../../core/config/config_controller.dart';
import '../../core/data_providers.dart';
import '../../core/formatters/inr.dart';
import '../../core/providers.dart';
import '../../core/widgets/buttons.dart';
import '../../core/widgets/glass_card.dart';
import '../../core/widgets/illustrations.dart';
import '../../core/widgets/screen.dart';
import '../../core/widgets/state_views.dart';
import '../ads/ads.dart';
import 'apk_share_service.dart';

final apkShareServiceProvider = Provider<ApkShareService>((ref) => const ApkShareService());

class ShareScreen extends ConsumerStatefulWidget {
  const ShareScreen({super.key});

  @override
  ConsumerState<ShareScreen> createState() => _ShareScreenState();
}

class _ShareScreenState extends ConsumerState<ShareScreen> {
  bool _sharing = false;
  late final AdsService _ads;
  AdSettings? _adSettings;

  @override
  void initState() {
    super.initState();
    _ads = ref.read(adsServiceProvider);
  }

  @override
  void dispose() {
    // A quiet boundary: leaving the share screen. Frequency-capped by the server.
    final settings = _adSettings;
    if (settings != null) _ads.maybeShowInterstitial(settings).ignore(); // an ad problem never reaches the user
    super.dispose();
  }

  Future<void> _copy(String text, String what) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) showMessage(context, '$what copied');
  }

  Future<void> _shareApp(ShareInfo info, String company) async {
    setState(() => _sharing = true);
    try {
      await ref
          .read(apkShareServiceProvider)
          .shareAppAndReferral(companyName: company, info: info, appVersion: ref.read(appVersionProvider));
    } on Object {
      if (mounted) showMessage(context, 'Sharing isn’t available right now. Copy the link instead.');
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cfg = ref.watch(configProvider).requireValue.config;
    final share = ref.watch(shareInfoProvider);
    _adSettings = cfg.ads;
    return AppScreen(
      title: 'Share & refer',
      particles: true,
      children: [
        Center(child: Illustrations.share(size: 150)),
        const SizedBox(height: Space.l),
        Text(
          'Earn ${formatPaise(cfg.level1RewardPaise)} for each friend who signs up with your code and verifies.',
          style: AppType.body,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: Space.xl),
        AsyncBody<ShareInfo>(
          value: share,
          onRetry: () => ref.invalidate(shareInfoProvider),
          data: (info) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              GlassCard(
                highlight: true,
                child: Column(
                  children: [
                    const Text('Your referral code', style: AppType.caption),
                    const SizedBox(height: Space.s),
                    SelectableText(
                      info.referralCode,
                      style: AppType.display.copyWith(fontSize: 34, letterSpacing: 4, color: AppColors.goldBright),
                    ),
                    const SizedBox(height: Space.m),
                    SecondaryButton(
                      label: 'Copy Referral Code',
                      icon: Icons.copy_rounded,
                      onPressed: () => _copy(info.referralCode, 'Referral code'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: Space.l),
              GlassCard(
                padding: const EdgeInsets.all(Space.l),
                child: Row(
                  children: [
                    const Icon(Icons.link_rounded, color: AppColors.gold),
                    const SizedBox(width: Space.m),
                    Expanded(child: Text(info.referralLink, style: AppType.bodySmall)),
                    IconButton(
                      tooltip: 'Copy link',
                      icon: const Icon(Icons.copy_rounded),
                      onPressed: () => _copy(info.referralLink, 'Referral link'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: Space.xl),
              PrimaryButton(
                label: 'Share App + Referral',
                icon: Icons.install_mobile_rounded,
                loading: _sharing,
                onPressed: () => _shareApp(info, cfg.companyName),
              ),
              const SizedBox(height: Space.m),
              SecondaryButton(
                label: 'Share Referral Link',
                icon: Icons.ios_share_rounded,
                onPressed: () => ref.read(apkShareServiceProvider).shareLink(companyName: cfg.companyName, info: info),
              ),
              const SizedBox(height: Space.xl),
              const GlassCard(
                padding: EdgeInsets.all(Space.l),
                child: Text(
                  'How your friend is linked to you: they enter your code when signing up (links fill it in '
                  'automatically when the app is already installed). The link is decided by our server at signup '
                  'and can’t be changed later. Their reward counts once they verify with Telegram.',
                  style: AppType.bodySmall,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
