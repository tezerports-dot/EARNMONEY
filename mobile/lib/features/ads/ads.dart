import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';

import '../../app/env.dart';
import '../../app/theme/spacing.dart';
import '../../core/api/models.dart';
import '../../core/config/config_controller.dart';

/// All ad code sits behind this interface (CLAUDE.md §15). Placement rules:
/// banners only on non-critical screens, interstitials only at quiet
/// navigation boundaries and never more often than the server's minimum
/// interval, and never on signup, verification, wallet or withdrawal screens.
abstract interface class AdsService {
  bool get enabled;
  Future<void> initialize();
  Future<void> maybeShowInterstitial(AdSettings settings);
}

/// No ads (tests, and builds before an AdMob account exists).
class NoAdsService implements AdsService {
  @override
  bool get enabled => false;

  @override
  Future<void> initialize() async {}

  @override
  Future<void> maybeShowInterstitial(AdSettings settings) async {}
}

class GoogleAdsService implements AdsService {
  bool _ready = false;
  DateTime? _lastInterstitial;
  InterstitialAd? _preloaded;

  @override
  bool get enabled => _ready;

  @override
  Future<void> initialize() async {
    try {
      await _gatherConsent();
      if (!await ConsentInformation.instance.canRequestAds()) return;
      await MobileAds.instance.initialize();
      _ready = true;
    } on Object {
      _ready = false; // ads are optional: the app works without them
    }
  }

  Future<void> _gatherConsent() {
    final done = Completer<void>();
    ConsentInformation.instance.requestConsentInfoUpdate(
      ConsentRequestParameters(),
      () => ConsentForm.loadAndShowConsentFormIfRequired((_) => done.complete()),
      (_) => done.complete(),
    );
    return done.future;
  }

  void _preload() {
    if (!_ready || _preloaded != null) return;
    InterstitialAd.load(
      adUnitId: AppEnv.interstitialAdUnitId,
      request: const AdRequest(),
      adLoadCallback: InterstitialAdLoadCallback(
        onAdLoaded: (ad) => _preloaded = ad,
        onAdFailedToLoad: (_) => _preloaded = null,
      ),
    );
  }

  @override
  Future<void> maybeShowInterstitial(AdSettings settings) async {
    if (!_ready || !settings.interstitialEnabled) return;
    final last = _lastInterstitial;
    if (last != null && DateTime.now().difference(last) < settings.minInterstitialInterval) return;
    final ad = _preloaded;
    if (ad == null) {
      _preload(); // ready for the next boundary
      return;
    }
    _preloaded = null;
    _lastInterstitial = DateTime.now();
    ad.fullScreenContentCallback = FullScreenContentCallback(
      onAdDismissedFullScreenContent: (ad) {
        ad.dispose();
        _preload();
      },
      onAdFailedToShowFullScreenContent: (ad, _) => ad.dispose(),
    );
    await ad.show();
  }
}

final adsServiceProvider = Provider<AdsService>((ref) => NoAdsService());

/// A banner for non-critical screens. Renders nothing when banners are off
/// on the server, ads aren't initialised, or the ad fails to load.
class AdBanner extends ConsumerWidget {
  const AdBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ads = ref.watch(adsServiceProvider);
    final settings = ref.watch(configProvider).value?.config.ads ?? AdSettings.off;
    if (!ads.enabled || !settings.bannerEnabled) return const SizedBox.shrink();
    return const _GoogleBanner();
  }
}

class _GoogleBanner extends StatefulWidget {
  const _GoogleBanner();

  @override
  State<_GoogleBanner> createState() => _GoogleBannerState();
}

class _GoogleBannerState extends State<_GoogleBanner> {
  BannerAd? _ad;
  bool _loaded = false;

  @override
  void initState() {
    super.initState();
    _ad = BannerAd(
      adUnitId: AppEnv.bannerAdUnitId,
      size: AdSize.banner,
      request: const AdRequest(),
      listener: BannerAdListener(
        onAdLoaded: (_) => mounted ? setState(() => _loaded = true) : null,
        onAdFailedToLoad: (ad, _) => ad.dispose(),
      ),
    )..load();
  }

  @override
  void dispose() {
    _ad?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ad = _ad;
    if (!_loaded || ad == null) return const SizedBox.shrink();
    // Clearly separated from the app's own buttons, so it can't be mistaken for one.
    return Padding(
      padding: const EdgeInsets.only(top: Space.l),
      child: Column(
        children: [
          Text('Advertisement', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: Space.xs),
          SizedBox(
            width: ad.size.width.toDouble(),
            height: ad.size.height.toDouble(),
            child: AdWidget(ad: ad),
          ),
        ],
      ),
    );
  }
}
