import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/deep_links/install_referral.dart';
import 'package:future_fashion/core/storage/prefs.dart';
import 'package:future_fashion/features/apk_sharing/apk_share_service.dart';
import 'package:share_plus/share_plus.dart';

/// "Share App + Referral" must send the APK file itself, with the sharer's
/// code built in, and never quietly fall back to a download link.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const apkChannel = MethodChannel('futurefashion/apk');
  const shareChannel = MethodChannel('dev.fluttercommunity.plus/share');
  const info = ShareInfo(
    referralCode: '7Q2K9MXA',
    referralLink: 'https://futurefashion.test/r/7Q2K9MXA',
    apkDownloadUrl: 'https://futurefashion.test/download',
  );

  late List<MethodCall> apkCalls;
  late List<Map<Object?, Object?>> shared;

  void nativeAnswers(Object? Function(MethodCall call) answer) {
    messenger.setMockMethodCallHandler(apkChannel, (call) async {
      apkCalls.add(call);
      final value = answer(call);
      if (value is PlatformException) throw value;
      return value;
    });
  }

  setUp(() {
    apkCalls = [];
    shared = [];
    messenger.setMockMethodCallHandler(shareChannel, (call) async {
      shared.add(call.arguments as Map<Object?, Object?>);
      return 'com.whatsapp/.ContactPicker'; // the app the user picked
    });
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(apkChannel, null);
    messenger.setMockMethodCallHandler(shareChannel, null);
  });

  group('Share App + Referral', () {
    test('sends the APK file with the code built in, and no download link', () async {
      nativeAnswers(
        (_) => {'path': '/data/cache/apk_share/FutureFashion-1.0.0-7Q2K9MXA.apk', 'bytes': 58793920, 'withCode': true},
      );
      final status = await const ApkShareService().shareAppAndReferral(
        companyName: 'Future Fashion',
        info: info,
        appVersion: '1.0.0',
      );

      expect(status, ShareResultStatus.success);
      expect(apkCalls.single.method, 'prepareApk');
      expect(apkCalls.single.arguments, {'fileName': 'FutureFashion-1.0.0-7Q2K9MXA.apk', 'referralCode': '7Q2K9MXA'});
      final sheet = shared.single;
      expect(sheet['paths'], ['/data/cache/apk_share/FutureFashion-1.0.0-7Q2K9MXA.apk']);
      expect(sheet['mimeTypes'], [ApkShareService.apkMimeType]);
      expect(sheet['text'], contains('7Q2K9MXA fills itself in'));
      expect(sheet['text'], isNot(contains('Download the app')));
    });

    test('still sends the file when the code could not be built in', () async {
      nativeAnswers((_) => {'path': '/data/cache/apk_share/app.apk', 'bytes': 58793920, 'withCode': false});
      await const ApkShareService().shareAppAndReferral(companyName: 'Future Fashion', info: info, appVersion: '1.0.0');
      expect(shared.single['paths'], ['/data/cache/apk_share/app.apk']);
      expect(shared.single['text'], contains('Use my referral code 7Q2K9MXA'));
    });

    test('a store install made of parts is reported, never swapped for a link', () async {
      nativeAnswers((_) => PlatformException(code: 'SPLIT_INSTALL'));
      await expectLater(
        const ApkShareService().shareAppAndReferral(companyName: 'Future Fashion', info: info, appVersion: '1.0.0'),
        throwsA(isA<ApkUnavailable>().having((e) => e.reason, 'reason', ApkUnavailableReason.splitInstall)),
      );
      expect(shared, isEmpty);
    });

    test('a failed copy and a missing native helper are reported too', () async {
      nativeAnswers((_) => PlatformException(code: 'COPY_FAILED'));
      await expectLater(
        const ApkShareService().shareAppAndReferral(companyName: 'Future Fashion', info: info, appVersion: '1.0.0'),
        throwsA(isA<ApkUnavailable>().having((e) => e.reason, 'reason', ApkUnavailableReason.copyFailed)),
      );
      messenger.setMockMethodCallHandler(apkChannel, null);
      await expectLater(
        const ApkShareService().shareAppAndReferral(companyName: 'Future Fashion', info: info, appVersion: '1.0.0'),
        throwsA(isA<ApkUnavailable>().having((e) => e.reason, 'reason', ApkUnavailableReason.unsupported)),
      );
      expect(shared, isEmpty);
    });

    test('the link is its own, explicit share', () async {
      await const ApkShareService().shareLink(companyName: 'Future Fashion', info: info);
      expect(shared.single['text'], contains('https://futurefashion.test/r/7Q2K9MXA'));
      expect(shared.single['text'], contains('Download the app: https://futurefashion.test/download'));
      expect(shared.single.containsKey('paths'), isFalse);
    });
  });

  group('a code built into the installed APK', () {
    test('fills in signup on the first launch only', () async {
      final prefs = MemoryAppPrefs();
      nativeAnswers((_) => '7Q2K9MXA');
      await InstallReferral(prefs).load();
      expect(prefs.pendingReferralCode, '7Q2K9MXA');
      expect(prefs.installReferralChecked, isTrue);

      await prefs.setPendingReferralCode(null); // signed up; the code is used
      await InstallReferral(prefs).load();
      expect(prefs.pendingReferralCode, isNull);
      expect(apkCalls, hasLength(1));
    });

    test('never replaces a code from a link, and ignores anything that isn’t a code', () async {
      final fromLink = MemoryAppPrefs()..pendingReferralCode = 'K3M9P2QA';
      nativeAnswers((_) => '7Q2K9MXA');
      await InstallReferral(fromLink).load();
      expect(fromLink.pendingReferralCode, 'K3M9P2QA');

      final junk = MemoryAppPrefs();
      nativeAnswers((_) => '<script>');
      await InstallReferral(junk).load();
      expect(junk.pendingReferralCode, isNull);
      expect(junk.installReferralChecked, isTrue);
    });

    test('an APK without a code, or no native helper, fills in nothing', () async {
      final prefs = MemoryAppPrefs();
      nativeAnswers((_) => null);
      await InstallReferral(prefs).load();
      expect(prefs.pendingReferralCode, isNull);

      messenger.setMockMethodCallHandler(apkChannel, null);
      final other = MemoryAppPrefs();
      await InstallReferral(other).load();
      expect(other.pendingReferralCode, isNull);
      expect(other.installReferralChecked, isTrue);
    });
  });
}
