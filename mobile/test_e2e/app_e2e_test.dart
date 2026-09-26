import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:future_fashion/app/app.dart';
import 'package:future_fashion/core/api/api_client.dart';
import 'package:future_fashion/core/api/future_fashion_api.dart';
import 'package:future_fashion/core/api/models.dart';
import 'package:future_fashion/core/auth/session_controller.dart';
import 'package:future_fashion/core/auth/token_store.dart';
import 'package:future_fashion/core/providers.dart';
import 'package:future_fashion/core/storage/prefs.dart';
import 'package:future_fashion/core/widgets/buttons.dart';
import 'package:future_fashion/features/apk_sharing/apk_share_service.dart';
import 'package:future_fashion/features/apk_sharing/share_screen.dart';
import 'package:share_plus/share_plus.dart';

/// End to end: this app's real screens, API client and state, talking over
/// real HTTP to the real server, database, Redis and worker, with a fake
/// Telegram standing in for the user's phone. Run it with e2e/run.sh.
///
/// The tests run in order and share two people, A and B. Each test starts the
/// app afresh with the same phone storage, like reopening the app.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = null; // reach the local server for real

  final env = Platform.environment;
  final apiBase = env['E2E_API'] ?? 'http://127.0.0.1:8000';
  final telegramBase = env['E2E_TELEGRAM'] ?? 'http://127.0.0.1:8081';
  final stack = (env['E2E_STACK'] ?? 'python3 ../e2e/stack.py').split(' ');
  final runDir = env['E2E_RUN_DIR'] ?? '../e2e/.run';

  final random = Random();
  String newPhone() => '9${List.generate(9, (_) => random.nextInt(10)).join()}';
  final a = _Person(phone: newPhone(), password: 'a-strong-password-1', telegramId: 700000000 + random.nextInt(99999));
  final b = _Person(phone: newPhone(), password: 'b-strong-password-2', telegramId: 800000000 + random.nextInt(99999));
  final opened = <String>[];

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/url_launcher'),
      (call) async {
        if (call.method == 'launch') opened.add((call.arguments as Map<Object?, Object?>)['url']! as String);
        return true;
      },
    );
  });

  // --- Driving the app over real HTTP ---------------------------------------

  Future<void> tick(WidgetTester tester) async {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 60)));
    await tester.pump(const Duration(milliseconds: 60));
  }

  /// Waits (in real time, for the server) until [finder] shows up.
  Future<Finder> waitFor(WidgetTester tester, Finder finder, {int seconds = 30}) async {
    final deadline = DateTime.now().add(Duration(seconds: seconds));
    while (finder.evaluate().isEmpty) {
      if (DateTime.now().isAfter(deadline)) {
        final texts = find.byType(Text).evaluate().map((e) => (e.widget as Text).data).whereType<String>().take(40);
        fail('Timed out waiting for $finder. On screen: ${texts.toList()}');
      }
      await tick(tester);
    }
    return finder;
  }

  Future<Finder> reveal(WidgetTester tester, Finder finder) async {
    final deadline = DateTime.now().add(const Duration(seconds: 30));
    while (finder.evaluate().isEmpty) {
      final lists = find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down);
      if (lists.evaluate().isNotEmpty) await tester.drag(lists.last, const Offset(0, -300));
      await tick(tester);
      if (DateTime.now().isAfter(deadline)) fail('Never found $finder');
    }
    await tester.ensureVisible(finder.last);
    await tick(tester);
    return finder.last;
  }

  Future<void> tapOn(WidgetTester tester, Finder finder) async {
    await tester.tap(await reveal(tester, finder));
    await tick(tester);
  }

  Future<void> tapText(WidgetTester tester, String text) => tapOn(tester, find.text(text));

  /// A snack bar's 4-second timer starts only once it has slid in, so step
  /// through time until it has come and gone.
  Future<void> messageGone(WidgetTester tester) async {
    for (var i = 0; i < 12 && find.byType(SnackBar).evaluate().isNotEmpty; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(find.byType(SnackBar), findsNothing);
  }

  Future<void> type(WidgetTester tester, String field, String text) async {
    await tester.enterText(await reveal(tester, find.widgetWithText(TextField, field)), text);
    await tick(tester);
  }

  Future<void> startApp(WidgetTester tester, _Person person) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.75;
    tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    rootBundle.clear();
    person.dio = Dio(
      BaseOptions(
        baseUrl: apiBase,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 20),
        sendTimeout: const Duration(seconds: 20),
        responseType: ResponseType.json,
      ),
    );
    final client = ApiClient(baseUrl: apiBase, appVersion: '1.0.0', tokens: person.tokens, dio: person.dio);
    await tester.pumpWidget(
      ProviderScope(
        retry: (retryCount, error) => null,
        overrides: [
          apiProvider.overrideWithValue(HttpFutureFashionApi(client)),
          tokenStoreProvider.overrideWithValue(person.tokens),
          prefsProvider.overrideWithValue(person.prefs),
          appVersionProvider.overrideWithValue('1.0.0'),
          apkShareServiceProvider.overrideWithValue(const _NoShare()),
        ],
        child: const FutureFashionApp(),
      ),
    );
    await tick(tester);
  }

  /// Closes the app like a person would, then lets requests still in flight
  /// land and the HTTP client's idle connections time out.
  Future<void> closeApp(WidgetTester tester, _Person person) async {
    await tester.pumpWidget(const SizedBox());
    for (var i = 0; i < 5; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pump(const Duration(seconds: 1));
    }
    person.dio?.close(force: true);
    await tester.pump(const Duration(seconds: 25));
  }

  Me? signedInUser(WidgetTester tester) {
    final session = ProviderScope.containerOf(tester.element(find.byType(FutureFashionApp)))
        .read(sessionProvider)
        .value;
    return session is SignedIn ? session.user : null;
  }

  // --- Acting as Telegram and as the admin -----------------------------------

  Future<Object?> telegram(WidgetTester tester, String path, Map<String, Object?> body) async {
    return tester.runAsync<Object?>(() async {
      final client = HttpClient();
      try {
        final request = await client.postUrl(Uri.parse('$telegramBase/control/$path'));
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode(body));
        final response = await request.close();
        final text = await response.transform(utf8.decoder).join();
        expect(response.statusCode, 200, reason: '$path: $text');
        return jsonDecode(text);
      } finally {
        client.close();
      }
    });
  }

  Future<void> admin(WidgetTester tester, List<String> args) async {
    final result = await tester.runAsync(() => Process.run(stack.first, [...stack.skip(1), ...args]));
    expect(result!.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
  }

  /// Everything a person does inside Telegram, as the verification screen asks.
  Future<void> verifyInTelegram(WidgetTester tester, _Person person) async {
    final setup = jsonDecode(File('$runDir/env.json').readAsStringSync()) as Map<String, Object?>;
    final bot = setup['verifier']! as String;
    await tapOn(tester, find.widgetWithText(PrimaryButton, 'Open Telegram')); // below the fold: scrolls to it
    final link = Uri.parse(opened.last);
    expect(link.host, 't.me');
    expect(link.pathSegments.single, bot);
    await telegram(tester, 'start', {'bot': bot, 'user_id': person.telegramId, 'token': link.queryParameters['start']});
    for (final chat in (setup['channels']! as List<Object?>).cast<int>()) {
      await telegram(tester, 'join-request', {'user_id': person.telegramId, 'chat_id': chat});
    }
    await telegram(tester, 'callback', {'bot': bot, 'user_id': person.telegramId, 'data': 'vs:check'});
    await telegram(tester, 'contact', {'bot': bot, 'user_id': person.telegramId, 'phone': '+91${person.phone}'});
    await tapText(tester, 'I’ve finished — check again');
    await waitFor(tester, find.text('Verification complete'));
    await tapText(tester, 'Continue');
    await waitFor(tester, find.text('YOUR INCOME'));
  }

  Future<void> signUp(WidgetTester tester, _Person person, {String? referralCode}) async {
    await startApp(tester, person);
    await tapOn(tester, await waitFor(tester, find.text('Create an account')));
    await waitFor(tester, find.text('Telegram verification is required'));
    await type(tester, 'Mobile number', person.phone);
    await type(tester, 'Password', person.password);
    if (referralCode != null) {
      await type(tester, 'Referral code (optional)', referralCode);
      FocusManager.instance.primaryFocus?.unfocus();
      await waitFor(tester, find.text('Valid referral code'));
    }
    final question = await waitFor(tester, find.textContaining(RegExp(r'^\d+ [+−] \d+ = \?$')));
    await type(tester, 'Answer', _solve((question.evaluate().first.widget as Text).data!));
    await tapText(tester, 'Create account');
    await waitFor(tester, find.text('Verify with Telegram'));
  }

  Future<void> logOut(WidgetTester tester) async {
    await tapOn(tester, find.descendant(of: find.byType(NavigationBar), matching: find.text('Profile')));
    await tapOn(tester, find.widgetWithText(SecondaryButton, 'Log out'));
    await tapOn(tester, find.descendant(of: find.byType(AlertDialog), matching: find.text('Log out')));
    await waitFor(tester, find.text('Welcome back'));
  }

  // --- The journey --------------------------------------------------------------

  testWidgets('A signs up and verifies through Telegram', (tester) async {
    await signUp(tester, a);
    await verifyInTelegram(tester, a);
    a.code = signedInUser(tester)!.referralCode;
    expect(a.code, hasLength(8));
    expect(find.descendant(of: find.byType(NavigationBar), matching: find.text('Home')), findsOneWidget);
    await closeApp(tester, a);
  });

  testWidgets('reopening the app keeps A signed in', (tester) async {
    await startApp(tester, a);
    await waitFor(tester, find.text('L1 ₹0')); // the figure loaded: nobody referred yet
    expect(find.text('Invite friends: you earn ₹200 for each one who verifies.'), findsOneWidget);
    await logOut(tester);
    await closeApp(tester, a);
  });

  testWidgets('B signs up with A’s code (checked by the server) and verifies', (tester) async {
    await signUp(tester, b, referralCode: a.code);
    await verifyInTelegram(tester, b);
    await tapOn(tester, find.descendant(of: find.byType(NavigationBar), matching: find.text('Profile')));
    expect(await reveal(tester, find.text(a.code!)), findsOneWidget); // "Referred by"
    await logOut(tester);
    await closeApp(tester, b);
  });

  testWidgets('A logs in and sees the ₹200 reward on home, referrals and wallet', (tester) async {
    await startApp(tester, a);
    await type(tester, 'Mobile number', a.phone);
    await type(tester, 'Password', a.password);
    await tapText(tester, 'Log in');
    await waitFor(tester, find.text('YOUR INCOME'));
    await waitFor(tester, find.text('L1 ₹200'));
    expect(find.text('Pending until 31 December 2026'), findsOneWidget);

    await tapOn(tester, find.descendant(of: find.byType(NavigationBar), matching: find.text('Referrals')));
    await waitFor(tester, find.text('Level 1'));
    await tapText(tester, 'Level 1 — your direct referrals');
    await waitFor(tester, find.textContaining('ID '));
    expect(find.textContaining(b.phone.substring(0, 2)), findsWidgets); // masked, never the full number
    expect(find.text(b.phone), findsNothing);

    await tapOn(tester, find.descendant(of: find.byType(NavigationBar), matching: find.text('Wallet')));
    await waitFor(tester, find.text('Total earned'));
    await waitFor(tester, find.textContaining('Rewards become withdrawable on 31 December 2026'));
    await closeApp(tester, a);
  });

  testWidgets('on the payout date A adds bank details and withdraws ₹200', (tester) async {
    await admin(tester, ['open-payouts']);
    await startApp(tester, a);
    await tapOn(
      tester,
      await waitFor(tester, find.descendant(of: find.byType(NavigationBar), matching: find.text('Wallet'))),
    );
    await tapText(tester, 'Bank details');
    await type(tester, 'Account holder name', 'Ravi Kumar');
    await type(tester, 'Account number', '123456784821');
    await type(tester, 'Confirm account number', '123456784821');
    await type(tester, 'IFSC code', 'HDFC0001234');
    await tapText(tester, 'Save bank details');
    await waitFor(tester, find.text('Bank details saved'));
    await messageGone(tester); // a person takes longer than the message stays

    final withdraw = find.widgetWithText(PrimaryButton, 'Withdraw');
    await reveal(tester, withdraw);
    await waitFor(
      tester,
      find.byWidgetPredicate((w) => w is PrimaryButton && w.label == 'Withdraw' && w.onPressed != null),
    );
    await tapOn(tester, withdraw);
    await waitFor(tester, find.textContaining('XXXX XXXX 4821')); // masked: only the last 4 digits
    await type(tester, 'Amount (₹)', '200');
    await tapText(tester, 'Review withdrawal');
    await tapText(tester, 'Confirm withdrawal');
    await waitFor(tester, find.text('Withdrawal requested'));
    await tapText(tester, 'See withdrawal history');
    await waitFor(tester, find.text('Requested'));
    await closeApp(tester, a);
  });

  testWidgets('the admin pays the batch, and A sees it paid with the bank reference', (tester) async {
    await admin(tester, ['pay-all', 'UTR99887766']);
    await startApp(tester, a);
    await tapOn(
      tester,
      await waitFor(tester, find.descendant(of: find.byType(NavigationBar), matching: find.text('Wallet'))),
    );
    await tapText(tester, 'History');
    await waitFor(tester, find.text('Paid'));
    expect(find.textContaining('bank ref UTR99887766'), findsOneWidget);
    await closeApp(tester, a);
  });
}

String _solve(String question) {
  final m = RegExp(r'^(\d+) ([+−]) (\d+) = \?$').firstMatch(question)!;
  final x = int.parse(m.group(1)!);
  final y = int.parse(m.group(3)!);
  return '${m.group(2) == '+' ? x + y : x - y}';
}

class _Person {
  _Person({required this.phone, required this.password, required this.telegramId});

  final String phone;
  final String password;
  final int telegramId;
  final tokens = MemoryTokenStore();
  final prefs = MemoryAppPrefs()..onboardingSeen = true;
  Dio? dio;
  String? code;
}

/// Sharing needs Android; this journey doesn't share.
class _NoShare implements ApkShareService {
  const _NoShare();

  @override
  Future<ShareResultStatus> shareAppAndReferral({
    required String companyName,
    required ShareInfo info,
    required String appVersion,
  }) async => ShareResultStatus.unavailable;

  @override
  Future<void> shareLink({required String companyName, required ShareInfo info}) async {}
}
