import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/models.dart';
import 'providers.dart';

// Server data for signed-in screens. Each is fetched when a screen needs it
// and dropped when no screen does; nothing polls in the background.

final dashboardProvider = FutureProvider.autoDispose<Dashboard>((ref) => ref.watch(apiProvider).dashboard());

final referralSummaryProvider = FutureProvider.autoDispose<ReferralSummary>(
  (ref) => ref.watch(apiProvider).referralSummary(),
);

final walletProvider = FutureProvider.autoDispose<Wallet>((ref) => ref.watch(apiProvider).wallet());

final bankDetailsProvider = FutureProvider.autoDispose<BankDetails>((ref) => ref.watch(apiProvider).bankDetails());

final shareInfoProvider = FutureProvider.autoDispose<ShareInfo>((ref) => ref.watch(apiProvider).shareInfo());

/// First page of direct referrals, for the preview on the referral dashboard.
final directPreviewProvider = FutureProvider.autoDispose<Paged<DirectReferral>>(
  (ref) => ref.watch(apiProvider).directReferrals(limit: 3),
);

final recruitmentProvider = FutureProvider.autoDispose<List<RecruitmentPost>>(
  (ref) => ref.watch(apiProvider).recruitment(),
);
