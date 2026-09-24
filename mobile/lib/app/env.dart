/// Build-time settings, passed with `--dart-define-from-file=config/<env>.json`.
///
/// Nothing here is secret: the APK can be unpacked by anyone. Server
/// addresses, the public web host and ad unit ids only.
abstract final class AppEnv {
  static const String name = String.fromEnvironment('ENV', defaultValue: 'dev');
  static const String apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');
  static const String webHost = String.fromEnvironment('WEB_HOST', defaultValue: 'dev.futurefashion.example');

  // Google's public test ad units unless a build passes real ones.
  static const String _bannerId = String.fromEnvironment('ADMOB_BANNER_ID');
  static const String _interstitialId = String.fromEnvironment('ADMOB_INTERSTITIAL_ID');
  static const String _rewardedId = String.fromEnvironment('ADMOB_REWARDED_ID');

  static String get bannerAdUnitId => _bannerId.isEmpty ? 'ca-app-pub-3940256099942544/6300978111' : _bannerId;
  static String get interstitialAdUnitId =>
      _interstitialId.isEmpty ? 'ca-app-pub-3940256099942544/1033173712' : _interstitialId;
  static String get rewardedAdUnitId => _rewardedId.isEmpty ? 'ca-app-pub-3940256099942544/5224354917' : _rewardedId;

  static bool get isProduction => name == 'production';

  /// Referral links look like `https://<webHost>/r/CODE`.
  static String referralLink(String code) => 'https://$webHost/r/$code';
}
