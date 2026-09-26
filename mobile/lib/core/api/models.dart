import 'json.dart';

// Typed mirrors of the shapes in docs/API.md. Amounts are integer paise.

enum AccountStatus { pendingVerification, active, suspended }

AccountStatus _accountStatus(String raw) => switch (raw) {
  'PENDING_VERIFICATION' => AccountStatus.pendingVerification,
  'ACTIVE' => AccountStatus.active,
  'SUSPENDED' => AccountStatus.suspended,
  _ => throw FormatException('Unknown account status $raw'),
};

class Me {
  const Me({
    required this.publicId,
    required this.phoneMasked,
    required this.status,
    required this.referralCode,
    required this.referredBy,
    required this.createdAt,
    required this.verifiedAt,
  });

  factory Me.fromJson(Json j) => Me(
    publicId: j.str('public_id'),
    phoneMasked: j.str('phone_masked'),
    status: _accountStatus(j.str('status')),
    referralCode: j.strOrNull('referral_code'),
    referredBy: j.strOrNull('referred_by'),
    createdAt: j.time('created_at'),
    verifiedAt: j.timeOrNull('verified_at'),
  );

  final String publicId;
  final String phoneMasked;
  final AccountStatus status;
  final String? referralCode;
  final String? referredBy;
  final DateTime createdAt;
  final DateTime? verifiedAt;
}

class Tokens {
  const Tokens({required this.accessToken, required this.refreshToken, required this.refreshExpiresAt});

  factory Tokens.fromJson(Json j) => Tokens(
    accessToken: j.str('access_token'),
    refreshToken: j.str('refresh_token'),
    refreshExpiresAt: j.time('refresh_expires_at'),
  );

  final String accessToken;
  final String refreshToken;
  final DateTime refreshExpiresAt;

  Json toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'refresh_expires_at': refreshExpiresAt.toIso8601String(),
  };
}

class AuthResult {
  const AuthResult(this.user, this.tokens);

  factory AuthResult.fromJson(Json j) => AuthResult(Me.fromJson(j.obj('user')), Tokens.fromJson(j.obj('tokens')));

  final Me user;
  final Tokens tokens;
}

class Captcha {
  const Captcha({required this.id, required this.question});

  factory Captcha.fromJson(Json j) => Captcha(id: j.str('captcha_id'), question: j.str('question'));

  final String id;
  final String question;
}

enum CampaignStatus { notStarted, active, paused, ended }

class CampaignInfo {
  const CampaignInfo({
    required this.status,
    required this.startsAt,
    required this.endsAt,
    required this.brandRevealAt,
    required this.launchAt,
    required this.payoutOpensAt,
    required this.brandName,
    required this.signupsOpen,
    required this.rewardsOpen,
  });

  factory CampaignInfo.fromJson(Json j) => CampaignInfo(
    status: switch (j.str('status')) {
      'NOT_STARTED' => CampaignStatus.notStarted,
      'ACTIVE' => CampaignStatus.active,
      'PAUSED' => CampaignStatus.paused,
      'ENDED' => CampaignStatus.ended,
      final other => throw FormatException('Unknown campaign status $other'),
    },
    startsAt: j.time('starts_at'),
    endsAt: j.time('ends_at'),
    brandRevealAt: j.time('brand_reveal_at'),
    launchAt: j.time('launch_at'),
    payoutOpensAt: j.time('payout_opens_at'),
    brandName: j.strOrNull('brand_name'),
    signupsOpen: j.boolean('signups_open'),
    rewardsOpen: j.boolean('rewards_open'),
  );

  final CampaignStatus status;
  final DateTime startsAt;
  final DateTime endsAt;
  final DateTime brandRevealAt;
  final DateTime launchAt;
  final DateTime payoutOpensAt;
  final String? brandName;
  final bool signupsOpen;
  final bool rewardsOpen;
}

class LevelRate {
  const LevelRate(this.level, this.rewardPerUserPaise);

  final int level;
  final int rewardPerUserPaise;
}

class AdSettings {
  const AdSettings({
    required this.bannerEnabled,
    required this.interstitialEnabled,
    required this.rewardedEnabled,
    required this.minInterstitialInterval,
  });

  factory AdSettings.fromJson(Json j) => AdSettings(
    bannerEnabled: j.boolean('banner_enabled'),
    interstitialEnabled: j.boolean('interstitial_enabled'),
    rewardedEnabled: j.boolean('rewarded_enabled'),
    minInterstitialInterval: Duration(seconds: j.integer('min_interstitial_interval_seconds')),
  );

  static const off = AdSettings(
    bannerEnabled: false,
    interstitialEnabled: false,
    rewardedEnabled: false,
    minInterstitialInterval: Duration(minutes: 5),
  );

  final bool bannerEnabled;
  final bool interstitialEnabled;
  final bool rewardedEnabled;
  final Duration minInterstitialInterval;
}

class Announcement {
  const Announcement(this.text, this.tone);

  final String text;
  final String tone;
}

class PublicConfig {
  const PublicConfig({
    required this.serverNow,
    required this.companyName,
    required this.companyLegalName,
    required this.supportEmail,
    required this.minAppVersion,
    required this.apkDownloadUrl,
    required this.maintenanceActive,
    required this.maintenanceMessage,
    required this.maintenanceUntil,
    required this.campaign,
    required this.levels,
    required this.minWithdrawalPaise,
    required this.verifiedCount,
    required this.capacity,
    required this.promotionAllocationPaise,
    required this.announcement,
    required this.ads,
    required this.termsUrl,
    required this.privacyUrl,
    required this.supportUrl,
    required this.launchGateEnabled,
  });

  factory PublicConfig.fromJson(Json j) {
    final maintenance = j.obj('maintenance');
    final rewards = j.obj('rewards');
    final membership = j.obj('membership');
    final announcement = j.objOrNull('announcement');
    final links = j.obj('links');
    return PublicConfig(
      serverNow: j.time('server_now'),
      companyName: j.str('company_name'),
      companyLegalName: j.strOrNull('company_legal_name'),
      supportEmail: j.strOrNull('support_email'),
      minAppVersion: j.str('min_app_version'),
      apkDownloadUrl: j.strOrNull('apk_download_url'),
      maintenanceActive: maintenance.boolean('active'),
      maintenanceMessage: maintenance.strOrNull('message'),
      maintenanceUntil: maintenance.timeOrNull('until'),
      campaign: CampaignInfo.fromJson(j.obj('campaign')),
      levels: [
        for (final row in rewards.list('levels')) LevelRate(row.integer('level'), row.integer('reward_per_user_paise')),
      ],
      minWithdrawalPaise: rewards.integer('min_withdrawal_paise'),
      verifiedCount: membership.integer('verified_count'),
      capacity: membership.integer('capacity'),
      promotionAllocationPaise: j.obj('promotion').integerOrNull('allocation_paise'),
      announcement: announcement == null ? null : Announcement(announcement.str('text'), announcement.str('tone')),
      ads: AdSettings.fromJson(j.obj('ads')),
      termsUrl: links.strOrNull('terms_url'),
      privacyUrl: links.strOrNull('privacy_url'),
      supportUrl: links.strOrNull('support_url'),
      launchGateEnabled: (j.objOrNull('launch_gate')?.boolean('enabled')) ?? false,
    );
  }

  final DateTime serverNow;
  final String companyName;
  final String? companyLegalName;
  final String? supportEmail;
  final String minAppVersion;
  final String? apkDownloadUrl;
  final bool maintenanceActive;
  final String? maintenanceMessage;
  final DateTime? maintenanceUntil;
  final CampaignInfo campaign;
  final List<LevelRate> levels;
  final int minWithdrawalPaise;
  final int verifiedCount;
  final int capacity;
  final int? promotionAllocationPaise;
  final Announcement? announcement;
  final AdSettings ads;
  final String? termsUrl;
  final String? privacyUrl;
  final String? supportUrl;
  final bool launchGateEnabled;

  /// The only paid level, as the server reports it.
  int get level1RewardPaise => levels.firstWhere((l) => l.level == 1).rewardPerUserPaise;
}

class LaunchChallenge {
  const LaunchChallenge({required this.enabled, required this.deepLink, required this.expiresIn});

  factory LaunchChallenge.fromJson(Json j) => LaunchChallenge(
    enabled: j.boolean('enabled'),
    deepLink: j.strOrNull('deep_link'),
    expiresIn: j.integer('expires_in'),
  );

  final bool enabled;
  final String? deepLink;
  final int expiresIn;
}

class LaunchStatus {
  const LaunchStatus({required this.enabled, required this.passed});

  factory LaunchStatus.fromJson(Json j) => LaunchStatus(enabled: j.boolean('enabled'), passed: j.boolean('passed'));

  final bool enabled;
  final bool passed;
}

class RecruitmentPost {
  const RecruitmentPost({
    required this.title,
    required this.location,
    required this.employmentType,
    required this.description,
    required this.applyUrl,
    required this.applyEmail,
  });

  factory RecruitmentPost.fromJson(Json j) => RecruitmentPost(
    title: j.str('title'),
    location: j.strOrNull('location'),
    employmentType: j.strOrNull('employment_type'),
    description: j.str('description'),
    applyUrl: j.strOrNull('apply_url'),
    applyEmail: j.strOrNull('apply_email'),
  );

  final String title;
  final String? location;
  final String? employmentType;
  final String description;
  final String? applyUrl;
  final String? applyEmail;
}

enum VerificationStatus { open, inProgress, completed, expired, failed }

class VerificationSession {
  const VerificationSession({
    required this.status,
    required this.botUsername,
    required this.deepLink,
    required this.expiresAt,
    required this.channelCount,
    required this.issue,
  });

  factory VerificationSession.fromJson(Json j) => VerificationSession(
    status: switch (j.str('status')) {
      'OPEN' => VerificationStatus.open,
      'IN_PROGRESS' => VerificationStatus.inProgress,
      'COMPLETED' => VerificationStatus.completed,
      'EXPIRED' => VerificationStatus.expired,
      'FAILED' => VerificationStatus.failed,
      final other => throw FormatException('Unknown verification status $other'),
    },
    botUsername: j.str('bot_username'),
    deepLink: j.strOrNull('deep_link'),
    expiresAt: j.time('expires_at'),
    channelCount: j.integer('channel_count'),
    issue: j.strOrNull('issue'),
  );

  final VerificationStatus status;
  final String botUsername;
  final String? deepLink;
  final DateTime expiresAt;
  final int channelCount;
  final String? issue;

  bool get isOpen => status == VerificationStatus.open || status == VerificationStatus.inProgress;
}

class Dashboard {
  const Dashboard({
    required this.user,
    required this.totalEarnedPaise,
    required this.pendingPaise,
    required this.availablePaise,
    required this.level1Count,
    required this.level1PendingCount,
    required this.referralCode,
    required this.referralLink,
  });

  factory Dashboard.fromJson(Json j) {
    final wallet = j.obj('wallet');
    final referrals = j.obj('referrals');
    final share = j.obj('share');
    return Dashboard(
      user: Me.fromJson(j.obj('user')),
      totalEarnedPaise: wallet.integer('total_earned_paise'),
      pendingPaise: wallet.integer('pending_paise'),
      availablePaise: wallet.integer('available_paise'),
      level1Count: referrals.integer('level_1_count'),
      level1PendingCount: referrals.integer('level_1_pending_count'),
      referralCode: share.str('referral_code'),
      referralLink: share.str('referral_link'),
    );
  }

  final Me user;
  final int totalEarnedPaise;
  final int pendingPaise;
  final int availablePaise;
  final int level1Count;
  final int level1PendingCount;
  final String referralCode;
  final String referralLink;
}

class LevelRow {
  const LevelRow({
    required this.level,
    required this.userCount,
    required this.rewardPerUserPaise,
    required this.totalRewardPaise,
  });

  factory LevelRow.fromJson(Json j) => LevelRow(
    level: j.integer('level'),
    userCount: j.integer('user_count'),
    rewardPerUserPaise: j.integer('reward_per_user_paise'),
    totalRewardPaise: j.integer('total_reward_paise'),
  );

  final int level;
  final int userCount;
  final int rewardPerUserPaise;
  final int totalRewardPaise;
}

class ReferralSummary {
  const ReferralSummary({
    required this.generatedAt,
    required this.refreshPending,
    required this.levels,
    required this.totalUserCount,
    required this.totalRewardPaise,
    required this.level1PendingCount,
  });

  factory ReferralSummary.fromJson(Json j) => ReferralSummary(
    generatedAt: j.time('generated_at'),
    refreshPending: j.boolean('refresh_pending'),
    levels: j.list('levels').map(LevelRow.fromJson).toList(),
    totalUserCount: j.integer('total_user_count'),
    totalRewardPaise: j.integer('total_reward_paise'),
    level1PendingCount: j.integer('level_1_pending_count'),
  );

  final DateTime generatedAt;
  final bool refreshPending;
  final List<LevelRow> levels;
  final int totalUserCount;
  final int totalRewardPaise;
  final int level1PendingCount;
}

class DirectReferral {
  const DirectReferral({
    required this.publicId,
    required this.phoneMasked,
    required this.verified,
    required this.joinedAt,
    required this.verifiedAt,
    required this.rewardPaise,
  });

  factory DirectReferral.fromJson(Json j) => DirectReferral(
    publicId: j.str('public_id'),
    phoneMasked: j.str('phone_masked'),
    verified: j.str('status') == 'VERIFIED',
    joinedAt: j.time('joined_at'),
    verifiedAt: j.timeOrNull('verified_at'),
    rewardPaise: j.integer('reward_paise'),
  );

  final String publicId;
  final String phoneMasked;
  final bool verified;
  final DateTime joinedAt;
  final DateTime? verifiedAt;
  final int rewardPaise;
}

class Paged<T> {
  const Paged(this.items, this.nextCursor);

  factory Paged.fromJson(Json j, T Function(Json) item) =>
      Paged(j.list('items').map(item).toList(), j.strOrNull('next_cursor'));

  final List<T> items;
  final String? nextCursor;
}

class ShareInfo {
  const ShareInfo({required this.referralCode, required this.referralLink, required this.apkDownloadUrl});

  factory ShareInfo.fromJson(Json j) => ShareInfo(
    referralCode: j.str('referral_code'),
    referralLink: j.str('referral_link'),
    apkDownloadUrl: j.str('apk_download_url'),
  );

  final String referralCode;
  final String referralLink;
  final String apkDownloadUrl;
}

enum EntryKind { referralReward, rewardsUnlocked, withdrawal, withdrawalReturned }

class WalletEntry {
  const WalletEntry({
    required this.id,
    required this.kind,
    required this.credit,
    required this.amountPaise,
    required this.createdAt,
    required this.counterpartyPublicId,
  });

  factory WalletEntry.fromJson(Json j) => WalletEntry(
    id: j.str('id'),
    kind: switch (j.str('kind')) {
      'REFERRAL_REWARD' => EntryKind.referralReward,
      'REWARDS_UNLOCKED' => EntryKind.rewardsUnlocked,
      'WITHDRAWAL' => EntryKind.withdrawal,
      'WITHDRAWAL_RETURNED' => EntryKind.withdrawalReturned,
      final other => throw FormatException('Unknown entry kind $other'),
    },
    credit: j.str('direction') == 'CREDIT',
    amountPaise: j.integer('amount_paise'),
    createdAt: j.time('created_at'),
    counterpartyPublicId: j.strOrNull('counterparty_public_id'),
  );

  final String id;
  final EntryKind kind;
  final bool credit;
  final int amountPaise;
  final DateTime createdAt;
  final String? counterpartyPublicId;
}

class Wallet {
  const Wallet({
    required this.totalEarnedPaise,
    required this.pendingPaise,
    required this.availablePaise,
    required this.inWithdrawalPaise,
    required this.withdrawnPaise,
    required this.payoutsOpen,
    required this.payoutOpensAt,
    required this.minWithdrawalPaise,
    required this.level1RewardCount,
    required this.level1RewardPaise,
    required this.recentEntries,
  });

  factory Wallet.fromJson(Json j) {
    final level1 = j.list('breakdown').where((row) => row.integer('level') == 1).toList();
    return Wallet(
      totalEarnedPaise: j.integer('total_earned_paise'),
      pendingPaise: j.integer('pending_paise'),
      availablePaise: j.integer('available_paise'),
      inWithdrawalPaise: j.integer('in_withdrawal_paise'),
      withdrawnPaise: j.integer('withdrawn_paise'),
      payoutsOpen: j.boolean('payouts_open'),
      payoutOpensAt: j.time('payout_opens_at'),
      minWithdrawalPaise: j.integer('min_withdrawal_paise'),
      level1RewardCount: level1.isEmpty ? 0 : level1.first.integer('reward_count'),
      level1RewardPaise: level1.isEmpty ? 0 : level1.first.integer('amount_paise'),
      recentEntries: j.list('recent_entries').map(WalletEntry.fromJson).toList(),
    );
  }

  final int totalEarnedPaise;
  final int pendingPaise;
  final int availablePaise;
  final int inWithdrawalPaise;
  final int withdrawnPaise;
  final bool payoutsOpen;
  final DateTime payoutOpensAt;
  final int minWithdrawalPaise;
  final int level1RewardCount;
  final int level1RewardPaise;
  final List<WalletEntry> recentEntries;
}

class BankDetails {
  const BankDetails({
    required this.saved,
    this.accountHolderName,
    this.accountNumberMasked,
    this.ifsc,
    this.locked = false,
  });

  factory BankDetails.fromJson(Json j) => j.str('status') == 'SAVED'
      ? BankDetails(
          saved: true,
          accountHolderName: j.str('account_holder_name'),
          accountNumberMasked: j.str('account_number_masked'),
          ifsc: j.str('ifsc'),
          locked: j.boolean('locked'),
        )
      : const BankDetails(saved: false);

  final bool saved;
  final String? accountHolderName;
  final String? accountNumberMasked;
  final String? ifsc;
  final bool locked;
}

enum WithdrawalStatus { requested, processing, paid, failed }

class Withdrawal {
  const Withdrawal({
    required this.id,
    required this.amountPaise,
    required this.status,
    required this.bankAccountMasked,
    required this.requestedAt,
    required this.paidAt,
    required this.bankReference,
    required this.failureReason,
  });

  factory Withdrawal.fromJson(Json j) => Withdrawal(
    id: j.str('id'),
    amountPaise: j.integer('amount_paise'),
    status: switch (j.str('status')) {
      'REQUESTED' => WithdrawalStatus.requested,
      'PROCESSING' => WithdrawalStatus.processing,
      'PAID' => WithdrawalStatus.paid,
      'FAILED' => WithdrawalStatus.failed,
      final other => throw FormatException('Unknown withdrawal status $other'),
    },
    bankAccountMasked: j.str('bank_account_masked'),
    requestedAt: j.time('requested_at'),
    paidAt: j.timeOrNull('paid_at'),
    bankReference: j.strOrNull('bank_reference'),
    failureReason: j.strOrNull('failure_reason'),
  );

  final String id;
  final int amountPaise;
  final WithdrawalStatus status;
  final String bankAccountMasked;
  final DateTime requestedAt;
  final DateTime? paidAt;
  final String? bankReference;
  final String? failureReason;
}
