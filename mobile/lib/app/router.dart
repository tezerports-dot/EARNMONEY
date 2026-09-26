import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/auth/session_controller.dart';
import '../core/config/config_controller.dart';
import '../core/launch/launch_gate_controller.dart';
import '../core/providers.dart';
import '../features/apk_sharing/share_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/signup_screen.dart';
import '../features/campaign/celebration_screen.dart';
import '../features/campaign/how_it_works_screen.dart';
import '../features/campaign/membership_screen.dart';
import '../features/home/home_screen.dart';
import '../features/launch/launch_gate_screen.dart';
import '../features/legal/legal_screens.dart';
import '../features/recruitment/recruitment_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/referrals/direct_referrals_screen.dart';
import '../features/referrals/referrals_screen.dart';
import '../features/shell/app_shell.dart';
import '../features/system/system_screens.dart';
import '../features/telegram_verification/verify_screen.dart';
import '../features/wallet/wallet_screen.dart';
import '../features/withdrawals/bank_details_screen.dart';
import '../features/withdrawals/withdraw_screen.dart';
import '../features/withdrawals/withdrawal_history_screen.dart';
import 'redirect.dart';

final _rootKey = GlobalKey<NavigatorState>(debugLabel: 'root');

/// Re-runs the redirect whenever the session or the configuration changes.
class _RouterRefresh extends ChangeNotifier {
  _RouterRefresh(Ref ref) {
    ref
      ..listen(sessionProvider, (_, _) => notifyListeners())
      ..listen(configProvider, (_, _) => notifyListeners())
      ..listen(gatePassedProvider, (_, _) => notifyListeners());
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _RouterRefresh(ref);
  ref.onDispose(refresh.dispose);

  GoRoute page(String path, Widget Function() build) =>
      GoRoute(path: path, parentNavigatorKey: _rootKey, builder: (_, _) => build());

  final router = GoRouter(
    navigatorKey: _rootKey,
    initialLocation: '/splash',
    refreshListenable: refresh,
    redirect: (context, state) => decideRedirect(
      config: ref.read(configProvider),
      session: ref.read(sessionProvider),
      onboardingSeen: ref.read(prefsProvider).onboardingSeen,
      appVersion: ref.read(appVersionProvider),
      location: state.matchedLocation,
      launchGateEnabled: ref.read(configProvider).valueOrNull?.config.launchGateEnabled ?? false,
      launchGatePassed: ref.read(gatePassedProvider),
    ),
    routes: [
      page('/splash', () => const SplashScreen()),
      page('/offline', () => const OfflineScreen()),
      page('/maintenance', () => const MaintenanceScreen()),
      page('/upgrade', () => const UpgradeScreen()),
      page('/suspended', () => const SuspendedScreen()),
      page('/onboarding', () => const OnboardingScreen()),
      page('/login', () => const LoginScreen()),
      page('/signup', () => const SignupScreen()),
      page('/verify', () => const VerifyScreen()),
      page('/verify/success', () => const VerifySuccessScreen()),
      page('/gate', () => const LaunchGateScreen()),
      page('/terms', () => const LegalScreen(document: 'terms', title: 'Terms of use')),
      page('/privacy', () => const LegalScreen(document: 'privacy', title: 'Privacy notice')),
      page('/rules', () => const RulesScreen()),
      page('/how-it-works', () => const HowItWorksScreen()),
      page('/support', () => const SupportScreen()),
      page('/share', () => const ShareScreen()),
      page('/settings', () => const SettingsScreen()),
      page('/membership', () => const MembershipScreen()),
      page('/celebration', () => const CelebrationScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [GoRoute(path: '/home', builder: (_, _) => const HomeScreen())],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/referrals',
                builder: (_, _) => const ReferralsScreen(),
                routes: [
                  GoRoute(
                    path: 'direct',
                    parentNavigatorKey: _rootKey,
                    builder: (_, _) => const DirectReferralsScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/wallet',
                builder: (_, _) => const WalletScreen(),
                routes: [
                  GoRoute(path: 'withdraw', parentNavigatorKey: _rootKey, builder: (_, _) => const WithdrawScreen()),
                  GoRoute(path: 'bank', parentNavigatorKey: _rootKey, builder: (_, _) => const BankDetailsScreen()),
                  GoRoute(
                    path: 'history',
                    parentNavigatorKey: _rootKey,
                    builder: (_, _) => const WithdrawalHistoryScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/recruitment', builder: (_, _) => const RecruitmentScreen())],
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
