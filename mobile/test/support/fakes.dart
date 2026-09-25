import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/app/app.dart';
import 'package:future_fashion/core/api/api_exception.dart';
import 'package:future_fashion/core/api/future_fashion_api.dart';
import 'package:future_fashion/core/api/json.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/auth/token_store.dart';
import 'package:future_fashion/core/providers.dart';
import 'package:future_fashion/core/storage/prefs.dart';
import 'package:future_fashion/features/ads/ads.dart';
import 'package:future_fashion/features/apk_sharing/apk_share_service.dart';
import 'package:future_fashion/features/apk_sharing/share_screen.dart';
import 'package:share_plus/share_plus.dart';

/// Test data shaped exactly like docs/API.md. Clearly fake: only tests use it.
Json configJson({
  String serverNow = '2026-10-01T06:30:00Z',
  int verifiedCount = 18342,
  bool maintenance = false,
  String minVersion = '1.0.0',
  bool signupsOpen = true,
  bool adsOn = false,
  String? legalName,
  String? supportEmail,
  String? supportUrl,
  String? termsUrl,
  String? brandName,
  Json? announcement,
}) => {
  'server_now': serverNow,
  'company_name': 'Future Fashion',
  'company_legal_name': legalName,
  'support_email': supportEmail,
  'min_app_version': minVersion,
  'apk_download_url': 'https://futurefashion.test/download',
  'maintenance': {'active': maintenance, 'message': maintenance ? 'Back at 6 pm' : null, 'until': null},
  'campaign': {
    'status': 'ACTIVE',
    'starts_at': '2026-09-24T00:00:00Z',
    'ends_at': '2026-12-31T18:29:59Z',
    'brand_reveal_at': '2026-12-20T18:30:00Z',
    'launch_at': '2026-12-30T18:30:00Z',
    'payout_opens_at': '2026-12-30T18:30:00Z',
    'brand_name': brandName,
    'signups_open': signupsOpen,
    'rewards_open': true,
  },
  'rewards': {
    'levels': [
      {'level': 1, 'reward_per_user_paise': 20000},
      {'level': 2, 'reward_per_user_paise': 0},
      {'level': 3, 'reward_per_user_paise': 0},
      {'level': 4, 'reward_per_user_paise': 0},
    ],
    'min_withdrawal_paise': 20000,
  },
  'membership': {'verified_count': verifiedCount, 'capacity': 50000000},
  'promotion': {'allocation_paise': null},
  'announcement': announcement,
  'ads': {
    'banner_enabled': adsOn,
    'interstitial_enabled': adsOn,
    'rewarded_enabled': false,
    'min_interstitial_interval_seconds': 300,
  },
  'links': {'terms_url': termsUrl, 'privacy_url': null, 'support_url': supportUrl},
};

Json meJson({String status = 'ACTIVE'}) => {
  'public_id': '7Q2K9MXA',
  'phone_masked': '98XXXXXX10',
  'status': status,
  'referral_code': status == 'ACTIVE' ? '7Q2K9MXA' : null,
  'referred_by': null,
  'created_at': '2026-09-24T10:00:00Z',
  'verified_at': status == 'ACTIVE' ? '2026-09-24T10:06:00Z' : null,
};

Json tokensJson() => {
  'token_type': 'Bearer',
  'access_token': 'ffa_test',
  'access_expires_at': '2026-10-01T07:00:00Z',
  'refresh_token': 'ffr_test',
  'refresh_expires_at': '2026-10-31T07:00:00Z',
};

Json walletJson({bool payoutsOpen = false, int available = 0, int pending = 240000}) => {
  'total_earned_paise': 240000,
  'pending_paise': pending,
  'available_paise': available,
  'in_withdrawal_paise': 0,
  'withdrawn_paise': 0,
  'payouts_open': payoutsOpen,
  'payout_opens_at': '2026-12-30T18:30:00Z',
  'min_withdrawal_paise': 20000,
  'breakdown': [
    {'level': 1, 'reward_count': 12, 'amount_paise': 240000},
  ],
  'recent_entries': [
    {
      'id': 'TX-8K2M4QZA7B',
      'kind': 'REFERRAL_REWARD',
      'direction': 'CREDIT',
      'amount_paise': 20000,
      'created_at': '2026-09-30T09:04:00Z',
      'counterparty_public_id': 'K3M9P2QA',
    },
  ],
};

Json summaryJson() => {
  'generated_at': '2026-10-01T02:00:00Z',
  'refresh_pending': false,
  'levels': [
    {'level': 1, 'user_count': 12, 'reward_per_user_paise': 20000, 'total_reward_paise': 240000},
    {'level': 2, 'user_count': 40, 'reward_per_user_paise': 0, 'total_reward_paise': 0},
    {'level': 3, 'user_count': 95, 'reward_per_user_paise': 0, 'total_reward_paise': 0},
    {'level': 4, 'user_count': 180, 'reward_per_user_paise': 0, 'total_reward_paise': 0},
  ],
  'total_user_count': 327,
  'total_reward_paise': 240000,
  'level_1_pending_count': 3,
};

Json dashboardJson({int earned = 240000, int available = 0, int verified = 12, int pending = 3}) => {
  'user': meJson(),
  'wallet': {'total_earned_paise': earned, 'pending_paise': earned - available, 'available_paise': available},
  'referrals': {'level_1_count': verified, 'level_1_pending_count': pending},
  'share': {'referral_code': '7Q2K9MXA', 'referral_link': 'https://futurefashion.test/r/7Q2K9MXA'},
};

DirectReferral directReferral(String id, String status) => DirectReferral.fromJson({
  'public_id': id,
  'phone_masked': '98XXXXXX21',
  'status': status,
  'joined_at': '2026-09-20T09:00:00Z',
  'verified_at': status == 'VERIFIED' ? '2026-09-20T09:04:00Z' : null,
  'reward_paise': status == 'VERIFIED' ? 20000 : 0,
});

Withdrawal withdrawal(WithdrawalStatus status, {String? reference, String? reason}) => Withdrawal(
  id: 'WD-3JQ9TEST0${status.index}',
  amountPaise: 40000,
  status: status,
  bankAccountMasked: 'XXXX 4821',
  requestedAt: DateTime.utc(2026, 12, 31, 6),
  paidAt: status == WithdrawalStatus.paid ? DateTime.utc(2027, 1, 2, 6) : null,
  bankReference: reference,
  failureReason: reason,
);

/// Records URLs the app opens and what it copies, instead of leaving the test.
class DeviceRecorder {
  final opened = <String>[];
  String? clipboard;

  void install() {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/url_launcher'), (call) async {
      if (call.method == 'launch') opened.add((call.arguments as Map<Object?, Object?>)['url']! as String);
      return true;
    });
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') clipboard = (call.arguments as Map<Object?, Object?>)['text'] as String?;
      if (call.method == 'Clipboard.getData') return {'text': clipboard};
      return null;
    });
  }

  void uninstall() {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/url_launcher'), null);
    messenger.setMockMethodCallHandler(SystemChannels.platform, null);
  }
}

/// A scripted server. Each method returns what the test set up, and every
/// call is recorded so tests can assert what the app sent.
class FakeApi implements FutureFashionApi {
  final calls = <String>[];
  final _ended = StreamController<void>.broadcast();

  /// Endpoints that fail until the test removes them, by method name.
  final failures = <String, ApiException>{};

  /// While set, config() waits: the app stays on its splash screen.
  Completer<void>? configGate;

  Json summaryResponse = summaryJson();
  Json dashboardResponse = dashboardJson();
  List<DirectReferral> directItems = [directReferral('K3M9P2QA', 'VERIFIED')];
  int directPageSize = 20;
  List<Withdrawal> history = [];
  int captchas = 0;

  void _gate(String name) {
    final failure = failures[name];
    if (failure != null) throw failure;
  }

  Object configResponse = configJson();
  Me meResponse = Me.fromJson(meJson());
  Wallet walletResponse = Wallet.fromJson(walletJson());
  BankDetails bankResponse = const BankDetails(saved: false);
  VerificationSession sessionResponse = VerificationSession.fromJson({
    'status': 'OPEN',
    'bot_username': 'futurefashion_verify_01_bot',
    'deep_link': 'https://t.me/futurefashion_verify_01_bot?start=vs_x',
    'expires_at': '2026-10-01T07:00:00Z',
    'channel_count': 3,
    'issue': null,
  });
  ApiException? loginError;
  ApiException? signupError;
  final List<Object> withdrawalResults = [];
  final withdrawalKeys = <String>[];
  String? lastSignupKey;

  T _answer<T>(Object value) {
    if (value is ApiException) throw value;
    return value as T;
  }

  @override
  Stream<void> get sessionEnded => _ended.stream;

  void endSession() => _ended.add(null);

  @override
  Future<PublicConfig> config() async {
    calls.add('config');
    await configGate?.future;
    final value = configResponse;
    if (value is ApiException) throw value;
    return PublicConfig.fromJson(value as Json);
  }

  @override
  Future<Captcha> captcha() async {
    calls.add('captcha');
    _gate('captcha');
    captchas++;
    return Captcha(id: 'c_test_$captchas', question: captchas.isOdd ? '7 + 8 = ?' : '9 − 4 = ?');
  }

  @override
  Future<bool> referralCodeValid(String code) async {
    calls.add('referralCodeValid:$code');
    _gate('referralCodeValid');
    return code == 'K3M9P2QA';
  }

  @override
  Future<AuthResult> signup({
    required String phone,
    required String password,
    required String? referralCode,
    required String captchaId,
    required String captchaAnswer,
    required String idempotencyKey,
  }) async {
    calls.add('signup:$phone:${referralCode ?? '-'}');
    lastSignupKey = idempotencyKey;
    if (signupError != null) throw signupError!;
    meResponse = Me.fromJson(meJson(status: 'PENDING_VERIFICATION'));
    return AuthResult(meResponse, Tokens.fromJson(tokensJson()));
  }

  @override
  Future<AuthResult> login({
    required String phone,
    required String password,
    String? captchaId,
    String? captchaAnswer,
  }) async {
    calls.add('login:$phone:${captchaId ?? '-'}');
    if (loginError != null) throw loginError!;
    return AuthResult(meResponse, Tokens.fromJson(tokensJson()));
  }

  @override
  Future<void> logout() async => calls.add('logout');

  @override
  Future<Me> me() async {
    calls.add('me');
    _gate('me');
    return meResponse;
  }

  @override
  Future<VerificationSession> openVerification() async {
    calls.add('openVerification');
    _gate('openVerification');
    return sessionResponse;
  }

  @override
  Future<VerificationSession> verificationStatus() async {
    calls.add('verificationStatus');
    _gate('verificationStatus');
    return sessionResponse;
  }

  @override
  Future<Dashboard> dashboard() async {
    calls.add('dashboard');
    _gate('dashboard');
    return Dashboard.fromJson(dashboardResponse);
  }

  @override
  Future<ReferralSummary> referralSummary() async {
    calls.add('referralSummary');
    _gate('referralSummary');
    return ReferralSummary.fromJson(summaryResponse);
  }

  @override
  Future<Paged<DirectReferral>> directReferrals({String? cursor, int limit = 20}) async {
    calls.add('directReferrals');
    _gate('directReferrals');
    final start = cursor == null ? 0 : int.parse(cursor);
    final end = (start + directPageSize).clamp(0, directItems.length);
    return Paged(directItems.sublist(start, end), end < directItems.length ? '$end' : null);
  }

  @override
  Future<ShareInfo> shareInfo() async => const ShareInfo(
    referralCode: '7Q2K9MXA',
    referralLink: 'https://futurefashion.test/r/7Q2K9MXA',
    apkDownloadUrl: 'https://futurefashion.test/download',
  );

  @override
  Future<Wallet> wallet() async {
    calls.add('wallet');
    _gate('wallet');
    return walletResponse;
  }

  @override
  Future<BankDetails> bankDetails() async {
    calls.add('bankDetails');
    _gate('bankDetails');
    return bankResponse;
  }

  @override
  Future<BankDetails> saveBankDetails({
    required String accountHolderName,
    required String accountNumber,
    required String ifsc,
    required String idempotencyKey,
  }) async {
    calls.add('saveBank');
    _gate('saveBank');
    bankResponse = BankDetails(
      saved: true,
      accountHolderName: accountHolderName,
      accountNumberMasked: 'XXXX XXXX ${accountNumber.substring(accountNumber.length - 4)}',
      ifsc: ifsc,
    );
    return bankResponse;
  }

  @override
  Future<Paged<Withdrawal>> withdrawals({String? cursor, int limit = 20}) async {
    calls.add('withdrawals');
    _gate('withdrawals');
    return Paged(history, null);
  }

  @override
  Future<Withdrawal> requestWithdrawal({required int amountPaise, required String idempotencyKey}) async {
    calls.add('withdraw:$amountPaise');
    withdrawalKeys.add(idempotencyKey);
    final next = withdrawalResults.isEmpty ? null : withdrawalResults.removeAt(0);
    if (next != null) _answer<Object>(next);
    return Withdrawal(
      id: 'WD-3JQ9TEST01',
      amountPaise: amountPaise,
      status: WithdrawalStatus.requested,
      bankAccountMasked: 'XXXX 4821',
      requestedAt: DateTime.utc(2026, 12, 31, 6),
      paidAt: null,
      bankReference: null,
      failureReason: null,
    );
  }
}

/// An ad SDK that never became ready (no consent, no network, or it failed
/// to start), optionally also throwing when asked to show an ad.
class FakeAds implements AdsService {
  FakeAds({this.throwOnInterstitial = false});

  final bool throwOnInterstitial;
  int interstitialRequests = 0;

  @override
  bool get enabled => false;

  @override
  Future<void> initialize() async {}

  @override
  Future<void> maybeShowInterstitial(AdSettings settings) async {
    interstitialRequests++;
    if (throwOnInterstitial) throw StateError('ad SDK failure');
  }
}

/// Records what the share screen asked Android to send.
class FakeApkShare implements ApkShareService {
  ApkUnavailable? problem; // set to make attaching the file fail
  final sent = <String>[];

  @override
  Future<ShareResultStatus> shareAppAndReferral({
    required String companyName,
    required ShareInfo info,
    required String appVersion,
  }) async {
    if (problem != null) throw problem!;
    sent.add('apk-file:${info.referralCode}');
    return ShareResultStatus.success;
  }

  @override
  Future<void> shareLink({required String companyName, required ShareInfo info}) async =>
      sent.add('link:${info.referralCode}');
}

class TestEnv {
  TestEnv({FakeApi? api, this.ads, FakeApkShare? apkShare, bool signedIn = false, bool onboardingSeen = true})
    : api = api ?? FakeApi(),
      apkShare = apkShare ?? FakeApkShare(),
      tokens = MemoryTokenStore(),
      prefs = MemoryAppPrefs()..onboardingSeen = onboardingSeen {
    if (signedIn) tokens.tokens = Tokens.fromJson(tokensJson());
  }

  final FakeApi api;
  final AdsService? ads;
  final FakeApkShare apkShare;
  final MemoryTokenStore tokens;
  final MemoryAppPrefs prefs;

  Widget app() => ProviderScope(
    retry: (retryCount, error) => null,
    overrides: [
      apiProvider.overrideWithValue(api),
      tokenStoreProvider.overrideWithValue(tokens),
      prefsProvider.overrideWithValue(prefs),
      appVersionProvider.overrideWithValue('1.0.0'),
      if (ads != null) adsServiceProvider.overrideWithValue(ads!),
      apkShareServiceProvider.overrideWithValue(apkShare),
    ],
    child: const FutureFashionApp(),
  );
}

/// Phones where the user asked for reduced motion: also keeps tests from
/// waiting on decorative loops.
Future<void> pumpApp(WidgetTester tester, TestEnv env) async {
  tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(disableAnimations: true);
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.75;
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(env.app());
  await settle(tester);
}

/// pumpAndSettle can't be used with ticking countdowns; pump in steps instead.
Future<void> settle(WidgetTester tester, [int frames = 12]) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}
