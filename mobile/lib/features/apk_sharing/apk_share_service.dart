import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api/models.dart';

/// Shares the app and the user's referral code (CLAUDE.md §14).
///
/// The installed APK is copied by the native side (MainActivity) into this
/// app's own cache, with no storage permission, and handed to Android's
/// share sheet. Where that isn't possible (for example a store install made
/// of split APKs) it shares the download link instead. Either way the
/// referral itself travels as the code/link: the server binds it at signup.
class ApkShareService {
  const ApkShareService();

  static const _channel = MethodChannel('futurefashion/apk');
  static const apkMimeType = 'application/vnd.android.package-archive';

  static String message(String companyName, ShareInfo info) =>
      'Join me on $companyName! Sign up with my referral code ${info.referralCode}: ${info.referralLink}\n'
      'Joining is free. Rewards follow the campaign rules in the app.';

  Future<void> shareAppAndReferral({
    required String companyName,
    required ShareInfo info,
    required String appVersion,
  }) async {
    String? path;
    try {
      path = await _channel.invokeMethod<String>('prepareApk', {'fileName': 'FutureFashion-$appVersion.apk'});
    } on PlatformException {
      path = null;
    } on MissingPluginException {
      path = null;
    }
    final text = message(companyName, info);
    if (path == null) {
      await SharePlus.instance.share(ShareParams(text: '$text\nDownload the app: ${info.apkDownloadUrl}'));
      return;
    }
    await SharePlus.instance.share(
      ShareParams(
        text: text,
        subject: companyName,
        files: [XFile(path, mimeType: apkMimeType)],
      ),
    );
  }

  Future<void> shareLink({required String companyName, required ShareInfo info}) => SharePlus.instance.share(
    ShareParams(text: '${message(companyName, info)}\nDownload the app: ${info.apkDownloadUrl}'),
  );
}
