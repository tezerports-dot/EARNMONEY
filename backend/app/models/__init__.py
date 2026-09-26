"""All tables. Importing this module registers them on ``Base.metadata``."""

from app.models.base import Base
from app.models.config import AppSettings, Campaign, MembershipCounter, RecruitmentPost
from app.models.ledger import (
    BankAccount,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    PayoutBatch,
    WithdrawalRequest,
)
from app.models.ops import AuditLog, IdempotencyKey, Job, RiskFlag
from app.models.referrals import MAX_TRACKED_LEVEL, PAID_LEVEL, ReferralEdge, ReferralReward, ReferralSnapshot
from app.models.telegram import (
    RequiredChannel,
    TelegramBot,
    TelegramJoinRequest,
    TelegramVerification,
    TelegramVerificationSession,
)
from app.models.users import AdminSession, AdminUser, AuthSession, User

__all__ = [
    "MAX_TRACKED_LEVEL",
    "PAID_LEVEL",
    "AdminSession",
    "AdminUser",
    "AppSettings",
    "AuditLog",
    "AuthSession",
    "BankAccount",
    "Base",
    "Campaign",
    "IdempotencyKey",
    "Job",
    "LedgerAccount",
    "LedgerEntry",
    "LedgerTransaction",
    "MembershipCounter",
    "PayoutBatch",
    "RecruitmentPost",
    "ReferralEdge",
    "ReferralReward",
    "ReferralSnapshot",
    "RequiredChannel",
    "RiskFlag",
    "TelegramBot",
    "TelegramJoinRequest",
    "TelegramVerification",
    "TelegramVerificationSession",
    "User",
    "WithdrawalRequest",
]
