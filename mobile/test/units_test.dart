import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/app/redirect.dart';
import 'package:future_fashion/core/api/api_exception.dart';
import 'package:future_fashion/core/api/json.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/auth/session_controller.dart';
import 'package:future_fashion/core/config/config_controller.dart';
import 'package:future_fashion/core/deep_links/referral_links.dart';
import 'package:future_fashion/core/formatters/dates.dart';
import 'package:future_fashion/core/formatters/inr.dart';
import 'package:future_fashion/core/security/idempotency.dart';

import 'support/fakes.dart';

void main() {
  group('INR formatting (integer paise, Indian grouping)', () {
    test('formats whole rupees and paise', () {
      expect(formatPaise(0), '₹0');
      expect(formatPaise(20000), '₹200');
      expect(formatPaise(1250000), '₹12,500');
      expect(formatPaise(1234550), '₹12,345.50');
      expect(formatPaise(5), '₹0.05');
      expect(formatPaise(-20000), '-₹200');
      expect(formatPaise(1000000000000), '₹10,00,00,00,000');
    });

    test('groups counts the Indian way', () {
      expect(groupIndian(11577956), '1,15,77,956');
      expect(groupIndian(50000000), '5,00,00,000');
      expect(groupIndian(999), '999');
      expect(groupIndian(1000), '1,000');
    });

    test('parses typed amounts without floating point', () {
      expect(parseRupeesToPaise('2,400'), 240000);
      expect(parseRupeesToPaise('₹200.5'), 20050);
      expect(parseRupeesToPaise('0.07'), 7);
      expect(parseRupeesToPaise('12.345'), isNull);
      expect(parseRupeesToPaise('-5'), isNull);
      expect(parseRupeesToPaise('abc'), isNull);
    });
  });

  test('countdown parts clamp at zero', () {
    final parts = CountdownParts.from(const Duration(days: 2, hours: 3, minutes: 4, seconds: 5));
    expect([parts.days, parts.hours, parts.minutes, parts.seconds], [2, 3, 4, 5]);
    expect(CountdownParts.from(const Duration(seconds: -10)).isZero, isTrue);
  });

  test('IST display shifts UTC by 5:30', () {
    expect(formatIstDayMonth(DateTime.utc(2026, 12, 30, 18, 30)), '31 December');
  });

  test('idempotency keys are random UUID v4s', () {
    final a = newIdempotencyKey();
    expect(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$').hasMatch(a), isTrue);
    expect(newIdempotencyKey(), isNot(a));
  });

  group('referral codes', () {
    test('normalise pasted codes', () {
      expect(normalizeReferralCode(' 7q2k 9mxa '), '7Q2K9MXA');
      expect(normalizeReferralCode('O0I1L5UA'), isNull);
      expect(normalizeReferralCode('SHORT'), isNull);
    });

    test('read codes from links only on our host', () {
      expect(referralCodeFromUri(Uri.parse('futurefashion://r/7Q2K9MXA')), '7Q2K9MXA');
      expect(referralCodeFromUri(Uri.parse('https://dev.futurefashion.example/r/7q2k9mxa')), '7Q2K9MXA');
      expect(referralCodeFromUri(Uri.parse('https://evil.example/r/7Q2K9MXA')), isNull);
    });
  });

  group('models are strict', () {
    test('config parses the documented shape', () {
      final cfg = PublicConfig.fromJson(configJson());
      expect(cfg.level1RewardPaise, 20000);
      expect(cfg.levels.map((l) => l.rewardPerUserPaise), [20000, 0, 0, 0]);
      expect(cfg.verifiedCount, 18342);
    });

    test('a fractional amount is rejected, not rounded', () {
      final bad = walletJson()..['available_paise'] = 200.5;
      expect(() => Wallet.fromJson(bad), throwsFormatException);
    });

    test('unknown statuses are rejected', () {
      final me = meJson()..['status'] = 'VIP';
      expect(() => Me.fromJson(me), throwsFormatException);
    });
  });

  group('versions', () {
    test('compares numerically', () {
      expect(isOlderVersion('1.2.0', '1.10.0'), isTrue);
      expect(isOlderVersion('1.10.0', '1.2.0'), isFalse);
      expect(isOlderVersion('1.0.0', '1.0.0'), isFalse);
      expect(isOlderVersion('1.0', '1.0.1'), isTrue);
      expect(isOlderVersion('garbage', '1.0.0'), isFalse);
    });
  });

  group('redirect rules', () {
    final ok = AsyncData(ConfigState(PublicConfig.fromJson(configJson()), Duration.zero));
    AsyncValue<Session> signedIn(String status) => AsyncData(SignedIn(Me.fromJson(meJson(status: status))));
    String? decide({
      AsyncValue<ConfigState>? config,
      AsyncValue<Session>? session,
      String location = '/home',
      bool onboardingSeen = true,
      String version = '1.0.0',
    }) => decideRedirect(
      config: config ?? ok,
      session: session ?? signedIn('ACTIVE'),
      onboardingSeen: onboardingSeen,
      appVersion: version,
      location: location,
    );

    test('waits on the splash while loading', () {
      expect(decide(config: const AsyncLoading(), location: '/home'), '/splash');
      expect(decide(session: const AsyncLoading(), location: '/splash'), isNull);
    });

    test('system states win', () {
      expect(decide(config: const AsyncError(OfflineException(), StackTrace.empty)), '/offline');
      expect(decide(config: const AsyncError(MaintenanceException(null, null), StackTrace.empty)), '/maintenance');
      expect(decide(config: AsyncData(ConfigState(PublicConfig.fromJson(configJson(maintenance: true)), Duration.zero))), '/maintenance');
      expect(decide(version: '0.9.0'), '/upgrade');
    });

    test('signed-out users see onboarding once, then login', () {
      expect(decide(session: const AsyncData(SignedOut()), onboardingSeen: false), '/onboarding');
      expect(decide(session: const AsyncData(SignedOut())), '/login');
      expect(decide(session: const AsyncData(SignedOut()), location: '/signup'), isNull);
      expect(decide(session: const AsyncData(SignedOut()), location: '/terms'), isNull);
    });

    test('pending accounts can only verify', () {
      expect(decide(session: signedIn('PENDING_VERIFICATION'), location: '/wallet'), '/verify');
      expect(decide(session: signedIn('PENDING_VERIFICATION'), location: '/verify'), isNull);
      expect(decide(session: signedIn('PENDING_VERIFICATION'), location: '/rules'), isNull);
    });

    test('verified accounts leave auth screens, and see success once after verifying', () {
      expect(decide(location: '/login'), '/home');
      expect(decide(location: '/splash'), '/home');
      expect(decide(location: '/verify'), '/verify/success');
      expect(decide(location: '/verify/success'), isNull);
      expect(decide(location: '/wallet'), isNull);
    });

    test('suspended accounts are held on one screen', () {
      expect(decide(session: signedIn('SUSPENDED'), location: '/home'), '/suspended');
    });
  });

  test('json readers name the missing field', () {
    const Json j = {'a': 'x'};
    expect(() => j.integer('a'), throwsA(isA<FormatException>().having((e) => e.message, 'message', contains('"a"'))));
  });
}
