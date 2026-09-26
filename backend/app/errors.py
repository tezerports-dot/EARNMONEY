"""Errors the API returns. Messages are safe to show to users as they are."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status: int = 400
    code: str = "BAD_REQUEST"
    message: str = "Something went wrong. Please try again."

    def __init__(
        self,
        message: str | None = None,
        *,
        fields: dict[str, str] | None = None,
        retry_after: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.fields = fields
        self.retry_after = retry_after
        self.extra = extra or {}
        super().__init__(self.message)


def _error(status: int, code: str, message: str) -> type[AppError]:
    return type(code.title().replace("_", ""), (AppError,), {"status": status, "code": code, "message": message})


ValidationFailed = _error(400, "VALIDATION_FAILED", "Please check the highlighted fields.")
CaptchaRequired = _error(400, "CAPTCHA_REQUIRED", "Please solve the check to continue.")
CaptchaInvalid = _error(400, "CAPTCHA_INVALID", "That answer didn't match. Please try a new one.")
ReferralCodeInvalid = _error(400, "REFERRAL_CODE_INVALID", "That referral code isn't valid.")
# The same error from GET /v1/referral-codes/{code}, where "no such code" is a 404.
ReferralCodeUnknown = _error(404, "REFERRAL_CODE_INVALID", "That referral code isn't valid.")
Unauthenticated = _error(401, "UNAUTHENTICATED", "Please log in again.")
SessionExpired = _error(401, "SESSION_EXPIRED", "Your session has ended. Please log in again.")
InvalidCredentials = _error(401, "INVALID_CREDENTIALS", "Phone number or password is incorrect.")
AccountNotVerified = _error(403, "ACCOUNT_NOT_VERIFIED", "Please finish Telegram verification first.")
AccountSuspended = _error(403, "ACCOUNT_SUSPENDED", "This account is suspended. Please contact support.")
NotFound = _error(404, "NOT_FOUND", "Not found.")
PhoneUnavailable = _error(409, "PHONE_UNAVAILABLE", "This number can't be used to sign up. Try logging in instead.")
AlreadyVerified = _error(409, "ALREADY_VERIFIED", "Your account is already verified.")
IdempotencyKeyReused = _error(409, "IDEMPOTENCY_KEY_REUSED", "This request was already sent with different details.")
RequestInProgress = _error(409, "REQUEST_IN_PROGRESS", "This request is still being processed. Please wait.")
WithdrawalInProgress = _error(409, "WITHDRAWAL_IN_PROGRESS", "You already have a withdrawal being processed.")
BankDetailsLocked = _error(409, "BANK_DETAILS_LOCKED", "Bank details can't change while a withdrawal is being processed.")
SignupsClosed = _error(422, "SIGNUPS_CLOSED", "Sign-ups are closed right now.")
PayoutsNotOpen = _error(422, "PAYOUTS_NOT_OPEN", "Withdrawals open on the payout date.")
BankDetailsRequired = _error(422, "BANK_DETAILS_REQUIRED", "Add your bank details before withdrawing.")
InsufficientBalance = _error(422, "INSUFFICIENT_BALANCE", "That's more than your available balance.")
BelowMinimum = _error(422, "BELOW_MINIMUM", "That's below the minimum withdrawal amount.")
UpgradeRequired = _error(426, "UPGRADE_REQUIRED", "Please update the app to continue.")
LaunchGateRequired = _error(428, "LAUNCH_GATE_REQUIRED", "Please reopen the app from Telegram to continue.")
LaunchGateMismatch = _error(
    403, "LAUNCH_GATE_MISMATCH", "Open the app's Telegram bot from the Telegram account you verified with."
)
LaunchGateInvalid = _error(400, "LAUNCH_GATE_INVALID", "That didn't work. Please start again from the app.")
RateLimited = _error(429, "RATE_LIMITED", "Too many attempts. Please try again later.")
Maintenance = _error(503, "MAINTENANCE", "We're doing some maintenance. Please try again soon.")
VerificationUnavailable = _error(
    503, "VERIFICATION_UNAVAILABLE", "Verification is busy right now. Please try again in a few minutes."
)
ServiceUnavailable = _error(503, "SERVICE_UNAVAILABLE", "The service is temporarily unavailable. Please try again.")
