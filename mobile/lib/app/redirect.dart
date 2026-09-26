import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api/api_exception.dart';
import '../core/api/models.dart';
import '../core/auth/session_controller.dart';
import '../core/config/config_controller.dart';

/// Pages anyone may read, signed in or not.
const publicPages = {'/terms', '/privacy', '/rules', '/how-it-works', '/support'};

const _authPages = {'/login', '/signup', '/onboarding'};
const _systemPages = {'/splash', '/offline', '/maintenance', '/upgrade', '/suspended'};

/// Where the app must be, given what the server said. A pure function so
/// every rule can be unit-tested (test/redirect_test.dart).
String? decideRedirect({
  required AsyncValue<ConfigState> config,
  required AsyncValue<Session> session,
  required bool onboardingSeen,
  required String appVersion,
  required String location,
  required bool launchGateEnabled,
  required bool launchGatePassed,
}) {
  String? go(String target) => location == target ? null : target;

  String? systemPageFor(Object? error) => switch (error) {
    MaintenanceException() => go('/maintenance'),
    UpgradeRequiredException() => go('/upgrade'),
    _ => go('/offline'),
  };

  if (!config.hasValue) {
    return config.hasError ? systemPageFor(config.error) : go('/splash');
  }
  final cfg = config.requireValue.config;
  if (cfg.maintenanceActive) return go('/maintenance');
  if (isOlderVersion(appVersion, cfg.minAppVersion)) return go('/upgrade');

  if (!session.hasValue) {
    return session.hasError ? systemPageFor(session.error) : go('/splash');
  }
  if (publicPages.contains(location)) return null;

  switch (session.requireValue) {
    case SignedOut():
      if (_authPages.contains(location)) return null;
      return onboardingSeen ? '/login' : '/onboarding';
    case SignedIn(:final user) when user.status == AccountStatus.suspended:
      return go('/suspended');
    case SignedIn(:final user) when user.status == AccountStatus.pendingVerification:
      return go('/verify');
    case SignedIn():
      if (location == '/verify/success') return null;
      // Verification just finished (the session was refreshed on /verify).
      if (location == '/verify') return '/verify/success';
      if (_authPages.contains(location) || _systemPages.contains(location)) return '/home';
      if (launchGateEnabled && !launchGatePassed) return go('/gate');
      if (location == '/gate') return '/home';
      return null;
  }
}

/// "1.2.0" < "1.10.0". Anything unparsable is treated as not older.
bool isOlderVersion(String have, String need) {
  List<int>? parts(String v) {
    final core = v.split('+').first.split('-').first;
    final numbers = core.split('.').map(int.tryParse).toList();
    return numbers.any((n) => n == null) ? null : numbers.cast<int>();
  }

  final a = parts(have);
  final b = parts(need);
  if (a == null || b == null) return false;
  for (var i = 0; i < (a.length > b.length ? a.length : b.length); i++) {
    final x = i < a.length ? a[i] : 0;
    final y = i < b.length ? b[i] : 0;
    if (x != y) return x < y;
  }
  return false;
}
