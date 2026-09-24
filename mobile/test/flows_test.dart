import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/core/api/api_exception.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/widgets/buttons.dart';

import 'support/fakes.dart';

/// UI flows from CLAUDE.md §29, run against a scripted server (FakeApi).
void main() {
  Future<void> finish(WidgetTester tester) async {
    // Unmount so screen timers (countdown, verification polling) are cancelled.
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  }

  /// Screens are lazily built lists: scroll until [finder] exists, then show it.
  Future<Finder> reveal(WidgetTester tester, Finder finder) async {
    if (finder.evaluate().isEmpty) {
      final list = find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down);
      await tester.scrollUntilVisible(finder, 250, scrollable: list.last);
    }
    await tester.ensureVisible(finder.last);
    await tester.pump();
    return finder.last;
  }

  Future<void> tapText(WidgetTester tester, String text) async {
    await tester.tap(await reveal(tester, find.text(text)));
    await settle(tester);
  }

  testWidgets('offline start shows the connection screen, and retry recovers', (tester) async {
    final env = TestEnv();
    env.api.configResponse = const OfflineException();
    await pumpApp(tester, env);
    expect(find.text('Connection unavailable'), findsOneWidget);

    env.api.configResponse = configJson();
    await tapText(tester, 'Try again');
    expect(find.text('Welcome back'), findsOneWidget); // signed out → login
    await finish(tester);
  });

  testWidgets('maintenance mode blocks the app with the server message', (tester) async {
    final env = TestEnv();
    env.api.configResponse = configJson(maintenance: true);
    await pumpApp(tester, env);
    expect(find.textContaining('right back'), findsOneWidget);
    expect(find.textContaining('Back at 6 pm'), findsOneWidget);
    await finish(tester);
  });

  testWidgets('an app older than the minimum version must update', (tester) async {
    final env = TestEnv();
    env.api.configResponse = configJson(minVersion: '2.0.0');
    await pumpApp(tester, env);
    expect(find.text('Update required'), findsOneWidget);
    await finish(tester);
  });

  testWidgets('first launch shows onboarding', (tester) async {
    await pumpApp(tester, TestEnv(onboardingSeen: false));
    expect(find.text('A new fashion label is coming'), findsOneWidget);
    await finish(tester);
  });

  testWidgets('signup creates a pending account and opens Telegram verification', (tester) async {
    final env = TestEnv();
    await pumpApp(tester, env);
    await tapText(tester, 'Create an account');
    expect(find.text('Telegram verification is required'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Mobile number'), '9876543210');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'correct-horse-9');
    await tester.enterText(find.widgetWithText(TextField, 'Answer'), '15');
    await tapText(tester, 'Create account');

    expect(env.api.calls, contains('signup:9876543210:-'));
    expect(env.api.lastSignupKey, isNotNull);
    expect(env.tokens.tokens, isNotNull);
    expect(find.text('Verify with Telegram'), findsOneWidget);
    expect(find.text('JOIN 3'), findsOneWidget); // one small JOIN chip per channel
    await finish(tester);
  });

  testWidgets('signup validates before calling the server', (tester) async {
    final env = TestEnv();
    await pumpApp(tester, env);
    await tapText(tester, 'Create an account');
    await tester.enterText(find.widgetWithText(TextField, 'Mobile number'), '12345');
    await tapText(tester, 'Create account');
    expect(find.text('Enter your 10-digit mobile number.'), findsOneWidget);
    expect(env.api.calls.where((c) => c.startsWith('signup')), isEmpty);
    await finish(tester);
  });

  testWidgets('login shows one generic error for wrong details', (tester) async {
    final env = TestEnv();
    env.api.loginError = const ServerRejection(
      status: 401,
      code: 'INVALID_CREDENTIALS',
      message: 'Phone number or password is incorrect.',
    );
    await pumpApp(tester, env);
    await tester.enterText(find.widgetWithText(TextField, 'Mobile number'), '9876543210');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'wrong-password');
    await tapText(tester, 'Log in');
    expect(find.text('Phone number or password is incorrect.'), findsOneWidget);

    env.api.loginError = null;
    await tapText(tester, 'Log in');
    expect(find.textContaining('Our Big Launch.'), findsOneWidget);
    await finish(tester);
  });

  testWidgets('login asks for the check after repeated failures', (tester) async {
    final env = TestEnv();
    env.api.loginError = const ServerRejection(
      status: 400,
      code: 'CAPTCHA_REQUIRED',
      message: 'Please solve the check.',
    );
    await pumpApp(tester, env);
    await tester.enterText(find.widgetWithText(TextField, 'Mobile number'), '9876543210');
    await tester.enterText(find.widgetWithText(TextField, 'Password'), 'whatever-1');
    await tapText(tester, 'Log in');
    expect(find.text('7 + 8 = ?'), findsOneWidget);
    await finish(tester);
  });

  testWidgets('home shows the real member count and campaign dates', (tester) async {
    final env = TestEnv(signedIn: true);
    await pumpApp(tester, env);
    expect(find.textContaining('Our Big Launch.'), findsOneWidget);
    expect(await reveal(tester, find.text('LAUNCH IN')), findsOneWidget);
    expect(await reveal(tester, find.text('21 December')), findsOneWidget);
    expect(await reveal(tester, find.text('18,342')), findsOneWidget); // exactly the server's number
    expect(await reveal(tester, find.text('Start Referring')), findsOneWidget);
    await finish(tester);
  });

  testWidgets('referral dashboard shows four levels: ₹200 then ₹0', (tester) async {
    await pumpApp(tester, TestEnv(signedIn: true));
    await tapText(tester, 'Referrals');
    for (final level in [1, 2, 3, 4]) {
      expect(await reveal(tester, find.text('Level $level')), findsOneWidget);
    }
    expect(find.text('₹200'), findsOneWidget); // level 1 reward per user
    expect(find.text('₹2,400'), findsNWidgets(2)); // level 1 total and grand total
    expect(find.text('₹0'), findsNWidgets(6)); // levels 2–4, both columns
    expect(await reveal(tester, find.textContaining('Only direct referrals (level 1) earn rewards')), findsOneWidget);
    await finish(tester);
  });

  testWidgets('wallet shows ledger figures and blocks withdrawing before the payout date', (tester) async {
    final env = TestEnv(signedIn: true);
    await pumpApp(tester, env);
    await tapText(tester, 'Wallet');
    expect(find.text('₹2,400'), findsWidgets);
    expect(
      await reveal(tester, find.textContaining('Rewards become withdrawable on 31 December 2026')),
      findsOneWidget,
    );
    await reveal(tester, find.widgetWithText(PrimaryButton, 'Withdraw'));
    expect(tester.widget<PrimaryButton>(find.widgetWithText(PrimaryButton, 'Withdraw')).onPressed, isNull);
    await finish(tester);
  });

  testWidgets('withdrawal: review, confirm, safe retry, and success only after the server agrees', (tester) async {
    final env = TestEnv(signedIn: true);
    env.api.walletResponse = Wallet.fromJson(walletJson(payoutsOpen: true, available: 240000, pending: 0));
    env.api.bankResponse = const BankDetails(
      saved: true,
      accountHolderName: 'Ravi Kumar',
      accountNumberMasked: 'XXXX XXXX 4821',
      ifsc: 'HDFC0001234',
    );
    env.api.withdrawalResults.add(const OfflineException()); // the first confirm never reaches the server
    await pumpApp(tester, env);
    await tapText(tester, 'Wallet');
    await tapText(tester, 'Withdraw');
    await tapText(tester, 'Review withdrawal');
    expect(find.text('Review and confirm'), findsOneWidget);

    await tapText(tester, 'Confirm withdrawal');
    expect(find.text('Withdrawal requested'), findsNothing);
    expect(find.textContaining('Tap Confirm again to retry safely'), findsOneWidget);

    await tapText(tester, 'Confirm withdrawal');
    expect(find.text('Withdrawal requested'), findsOneWidget);
    expect(env.api.withdrawalKeys, hasLength(2));
    expect(env.api.withdrawalKeys.toSet(), hasLength(1)); // same key both times
    expect(env.api.calls.where((c) => c == 'withdraw:240000'), hasLength(2));
    await finish(tester);
  });

  testWidgets('verification completes when the server says so', (tester) async {
    final env = TestEnv(signedIn: true);
    env.api.meResponse = Me.fromJson(meJson(status: 'PENDING_VERIFICATION'));
    await pumpApp(tester, env);
    expect(find.text('Verify with Telegram'), findsOneWidget);

    env.api.sessionResponse = VerificationSession.fromJson({
      'status': 'COMPLETED',
      'bot_username': 'futurefashion_verify_01_bot',
      'deep_link': null,
      'expires_at': '2026-10-01T07:00:00Z',
      'channel_count': 3,
      'issue': null,
    });
    env.api.meResponse = Me.fromJson(meJson());
    await tapText(tester, 'I’ve finished — check again');
    expect(find.text('Verification complete'), findsOneWidget);
    await tapText(tester, 'Continue');
    expect(find.textContaining('Our Big Launch.'), findsOneWidget);
    await finish(tester);
  });

  testWidgets('logout ends the session on this phone only', (tester) async {
    final env = TestEnv(signedIn: true);
    await pumpApp(tester, env);
    await tapText(tester, 'Profile');
    await tapText(tester, 'Log out');
    await tapText(tester, 'Log out'); // confirm in the dialog
    expect(find.text('Welcome back'), findsOneWidget);
    expect(env.api.calls, contains('logout'));
    expect(env.tokens.tokens, isNull);
    await finish(tester);
  });

  testWidgets('a session ended by the server returns to login with a notice', (tester) async {
    final env = TestEnv(signedIn: true);
    await pumpApp(tester, env);
    env.api.endSession();
    await settle(tester);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.text('Your session has ended. Please log in again.'), findsOneWidget);
    await finish(tester);
  });
}
