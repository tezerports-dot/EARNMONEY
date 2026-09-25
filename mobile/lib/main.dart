import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'app/app.dart';
import 'app/env.dart';
import 'core/api/api_client.dart';
import 'core/api/future_fashion_api.dart';
import 'core/auth/token_store.dart';
import 'core/deep_links/install_referral.dart';
import 'core/deep_links/referral_links.dart';
import 'core/providers.dart';
import 'core/storage/prefs.dart';
import 'features/ads/ads.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

  final info = await PackageInfo.fromPlatform();
  final prefs = await SharedAppPrefs.load();
  final tokens = SecureTokenStore();
  final api = HttpFutureFashionApi(ApiClient(baseUrl: AppEnv.apiBaseUrl, appVersion: info.version, tokens: tokens));
  final ads = GoogleAdsService();

  // A code built into the shared APK first; a link opened later replaces it.
  await InstallReferral(prefs).load();
  await ReferralLinkListener(prefs).start();
  // Ads never block startup; they appear once consent and the SDK are ready.
  ads.initialize().ignore();

  runApp(
    ProviderScope(
      // Retries are handled by the API client (only where safe), never
      // automatically by the state layer.
      retry: (retryCount, error) => null,
      overrides: [
        apiProvider.overrideWithValue(api),
        tokenStoreProvider.overrideWithValue(tokens),
        prefsProvider.overrideWithValue(prefs),
        appVersionProvider.overrideWithValue(info.version),
        adsServiceProvider.overrideWithValue(ads),
      ],
      child: const FutureFashionApp(),
    ),
  );
}
