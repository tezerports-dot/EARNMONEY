// ---- Capacity & sharding (Section 2 of spec) ----
export const CHANNEL_SHARD_CAPACITY = 1_000_000;
export const CHANNEL_SHARD_NEAR_CAPACITY_AT = 950_000;

export const GROUP_SHARD_CAPACITY = 200_000;
export const GROUP_SHARD_NEAR_CAPACITY_AT = 180_000;

// ---- Activation / deactivation timing (Section 3) ----
export const ACTIVATION_DUAL_MEMBERSHIP_HOURS = 24;
export const DEACTIVATION_ABSENCE_HOURS = 72;

// ---- Fraud scoring weights (Section 3) ----
export const FRAUD_WEIGHTS = {
  SAME_IP_MULTI_ACCOUNT: 20, // Same IP creates 5+ accounts/day
  DEVICE_FINGERPRINT_REUSE: 30, // Same device fingerprint reused
  RAPID_JOIN_LEAVE_CYCLING: 25, // Rapid join/leave cycling
  MASS_REFERRAL_CREATION: 15, // Mass referral creation
} as const;

export const FRAUD_THRESHOLDS = {
  FLAG_FOR_REVIEW: 40, // 40-69 => flag
  SUSPEND: 70, // 70+   => suspend
} as const;

export const SAME_IP_ACCOUNTS_PER_DAY_THRESHOLD = 5;
export const MASS_REFERRAL_PER_DAY_THRESHOLD = 20;
export const RAPID_CYCLE_WINDOW_HOURS = 24;
export const RAPID_CYCLE_MIN_EVENTS = 3;

// ---- Payout bounds (Section 4) ----
export const PAYOUT_MIN_INR = 1;
export const PAYOUT_MAX_INR = 5;

// ---- Worker scheduling ----
export const MEMBERSHIP_CHECK_INTERVAL_HOURS = 6;

// ---- Referral code ----
export const REFERRAL_CODE_PREFIX = 'REF_';
export const REFERRAL_CODE_LENGTH = 8; // characters after prefix
