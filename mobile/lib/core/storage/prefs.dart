import 'package:shared_preferences/shared_preferences.dart';

/// Non-sensitive preferences only. Referral attribution is never decided
/// here: a stored code only pre-fills the signup form, and the server
/// validates and binds it at signup.
abstract interface class AppPrefs {
  bool get onboardingSeen;
  Future<void> setOnboardingSeen();
  String? get pendingReferralCode;
  Future<void> setPendingReferralCode(String? code);
  bool get launchCelebrated;
  Future<void> setLaunchCelebrated();

  /// Whether the referral code built into the installed APK was read yet.
  bool get installReferralChecked;
  Future<void> setInstallReferralChecked();
}

class SharedAppPrefs implements AppPrefs {
  SharedAppPrefs(this._prefs);

  static Future<SharedAppPrefs> load() async {
    try {
      return SharedAppPrefs(await SharedPreferences.getInstance());
    } on Object {
      return SharedAppPrefs(null); // storage unavailable: behave like a first launch
    }
  }

  final SharedPreferences? _prefs;

  @override
  bool get onboardingSeen => _prefs?.getBool('onboarding_seen') ?? false;

  @override
  Future<void> setOnboardingSeen() async => _prefs?.setBool('onboarding_seen', true);

  @override
  String? get pendingReferralCode => _prefs?.getString('pending_referral_code');

  @override
  Future<void> setPendingReferralCode(String? code) async {
    if (code == null) {
      await _prefs?.remove('pending_referral_code');
    } else {
      await _prefs?.setString('pending_referral_code', code);
    }
  }

  @override
  bool get launchCelebrated => _prefs?.getBool('launch_celebrated') ?? false;

  @override
  Future<void> setLaunchCelebrated() async => _prefs?.setBool('launch_celebrated', true);

  @override
  bool get installReferralChecked => _prefs?.getBool('install_referral_checked') ?? false;

  @override
  Future<void> setInstallReferralChecked() async => _prefs?.setBool('install_referral_checked', true);
}

class MemoryAppPrefs implements AppPrefs {
  @override
  bool onboardingSeen = false;
  @override
  String? pendingReferralCode;
  @override
  bool launchCelebrated = false;
  @override
  bool installReferralChecked = false;

  @override
  Future<void> setOnboardingSeen() async => onboardingSeen = true;

  @override
  Future<void> setPendingReferralCode(String? code) async => pendingReferralCode = code;

  @override
  Future<void> setLaunchCelebrated() async => launchCelebrated = true;

  @override
  Future<void> setInstallReferralChecked() async => installReferralChecked = true;
}
