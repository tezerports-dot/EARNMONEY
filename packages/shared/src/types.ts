export type UserStatus = 'PENDING' | 'JOINING' | 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';
export type ShardStatus = 'ACTIVE' | 'NEAR_CAPACITY' | 'DISABLED';
export type PayoutStatus = 'PENDING' | 'PAID' | 'FAILED';
export type AdminRole = 'SUPER_ADMIN' | 'OPERATOR' | 'FINANCE';

export interface BankDetails {
  bankAccountHolder: string;
  bankAccountNumber: string;
  bankIfsc?: string | null;
  bankUpiId?: string | null;
}

export interface ShardAssignmentResult {
  channelId: string;
  channelInviteLink: string;
  groupId: string;
  groupInviteLink: string;
}

export interface PublicUserStatus {
  referralCode: string;
  status: UserStatus;
  activeReferralCount: number;
  thisMonthPayoutInr: number | null;
  lifetimePaidInr: number;
}

export interface JwtAdminPayload {
  sub: string; // admin id
  username: string;
  role: AdminRole;
}

export interface FraudCheckInput {
  userId: string;
  ipHash?: string | null;
  deviceFingerprint?: string | null;
}

export interface FraudCheckResult {
  score: number;
  reasons: string[];
  action: 'NORMAL' | 'FLAG' | 'SUSPEND';
}
