import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api/models.dart';

/// Why the app file couldn't be attached.
enum ApkUnavailableReason {
  /// Installed from a store as several split APKs: there's no single file to send.
  splitInstall,

  /// Copying failed, usually because the phone is full.
  copyFailed,

  /// Not running on Android, or the native helper is missing.
  unsupported,
}

class ApkUnavailable implements Exception {
  const ApkUnavailable(this.reason);

  final ApkUnavailableReason reason;

  String get message => switch (reason) {
    ApkUnavailableReason.splitInstall =>
      'This copy of the app was installed from a store in parts, so it can’t be sent as one file.',
    ApkUnavailableReason.copyFailed =>
      'The app file couldn’t be prepared. Free up some space on your phone and try again.',
    ApkUnavailableReason.unsupported => 'This phone can’t attach the app file.',
  };

  @override
  String toString() => 'ApkUnavailable($reason)';
}

/// Shares the app itself (CLAUDE.md §14).
///
/// "Share App + Referral" always sends the APK file. The native side
/// (MainActivity) copies this app's own installed APK into its cache, with no
/// storage permission, and builds the sharer's referral code into the copy
/// (ApkReferral.kt). The friend's app reads that code on first launch and
/// fills it in at signup, even when the file travels without the message
/// (Bluetooth, Nearby Share, Xender…). The server still checks the code at
/// signup, like any typed code.
///
/// If the file can't be attached this throws [ApkUnavailable]. It never quietly
/// sends a link instead: sharing the link is a separate choice ([shareLink]).
class ApkShareService {
  const ApkShareService();

  static const _channel = MethodChannel('futurefashion/apk');
  static const apkMimeType = 'application/vnd.android.package-archive';

  static String fileName(String appVersion, String referralCode) => 'FutureFashion-$appVersion-$referralCode.apk';

  static String appMessage(String companyName, ShareInfo info, {required bool codeBuiltIn}) =>
      'I’m sending you the $companyName app (the file attached). Install it and sign up. '
      '${codeBuiltIn ? 'My referral code ${info.referralCode} fills itself in.' : 'Use my referral code ${info.referralCode}.'}\n'
      'After installing, this link also fills it in: ${info.referralLink}\n'
      'Joining is free. Rewards follow the campaign rules in the app.';

  static String linkMessage(String companyName, ShareInfo info) =>
      'Join me on $companyName! Sign up with my referral code ${info.referralCode}: ${info.referralLink}\n'
      'Joining is free. Rewards follow the campaign rules in the app.';

  /// Sends the APK file with the referral code built in. Returns how the
  /// share sheet ended (sent, dismissed, or unknown on older Android).
  Future<ShareResultStatus> shareAppAndReferral({
    required String companyName,
    required ShareInfo info,
    required String appVersion,
  }) async {
    final Map<Object?, Object?>? prepared;
    try {
      prepared = await _channel.invokeMapMethod<Object?, Object?>('prepareApk', {
        'fileName': fileName(appVersion, info.referralCode),
        'referralCode': info.referralCode,
      });
    } on PlatformException catch (e) {
      throw ApkUnavailable(
        e.code == 'SPLIT_INSTALL' ? ApkUnavailableReason.splitInstall : ApkUnavailableReason.copyFailed,
      );
    } on MissingPluginException {
      throw const ApkUnavailable(ApkUnavailableReason.unsupported);
    }
    final path = prepared?['path'];
    if (path is! String) throw const ApkUnavailable(ApkUnavailableReason.copyFailed);
    final result = await SharePlus.instance.share(
      ShareParams(
        text: appMessage(companyName, info, codeBuiltIn: prepared?['withCode'] == true),
        subject: companyName,
        files: [XFile(path, mimeType: apkMimeType)],
      ),
    );
    return result.status;
  }

  /// A separate, explicit choice: the referral link and the download page.
  Future<void> shareLink({required String companyName, required ShareInfo info}) => SharePlus.instance.share(
    ShareParams(text: '${linkMessage(companyName, info)}\nDownload the app: ${info.apkDownloadUrl}'),
  );
}
