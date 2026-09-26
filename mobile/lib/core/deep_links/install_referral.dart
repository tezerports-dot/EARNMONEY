import 'package:flutter/services.dart';

import '../storage/prefs.dart';
import 'referral_links.dart';

/// Reads the referral code built into the APK this copy was installed from
/// (a friend's "Share App + Referral", see ApkShareService), once, on the first
/// launch. Like a code from a link, it only pre-fills signup: the server checks
/// it at signup, and a link opened later replaces it.
class InstallReferral {
  InstallReferral(this._prefs, {this.channel = const MethodChannel('futurefashion/apk')});

  final AppPrefs _prefs;
  final MethodChannel channel;

  Future<void> load() async {
    if (_prefs.installReferralChecked) return;
    try {
      final code = normalizeReferralCode(await channel.invokeMethod<String>('embeddedReferralCode'));
      if (code != null && _prefs.pendingReferralCode == null) await _prefs.setPendingReferralCode(code);
    } on Object {
      // Not on Android, or no code in this APK: nothing to fill in.
    }
    await _prefs.setInstallReferralChecked();
  }
}
