import 'dart:async';

import 'package:flutter/material.dart';
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

/// Test data shaped exactly like docs/API.md. Clearly fake: only tests use it.
Json configJson({
  String serverNow = '2026-10-01T06:30:00Z',
  int verifiedCount = 18342,
  bool maintenance = false,
  String minVersion = '1.0.0',
  bool signupsOpen = true,
}) => {
  'server_now': serverNow,
  'company_name': 'Future Fashion',
  'company_legal_name': null,
  'support_email': null,
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
    'brand_name': null,
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
  'announcement': null,
  'ads': {
    'banner_enabled': false,
    'interstitial_enabled': false,
    'rewarded_enabled': false,
    'min_interstitial_interval_seconds': 300,
  },
  'links': {'terms_url': null, 'privacy_url': null, 'support_url': null},
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

/// A scripted server. Each method returns what the test set up, and every
/// call is recorded so tests can assert what the app sent.
class FakeApi implements FutureFashionApi {
  final calls = <String>[];
  final _ended = StreamController<void>.broadcast();

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
    final value = configResponse;
    if (value is ApiException) throw value;
    return PublicConfig.fromJson(value as Json);
  }

  @override
  Future<Captcha> captcha() async {
    calls.add('captcha');
    return const Captcha(id: 'c_test', question: '7 + 8 = ?');
  }

  @override
  Future<bool> referralCodeValid(String code) async {
    calls.add('referralCodeValid:$code');
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
    return meResponse;
  }

  @override
  Future<VerificationSession> openVerification() async {
    calls.add('openVerification');
    return sessionResponse;
  }

  @override
  Future<VerificationSession> verificationStatus() async {
    calls.add('verificationStatus');
    return sessionResponse;
  }

  @override
  Future<Dashboard> dashboard() async {
    calls.add('dashboard');
    return Dashboard.fromJson({
      'user': meJson(),
      'wallet': {'total_earned_paise': 240000, 'pending_paise': 240000, 'available_paise': 0},
      'referrals': {'level_1_count': 12, 'level_1_pending_count': 3},
      'share': {'referral_code': '7Q2K9MXA', 'referral_link': 'https://futurefashion.test/r/7Q2K9MXA'},
    });
  }

  @override
  Future<ReferralSummary> referralSummary() async {
    calls.add('referralSummary');
    return ReferralSummary.fromJson(summaryJson());
  }

  @override
  Future<Paged<DirectReferral>> directReferrals({String? cursor, int limit = 20}) async {
    calls.add('directReferrals');
    return Paged([
      DirectReferral.fromJson({
        'public_id': 'K3M9P2QA',
        'phone_masked': '98XXXXXX21',
        'status': 'VERIFIED',
        'joined_at': '2026-09-20T09:00:00Z',
        'verified_at': '2026-09-20T09:04:00Z',
        'reward_paise': 20000,
      }),
    ], null);
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
    return walletResponse;
  }

  @override
  Future<BankDetails> bankDetails() async {
    calls.add('bankDetails');
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
    bankResponse = BankDetails(
      saved: true,
      accountHolderName: accountHolderName,
      accountNumberMasked: 'XXXX XXXX ${accountNumber.substring(accountNumber.length - 4)}',
      ifsc: ifsc,
    );
    return bankResponse;
  }

  @override
  Future<Paged<Withdrawal>> withdrawals({String? cursor, int limit = 20}) async => const Paged([], null);

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

class TestEnv {
  TestEnv({FakeApi? api, bool signedIn = false, bool onboardingSeen = true})
    : api = api ?? FakeApi(),
      tokens = MemoryTokenStore(),
      prefs = MemoryAppPrefs()..onboardingSeen = onboardingSeen {
    if (signedIn) tokens.tokens = Tokens.fromJson(tokensJson());
  }

  final FakeApi api;
  final MemoryTokenStore tokens;
  final MemoryAppPrefs prefs;

  Widget app() => ProviderScope(
    retry: (retryCount, error) => null,
    overrides: [
      apiProvider.overrideWithValue(api),
      tokenStoreProvider.overrideWithValue(tokens),
      prefsProvider.overrideWithValue(prefs),
      appVersionProvider.overrideWithValue('1.0.0'),
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
