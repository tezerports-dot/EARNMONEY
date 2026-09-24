import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_exception.dart';
import '../api/models.dart';
import '../providers.dart';

sealed class Session {
  const Session();
}

final class SignedOut extends Session {
  const SignedOut({this.notice});

  /// Shown once on the login screen (for example "Your session has ended").
  final String? notice;
}

final class SignedIn extends Session {
  const SignedIn(this.user);

  final Me user;

  bool get verified => user.status == AccountStatus.active;
}

/// Who is using the app. The server decides everything: this only keeps
/// the tokens and the latest /v1/me answer.
class SessionController extends AsyncNotifier<Session> {
  StreamSubscription<void>? _ended;

  @override
  Future<Session> build() async {
    final api = ref.watch(apiProvider);
    _ended = api.sessionEnded.listen((_) {
      state = const AsyncData(SignedOut(notice: 'Your session has ended. Please log in again.'));
    });
    ref.onDispose(() => _ended?.cancel());

    final tokens = await ref.watch(tokenStoreProvider).read();
    if (tokens == null) return const SignedOut();
    try {
      return SignedIn(await api.me());
    } on SessionEndedException {
      return const SignedOut(notice: 'Your session has ended. Please log in again.');
    }
  }

  Future<void> signup({
    required String phone,
    required String password,
    required String? referralCode,
    required String captchaId,
    required String captchaAnswer,
    required String idempotencyKey,
  }) async {
    final result = await ref
        .read(apiProvider)
        .signup(
          phone: phone,
          password: password,
          referralCode: referralCode,
          captchaId: captchaId,
          captchaAnswer: captchaAnswer,
          idempotencyKey: idempotencyKey,
        );
    await ref.read(tokenStoreProvider).write(result.tokens);
    await ref.read(prefsProvider).setPendingReferralCode(null);
    state = AsyncData(SignedIn(result.user));
  }

  Future<void> login({required String phone, required String password, String? captchaId, String? captchaAnswer}) async {
    final result = await ref
        .read(apiProvider)
        .login(phone: phone, password: password, captchaId: captchaId, captchaAnswer: captchaAnswer);
    await ref.read(tokenStoreProvider).write(result.tokens);
    state = AsyncData(SignedIn(result.user));
  }

  /// Ends this device's session. The account itself is untouched.
  Future<void> logout() async {
    try {
      await ref.read(apiProvider).logout();
    } on ApiException {
      // Offline or already expired: the local sign-out still happens.
    }
    await ref.read(tokenStoreProvider).clear();
    state = const AsyncData(SignedOut());
  }

  /// Re-reads the account (for example after Telegram verification).
  Future<void> refreshUser() async {
    final me = await ref.read(apiProvider).me();
    state = AsyncData(SignedIn(me));
  }
}

final sessionProvider = AsyncNotifierProvider<SessionController, Session>(SessionController.new);
