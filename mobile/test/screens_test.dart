import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/app/app.dart';
import 'package:future_fashion/app/router.dart';
import 'package:future_fashion/core/api/api_exception.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/widgets/buttons.dart';
import 'package:go_router/go_router.dart';

import 'support/fakes.dart';

/// Every screen, and every button on it, against the scripted server.
/// UI flows that cross several screens live in flows_test.dart.
void main() {
  late DeviceRecorder device;
  setUp(() {
    (device = DeviceRecorder()).install();
    // Each test runs in its own fake-async zone; an asset Future cached by an
    // earlier test would never complete in this one.
    rootBundle.clear();
  });
  tearDown(() => device.uninstall());

  Future<void> finish(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  }

  /// Screens are lazily built lists: scroll (down, then up) until [finder]
  /// exists, then show it.
  Future<Finder> reveal(WidgetTester tester, Finder finder) async {
    if (finder.evaluate().isEmpty) {
      final list = find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down).last;
      try {
        await tester.scrollUntilVisible(finder, 250, scrollable: list);
      } on StateError {
        await tester.scrollUntilVisible(finder, -250, scrollable: list); // it was above
      }
    }
    await tester.ensureVisible(finder.last);
    await tester.pump();
    return finder.last;
  }

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await tester.tap(await reveal(tester, finder));
    await settle(tester);
  }

  Future<void> tapText(WidgetTester tester, String text) => tap(tester, find.text(text));

  GoRouter router(WidgetTester tester) =>
      ProviderScope.containerOf(tester.element(find.byType(FutureFashionApp))).read(routerProvider);

  /// The screen on top, including ones opened with push (which the URL doesn't show).
  String here(WidgetTester tester) => router(tester).routerDelegate.currentConfiguration.last.matchedLocation;

  Future<void> open(WidgetTester tester, String location) async {
    unawaited(router(tester).push(location));
    await settle(tester);
  }

  Future<void> back(WidgetTester tester) async {
    await tester.pageBack();
    await settle(tester);
  }

  Future<void> type(WidgetTester tester, String field, String text) async {
    await tester.enterText(await reveal(tester, find.widgetWithText(TextField, field)), text);
    await tester.pump();
  }

  PrimaryButton primary(WidgetTester tester, String label) =>
      tester.widget<PrimaryButton>(find.widgetWithText(PrimaryButton, label));

  group('system screens', () {
    testWidgets('the splash shows while the server is asked, then moves on', (tester) async {
      final env = TestEnv()..api.configGate = Completer<void>();
      await pumpApp(tester, env);
      expect(find.text('Referral rewards for our launch'), findsOneWidget);
      env.api.configGate!.complete();
      await settle(tester);
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('maintenance: Try again leaves once the server is back', (tester) async {
      final env = TestEnv()..api.configResponse = configJson(maintenance: true);
      await pumpApp(tester, env);
      expect(find.text("We'll be right back"), findsOneWidget);
      await tapText(tester, 'Try again');
      expect(find.text("We'll be right back"), findsOneWidget); // still down
      env.api.configResponse = configJson();
      await tapText(tester, 'Try again');
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('update required: Download opens the APK link, Check again re-checks', (tester) async {
      final env = TestEnv()..api.configResponse = configJson(minVersion: '2.0.0');
      await pumpApp(tester, env);
      await tapText(tester, 'Download the update');
      expect(device.opened, ['https://futurefashion.test/download']);
      env.api.configResponse = configJson();
      await tapText(tester, 'Check again');
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('suspended: Contact support emails support, Log out signs out', (tester) async {
      final env = TestEnv(signedIn: true);
      env.api.meResponse = Me.fromJson(meJson(status: 'SUSPENDED'));
      env.api.configResponse = configJson(supportEmail: 'help@futurefashion.test');
      await pumpApp(tester, env);
      expect(find.text('Account suspended'), findsOneWidget);
      await tapText(tester, 'Contact support');
      expect(device.opened.single, startsWith('mailto:help@futurefashion.test'));
      await tapText(tester, 'Log out');
      expect(find.text('Welcome back'), findsOneWidget);
      expect(env.api.calls, contains('logout'));
      await finish(tester);
    });
  });

  group('onboarding', () {
    testWidgets('Next walks the panels, and Create account opens signup once', (tester) async {
      final env = TestEnv(onboardingSeen: false);
      await pumpApp(tester, env);
      expect(find.text('A new fashion label is coming'), findsOneWidget);
      await tapText(tester, 'Next');
      await tapText(tester, 'Next');
      expect(find.text('Next'), findsNothing);
      await tapText(tester, 'Create account');
      expect(find.text('Telegram verification is required'), findsOneWidget);
      expect(env.prefs.onboardingSeen, isTrue);
      await finish(tester);
    });

    testWidgets('Skip opens signup', (tester) async {
      final env = TestEnv(onboardingSeen: false);
      await pumpApp(tester, env);
      await tapText(tester, 'Skip');
      expect(here(tester), '/signup');
      expect(env.prefs.onboardingSeen, isTrue);
      await finish(tester);
    });

    testWidgets('I already have an account opens login', (tester) async {
      await pumpApp(tester, TestEnv(onboardingSeen: false));
      await tapText(tester, 'I already have an account');
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });
  });

  group('login', () {
    testWidgets('checks the form, and links to password help, support and signup', (tester) async {
      final env = TestEnv();
      await pumpApp(tester, env);
      await tapText(tester, 'Log in');
      expect(find.text('Enter your 10-digit mobile number.'), findsOneWidget);
      expect(find.text('Enter your password.'), findsOneWidget);
      expect(env.api.calls.where((c) => c.startsWith('login')), isEmpty);

      await tapText(tester, 'Forgot password?');
      expect(find.textContaining('Contact support from the Support page'), findsOneWidget);

      await tapText(tester, 'Support');
      expect(find.text('My friend signed up but I see no reward'), findsOneWidget);
      await back(tester);

      await tapText(tester, 'Create an account');
      expect(here(tester), '/signup');
      await finish(tester);
    });

    testWidgets('New question swaps the check for another one', (tester) async {
      final env = TestEnv();
      env.api.loginError = const ServerRejection(status: 400, code: 'CAPTCHA_REQUIRED', message: 'Solve the check.');
      await pumpApp(tester, env);
      await type(tester, 'Mobile number', '9876543210');
      await type(tester, 'Password', 'whatever-1');
      await tapText(tester, 'Log in');
      expect(find.text('7 + 8 = ?'), findsOneWidget);
      await tap(tester, find.byTooltip('New question'));
      expect(find.text('9 − 4 = ?'), findsOneWidget);
      expect(env.api.captchas, 2);
      await finish(tester);
    });
  });

  group('signup', () {
    testWidgets('links to the terms, reward rules, privacy notice and login', (tester) async {
      await pumpApp(tester, TestEnv());
      await tapText(tester, 'Create an account');
      await tapText(tester, 'Terms');
      expect(here(tester), '/terms');
      await back(tester);
      await tapText(tester, 'Reward rules');
      expect(find.text('Levels 2–4 pay ₹0'), findsOneWidget);
      await back(tester);
      await tapText(tester, 'Privacy notice');
      expect(here(tester), '/privacy');
      await back(tester);
      await tapText(tester, 'Log in');
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('referral code: paste, a valid code, a wrong one, and no connection', (tester) async {
      final env = TestEnv();
      device.clipboard = ' k3m9 p2qa ';
      await pumpApp(tester, env);
      await tapText(tester, 'Create an account');
      await tap(tester, find.byTooltip('Paste code'));
      expect(find.text('K3M9P2QA'), findsOneWidget);
      expect(find.text('Valid referral code'), findsOneWidget);

      await type(tester, 'Referral code (optional)', 'ZZZZZZZZ');
      FocusManager.instance.primaryFocus?.unfocus();
      await settle(tester);
      expect(find.text("This code isn't valid"), findsOneWidget);

      env.api.failures['referralCodeValid'] = const OfflineException();
      await type(tester, 'Referral code (optional)', 'K3M9P2QA');
      FocusManager.instance.primaryFocus?.unfocus();
      await settle(tester);
      expect(find.text("Couldn't check the code now"), findsOneWidget);
      await finish(tester);
    });

    testWidgets('a number that already has an account offers Log in instead', (tester) async {
      final env = TestEnv();
      env.api.signupError = const ServerRejection(
        status: 409,
        code: 'PHONE_UNAVAILABLE',
        message: 'This number can’t be used to sign up. Try logging in instead.',
      );
      await pumpApp(tester, env);
      await tapText(tester, 'Create an account');
      await type(tester, 'Mobile number', '9876543210');
      await type(tester, 'Password', 'correct-horse-9');
      await type(tester, 'Answer', '15');
      await tapText(tester, 'Create account');
      await tapText(tester, 'Log in instead');
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('when sign-ups are closed, Create account is disabled and says why', (tester) async {
      final env = TestEnv()..api.configResponse = configJson(signupsOpen: false);
      await pumpApp(tester, env);
      await tapText(tester, 'Create an account');
      expect(find.text('Sign-ups are closed right now. Please check back later.'), findsOneWidget);
      await reveal(tester, find.widgetWithText(PrimaryButton, 'Create account'));
      expect(primary(tester, 'Create account').onPressed, isNull);
      await finish(tester);
    });
  });

  group('Telegram verification', () {
    TestEnv pending() => TestEnv(signedIn: true)..api.meResponse = Me.fromJson(meJson(status: 'PENDING_VERIFICATION'));

    VerificationSession session(
      String status, {
      String? issue,
      String? link = 'https://t.me/ff_verify_bot?start=vs_x',
    }) => VerificationSession.fromJson({
      'status': status,
      'bot_username': 'ff_verify_bot',
      'deep_link': link,
      'expires_at': '2026-10-01T07:00:00Z',
      'channel_count': 3,
      'issue': issue,
    });

    testWidgets('Open Telegram opens the bot link; check again asks the server', (tester) async {
      final env = pending();
      env.api.sessionResponse = session('OPEN');
      await pumpApp(tester, env);
      await tapText(tester, 'Open Telegram');
      expect(device.opened, ['https://t.me/ff_verify_bot?start=vs_x']);
      final before = env.api.calls.where((c) => c == 'verificationStatus').length;
      await tapText(tester, 'I’ve finished — check again');
      expect(env.api.calls.where((c) => c == 'verificationStatus').length, before + 1);
      await finish(tester);
    });

    testWidgets('each problem Telegram reports is explained', (tester) async {
      final env = pending();
      env.api.sessionResponse = session('OPEN');
      await pumpApp(tester, env);
      const explanations = {
        'CHANNELS_MISSING': 'Some channels don’t have a join request yet',
        'PHONE_MISMATCH': 'doesn’t match 98XXXXXX10',
        'TELEGRAM_ALREADY_LINKED': 'already linked to another account',
        'PHONE_MISMATCH_LIMIT': 'Too many numbers didn’t match',
      };
      for (final MapEntry(key: issue, value: text) in explanations.entries) {
        env.api.sessionResponse = session('IN_PROGRESS', issue: issue);
        await tapText(tester, 'I’ve finished — check again');
        expect(find.textContaining(text), findsOneWidget, reason: issue);
      }
      await finish(tester);
    });

    testWidgets('an expired link says so, and Get a new link replaces it', (tester) async {
      final env = pending();
      env.api.sessionResponse = session('EXPIRED', link: null);
      await pumpApp(tester, env);
      expect(await reveal(tester, find.text('This link expired')), findsOneWidget);
      env.api.sessionResponse = session('OPEN');
      await tapText(tester, 'Get a new link');
      expect(env.api.calls.where((c) => c == 'openVerification'), hasLength(2));
      expect(find.text('Open Telegram'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('Log out from the verification screen', (tester) async {
      final env = pending();
      await pumpApp(tester, env);
      await tapText(tester, 'Log out');
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });
  });

  group('home', () {
    testWidgets('every button and card goes where it says', (tester) async {
      final env = TestEnv(signedIn: true);
      await pumpApp(tester, env);
      await tapText(tester, '7Q2K9MXA');
      expect(device.clipboard, '7Q2K9MXA');
      expect(find.text('Referral code copied'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5)); // let the message go before tapping below it
      await settle(tester);

      await tapText(tester, 'Start Referring');
      expect(here(tester), '/share');
      await back(tester);
      await tapText(tester, 'How It Works');
      expect(await reveal(tester, find.text('Your referral tree')), findsOneWidget);
      await back(tester);
      await tapText(tester, 'Verified members so far');
      expect(find.text('Campaign capacity: 5,00,00,000 members'), findsOneWidget);
      await back(tester);
      await tapText(tester, 'Friends verified');
      expect(here(tester), '/wallet');
      await finish(tester);
    });

    testWidgets('an announcement from the admin shows at the top', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.configResponse = configJson(announcement: {'text': 'Brand reveal on 21 December!', 'tone': 'info'});
      await pumpApp(tester, env);
      expect(find.text('Brand reveal on 21 December!'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('after launch: the celebration shows once, then the campaign countdown', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.configResponse = configJson(serverNow: '2026-12-31T06:00:00Z', brandName: 'Maison Secret');
      await pumpApp(tester, env);
      expect(find.text('Welcome to Maison Secret'), findsOneWidget);
      expect(env.prefs.launchCelebrated, isTrue);
      await tapText(tester, 'Continue');
      expect(here(tester), '/home');
      expect(await reveal(tester, find.text('CAMPAIGN ENDS IN')), findsOneWidget);
      await finish(tester);
    });
  });

  group('referrals', () {
    testWidgets('Invite more friends, the level 1 list, and See all', (tester) async {
      await pumpApp(tester, TestEnv(signedIn: true));
      await tapText(tester, 'Referrals');
      await tapText(tester, 'Invite more friends');
      expect(here(tester), '/share');
      await back(tester);
      await tapText(tester, 'Level 1 — your direct referrals');
      expect(await reveal(tester, find.textContaining('ID K3M9P2QA')), findsOneWidget);
      await tapText(tester, 'See all direct referrals');
      expect(here(tester), '/referrals/direct');
      await finish(tester);
    });

    testWidgets('the direct list pages with Load more, and says when it’s empty', (tester) async {
      final env = TestEnv(signedIn: true);
      env.api.directItems = [for (var i = 10; i < 35; i++) directReferral('REF000$i', 'VERIFIED')];
      await pumpApp(tester, env);
      await open(tester, '/referrals/direct');
      expect(find.textContaining('ID REF00034'), findsNothing);
      await tapText(tester, 'Load more');
      expect(await reveal(tester, find.textContaining('ID REF00034')), findsOneWidget);
      expect(find.text('Load more'), findsNothing);

      env.api.directItems = [];
      await back(tester);
      await open(tester, '/referrals/direct');
      expect(find.text('No direct referrals yet'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('a table being refreshed says so, and errors offer Try again', (tester) async {
      final env = TestEnv(signedIn: true);
      env.api.summaryResponse = {...summaryJson(), 'refresh_pending': true};
      env.api.failures['referralSummary'] = const OfflineException();
      await pumpApp(tester, env);
      await tapText(tester, 'Referrals');
      expect(find.text('Try again'), findsOneWidget);
      env.api.failures.remove('referralSummary');
      await tapText(tester, 'Try again');
      expect(await reveal(tester, find.textContaining('A newer count is being prepared')), findsOneWidget);
      await finish(tester);
    });
  });

  group('wallet', () {
    testWidgets('Bank details, History and Withdraw open their screens', (tester) async {
      final env = TestEnv(signedIn: true);
      env.api.walletResponse = Wallet.fromJson(walletJson(payoutsOpen: true, available: 240000, pending: 0));
      await pumpApp(tester, env);
      await tapText(tester, 'Wallet');
      await tapText(tester, 'Bank details');
      expect(here(tester), '/wallet/bank');
      await back(tester);
      await tapText(tester, 'History');
      expect(here(tester), '/wallet/history');
      await back(tester);
      await tap(tester, find.widgetWithText(PrimaryButton, 'Withdraw'));
      expect(here(tester), '/wallet/withdraw');
      await finish(tester);
    });

    testWidgets('recent activity lists ledger entries', (tester) async {
      await pumpApp(tester, TestEnv(signedIn: true));
      await tapText(tester, 'Wallet');
      expect(await reveal(tester, find.text('Reward for K3M9P2QA')), findsOneWidget);
      expect(find.text('+₹200'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('with no activity yet, the wallet says so', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.walletResponse = Wallet.fromJson({...walletJson(), 'recent_entries': <Object>[]});
      await pumpApp(tester, env);
      await tapText(tester, 'Wallet');
      expect(await reveal(tester, find.text('No activity yet')), findsOneWidget);
      await finish(tester);
    });
  });

  group('withdraw', () {
    TestEnv ready() => TestEnv(signedIn: true)
      ..api.walletResponse = Wallet.fromJson(walletJson(payoutsOpen: true, available: 240000, pending: 0))
      ..api.bankResponse = const BankDetails(
        saved: true,
        accountHolderName: 'Ravi Kumar',
        accountNumberMasked: 'XXXX XXXX 4821',
        ifsc: 'HDFC0001234',
      );

    testWidgets('before the payout date it explains when', (tester) async {
      await pumpApp(tester, TestEnv(signedIn: true));
      await open(tester, '/wallet/withdraw');
      expect(find.text('Withdrawals aren’t open yet'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('without bank details, Add bank details leads there', (tester) async {
      final env = ready()..api.bankResponse = const BankDetails(saved: false);
      await pumpApp(tester, env);
      await open(tester, '/wallet/withdraw');
      expect(find.text('Add your bank details first'), findsOneWidget);
      await tapText(tester, 'Add bank details');
      expect(here(tester), '/wallet/bank');
      await finish(tester);
    });

    testWidgets('amount checks, Review, Change amount, Confirm, then See withdrawal history', (tester) async {
      final env = ready();
      await pumpApp(tester, env);
      await open(tester, '/wallet/withdraw');
      for (final (typed, error) in [
        ('', 'Enter an amount in rupees, like 2,400.'),
        ('100', 'The minimum is ₹200.'),
        ('5,000', 'You have ₹2,400 available.'),
      ]) {
        await type(tester, 'Amount (₹)', typed);
        await tapText(tester, 'Review withdrawal');
        expect(find.text(error), findsOneWidget, reason: typed);
      }
      await type(tester, 'Amount (₹)', '200');
      await tapText(tester, 'Review withdrawal');
      expect(find.text('Review and confirm'), findsOneWidget);
      await tapText(tester, 'Change amount');
      expect(find.text('Review withdrawal'), findsOneWidget);
      await tapText(tester, 'Review withdrawal');
      await tapText(tester, 'Confirm withdrawal');
      expect(find.text('Withdrawal requested'), findsOneWidget);
      expect(env.api.calls, contains('withdraw:20000'));
      await tapText(tester, 'See withdrawal history');
      expect(here(tester), '/wallet/history');
      await finish(tester);
    });

    testWidgets('Back to wallet after a request, and the bank row opens bank details', (tester) async {
      final env = ready();
      await pumpApp(tester, env);
      await tapText(tester, 'Wallet');
      await tap(tester, find.widgetWithText(PrimaryButton, 'Withdraw'));
      await tapText(tester, 'Ravi Kumar');
      expect(here(tester), '/wallet/bank');
      await back(tester);
      await type(tester, 'Amount (₹)', '2,400');
      await tapText(tester, 'Review withdrawal');
      await tapText(tester, 'Confirm withdrawal');
      await tapText(tester, 'Back to wallet');
      expect(here(tester), '/wallet');
      await finish(tester);
    });
  });

  group('bank details', () {
    testWidgets('every field is checked before anything is sent', (tester) async {
      final env = TestEnv(signedIn: true);
      await pumpApp(tester, env);
      await tapText(tester, 'Wallet');
      await tapText(tester, 'Bank details');
      await tapText(tester, 'Save bank details');
      expect(find.text('Enter the name exactly as on the bank account.'), findsOneWidget);
      expect(find.text('Account numbers have 9 to 18 digits.'), findsOneWidget);
      expect(find.text('IFSC has 11 characters, like HDFC0001234.'), findsOneWidget);

      await type(tester, 'Account holder name', 'Ravi Kumar');
      await type(tester, 'Account number', '123456784821');
      await type(tester, 'Confirm account number', '123456784820');
      await type(tester, 'IFSC code', 'hdfc0001234');
      await tapText(tester, 'Save bank details');
      expect(find.text('The numbers don’t match.'), findsOneWidget);
      expect(env.api.calls, isNot(contains('saveBank')));

      await type(tester, 'Confirm account number', '123456784821');
      await tapText(tester, 'Save bank details');
      expect(env.api.calls, contains('saveBank'));
      expect(find.text('Bank details saved'), findsOneWidget);
      expect(here(tester), '/wallet'); // back where the user came from
      await finish(tester);
    });

    testWidgets('saved details: Change bank details, then Cancel', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.bankResponse = const BankDetails(
          saved: true,
          accountHolderName: 'Ravi Kumar',
          accountNumberMasked: 'XXXX XXXX 4821',
          ifsc: 'HDFC0001234',
        );
      await pumpApp(tester, env);
      await open(tester, '/wallet/bank');
      expect(find.text('XXXX XXXX 4821'), findsOneWidget);
      await tapText(tester, 'Change bank details');
      expect(find.text('Save bank details'), findsOneWidget);
      await tapText(tester, 'Cancel');
      expect(find.text('Payouts go to'), findsOneWidget);
      await finish(tester);
    });

    testWidgets('while a withdrawal is being paid the details are locked', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.bankResponse = const BankDetails(
          saved: true,
          accountHolderName: 'Ravi Kumar',
          accountNumberMasked: 'XXXX XXXX 4821',
          ifsc: 'HDFC0001234',
          locked: true,
        );
      await pumpApp(tester, env);
      await open(tester, '/wallet/bank');
      expect(find.text('Change bank details'), findsNothing);
      await finish(tester);
    });
  });

  testWidgets('withdrawal history shows every status, or that there are none', (tester) async {
    final env = TestEnv(signedIn: true);
    env.api.history = [
      withdrawal(WithdrawalStatus.requested),
      withdrawal(WithdrawalStatus.processing),
      withdrawal(WithdrawalStatus.paid, reference: 'UTR123456'),
      withdrawal(WithdrawalStatus.failed, reason: 'Account closed.'),
    ];
    await pumpApp(tester, env);
    await open(tester, '/wallet/history');
    for (final chip in ['Requested', 'Processing', 'Paid', 'Failed']) {
      expect(await reveal(tester, find.text(chip)), findsOneWidget, reason: chip);
    }
    expect(await reveal(tester, find.textContaining('bank ref UTR123456')), findsOneWidget);
    expect(await reveal(tester, find.textContaining('The amount is back in your wallet')), findsOneWidget);

    env.api.history = [];
    await back(tester);
    await open(tester, '/wallet/history');
    expect(find.text('No withdrawals yet'), findsOneWidget);
    await finish(tester);
  });

  group('profile and settings', () {
    testWidgets('copy the code, and every row opens its page', (tester) async {
      await pumpApp(tester, TestEnv(signedIn: true));
      await tapText(tester, 'Profile');
      await tap(tester, find.byTooltip('Copy Your referral code'));
      expect(device.clipboard, '7Q2K9MXA');
      for (final (row, route) in [
        ('Settings', '/settings'),
        ('How it works', '/how-it-works'),
        ('Reward rules', '/rules'),
        ('Support', '/support'),
      ]) {
        await tapText(tester, row);
        expect(here(tester), route, reason: row);
        await back(tester);
      }
      await finish(tester);
    });

    testWidgets('Log out asks first; Cancel keeps you signed in', (tester) async {
      final env = TestEnv(signedIn: true);
      await pumpApp(tester, env);
      await tapText(tester, 'Profile');
      await tapText(tester, 'Log out');
      expect(find.text('Log out?'), findsOneWidget);
      await tapText(tester, 'Cancel');
      expect(env.api.calls, isNot(contains('logout')));
      expect(here(tester), '/profile');
      await finish(tester);
    });

    testWidgets('settings: privacy, terms, rules, support and log out', (tester) async {
      final env = TestEnv(signedIn: true);
      await pumpApp(tester, env);
      await open(tester, '/settings');
      for (final (row, route) in [
        ('Privacy notice', '/privacy'),
        ('Terms of use', '/terms'),
        ('Reward rules', '/rules'),
        ('Support', '/support'),
      ]) {
        await tapText(tester, row);
        expect(here(tester), route, reason: row);
        await back(tester);
      }
      await tapText(tester, 'Log out');
      await tapText(tester, 'Log out'); // confirm
      expect(find.text('Welcome back'), findsOneWidget);
      await finish(tester);
    });
  });

  group('legal and support', () {
    testWidgets('terms and privacy are filled from the server, with the online copy when set', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.configResponse = configJson(
          legalName: 'Future Fashion Private Limited',
          supportEmail: 'help@futurefashion.test',
          termsUrl: 'https://futurefashion.test/terms',
        );
      await pumpApp(tester, env);
      await open(tester, '/terms');
      expect(
        await reveal(tester, find.textContaining('Future Fashion Private Limited', findRichText: true)),
        findsWidgets,
      );
      expect(find.textContaining('{{', findRichText: true), findsNothing);
      await tapText(tester, 'Read the latest version online');
      expect(device.opened, ['https://futurefashion.test/terms']);
      await back(tester);
      await open(tester, '/privacy');
      expect(find.textContaining('{{', findRichText: true), findsNothing);
      expect(find.text('Read the latest version online'), findsNothing); // no online privacy URL set
      await finish(tester);
    });

    testWidgets('reward rules state ₹200 for level 1 and ₹0 for levels 2–4', (tester) async {
      await pumpApp(tester, TestEnv(signedIn: true));
      await open(tester, '/rules');
      expect(find.text('₹200 per direct referral'), findsOneWidget);
      expect(find.text('Levels 2–4 pay ₹0'), findsOneWidget);
      expect(await reveal(tester, find.textContaining('Rewards stay pending until 31 December 2026')), findsOneWidget);
      await finish(tester);
    });

    testWidgets('Contact support uses the support page, or else the support email', (tester) async {
      final env = TestEnv(signedIn: true)
        ..api.configResponse = configJson(
          supportEmail: 'help@futurefashion.test',
          supportUrl: 'https://futurefashion.test/help',
        );
      await pumpApp(tester, env);
      await open(tester, '/support');
      await tapText(tester, 'Contact support');
      expect(device.opened, ['https://futurefashion.test/help']);
      await finish(tester);

      final emailOnly = TestEnv(signedIn: true)
        ..api.configResponse = configJson(supportEmail: 'help@futurefashion.test');
      await pumpApp(tester, emailOnly);
      await open(tester, '/support');
      await tapText(tester, 'Contact support');
      expect(device.opened.last, 'mailto:help@futurefashion.test?subject=Future%20Fashion%20support');
      await finish(tester);
    });

    testWidgets('with no support contact set, the page says contact details are coming', (tester) async {
      await pumpApp(tester, TestEnv(signedIn: true));
      await open(tester, '/support');
      expect(find.text('Contact support'), findsNothing);
      expect(
        await reveal(tester, find.textContaining('Support contact details will appear here soon')),
        findsOneWidget,
      );
      await finish(tester);
    });
  });

  testWidgets('share: Copy Referral Code, Copy link and Share Referral Link', (tester) async {
    final env = TestEnv(signedIn: true);
    await pumpApp(tester, env);
    await open(tester, '/share');
    await tapText(tester, 'Copy Referral Code');
    expect(device.clipboard, '7Q2K9MXA');
    expect(find.text('Referral code copied'), findsOneWidget);
    await tap(tester, find.byTooltip('Copy link'));
    expect(device.clipboard, 'https://futurefashion.test/r/7Q2K9MXA');
    await tapText(tester, 'Share Referral Link');
    expect(env.apkShare.sent, ['link:7Q2K9MXA']);
    await finish(tester);
  });

  testWidgets('membership and how-it-works show real figures and the one paid level', (tester) async {
    await pumpApp(tester, TestEnv(signedIn: true));
    await open(tester, '/membership');
    expect(find.text('18,342'), findsOneWidget);
    expect(find.text('Campaign capacity: 5,00,00,000 members'), findsOneWidget);
    await back(tester);
    await open(tester, '/how-it-works');
    expect(
      await reveal(tester, find.textContaining('Only people you invite directly earn you a reward')),
      findsOneWidget,
    );
    await finish(tester);
  });

  testWidgets('the bottom tabs switch between Home, Referrals, Wallet and Profile', (tester) async {
    await pumpApp(tester, TestEnv(signedIn: true));
    for (final (tab, route) in [
      ('Referrals', '/referrals'),
      ('Wallet', '/wallet'),
      ('Profile', '/profile'),
      ('Home', '/home'),
    ]) {
      await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(tab)));
      await settle(tester);
      expect(here(tester), route, reason: tab);
    }
    await finish(tester);
  });
}
