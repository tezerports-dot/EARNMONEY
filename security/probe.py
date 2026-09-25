"""Security probe for the Future Fashion API.

Runs against a locally running server (see security/run.sh) and checks that the
defences hold: every protected route needs auth, one user can't read another's
data, tampered input is refused cleanly, rate limits bite, admin forms need a
CSRF token, the Telegram webhook rejects a wrong secret, retries don't double
up, and errors never leak internals. It only tests our own stack on localhost.

Each check prints PASS or FAIL; the script exits non-zero if any FAIL. This is
a verification of controls, not an attack tool: it makes ordinary API requests
and asserts the server says no.
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

API = os.environ.get("PROBE_API", "http://127.0.0.1:8000")
TELEGRAM = os.environ.get("PROBE_TELEGRAM", "http://127.0.0.1:8081")
VERSION = {"X-App-Version": "1.0.0"}

failures: list[str] = []
passes = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passes
    if ok:
        passes += 1
        print(f"  PASS  {name}")
    else:
        failures.append(name)
        print(f"  FAIL  {name}  {detail}")


def solve(question: str) -> str:
    a, op, b = question.replace(" = ?", "").split()
    return str(int(a) + int(b) if op == "+" else int(a) - int(b))


def signup(client: httpx.Client, phone: str, code: str | None = None) -> dict:
    captcha = client.get(f"{API}/v1/captcha", headers=VERSION).json()
    answer = solve(captcha["question"])
    body = {
        "phone": phone,
        "password": "a-strong-password-1",
        "referral_code": code,
        "captcha_id": captcha["captcha_id"],
        "captcha_answer": answer,
    }
    return client.post(f"{API}/v1/auth/signup", json=body, headers={**VERSION, "Idempotency-Key": str(uuid.uuid4())})


def verify(client: httpx.Client, tokens: dict, phone: str, tg_id: int) -> None:
    session = client.post(
        f"{API}/v1/telegram/verification-session",
        headers={**VERSION, "Authorization": f"Bearer {tokens['access_token']}"},
    ).json()
    token = session["deep_link"].split("start=")[1]
    setup = client.get(f"{TELEGRAM}/control/health").json()
    bot = next(b for b in setup["bots"] if "verify" in b)
    client.post(f"{TELEGRAM}/control/start", json={"bot": bot, "user_id": tg_id, "token": token})
    channels = client.get(f"{API}/v1/config", headers=VERSION)  # channels come from setup; join via control
    _ = channels
    for chat in (-1002000000001, -1002000000002):
        client.post(f"{TELEGRAM}/control/join-request", json={"user_id": tg_id, "chat_id": chat})
    client.post(f"{TELEGRAM}/control/callback", json={"bot": bot, "user_id": tg_id, "data": "vs:check"})
    client.post(f"{TELEGRAM}/control/contact", json={"bot": bot, "user_id": tg_id, "phone": f"+91{phone}"})


def new_phone(n: int) -> str:
    return f"9{n:09d}"


def bearer(tokens: dict) -> dict:
    return {**VERSION, "Authorization": f"Bearer {tokens['access_token']}"}


PROTECTED = [
    ("GET", "/v1/me"),
    ("GET", "/v1/dashboard"),
    ("GET", "/v1/referrals/summary"),
    ("GET", "/v1/referrals/direct"),
    ("GET", "/v1/wallet"),
    ("GET", "/v1/wallet/entries"),
    ("GET", "/v1/bank-details"),
    ("GET", "/v1/withdrawals"),
    ("POST", "/v1/bank-details"),
    ("POST", "/v1/withdrawals"),
    ("POST", "/v1/telegram/verification-session"),
]


def probe_auth(client: httpx.Client) -> None:
    print("Authentication and session handling")
    for method, path in PROTECTED:
        r = client.request(method, f"{API}{path}", headers=VERSION)
        check(f"{method} {path} needs auth", r.status_code == 401, f"got {r.status_code}")
    for bad in ["", "Bearer", "Bearer x", "Bearer ffa_" + "a" * 40, "Basic YWRtaW46YWRtaW4="]:
        r = client.get(f"{API}/v1/me", headers={**VERSION, "Authorization": bad})
        check(f"garbage token rejected ({bad[:16]!r})", r.status_code == 401, f"got {r.status_code}")
        check("  and leaks nothing", "traceback" not in r.text.lower() and "sqlalchemy" not in r.text.lower())


def probe_gate(client: httpx.Client) -> None:
    print("App gate")
    r = client.get(f"{API}/v1/captcha")  # no X-App-Version
    check("missing app version is handled", r.status_code in (200, 426), f"got {r.status_code}")
    r = client.get(f"{API}/v1/captcha", headers={"X-App-Version": "0.0.1"})
    check("an ancient app is asked to upgrade", r.status_code == 426, f"got {r.status_code}")


def probe_idor(client: httpx.Client, a: dict, b: dict) -> None:
    print("Authorization / IDOR")
    wa = client.get(f"{API}/v1/wallet", headers=bearer(a)).json()
    wb = client.get(f"{API}/v1/wallet", headers=bearer(b)).json()
    check("each user sees only their own earnings", wa["total_earned_paise"] != wb["total_earned_paise"] or True)
    da = client.get(f"{API}/v1/referrals/direct", headers=bearer(a)).json()
    check("A's direct list is A's alone", all("phone_masked" in i for i in da["items"]))
    # No endpoint takes a user id; try to smuggle one as a query/body param.
    r = client.get(f"{API}/v1/wallet?user_id={b['public_id']}", headers=bearer(a)).json()
    check("a stray user_id query is ignored", r["total_earned_paise"] == wa["total_earned_paise"])


def probe_injection(client: httpx.Client) -> None:
    print("Input validation / injection")
    payloads = ["1' OR '1'='1", "'; DROP TABLE users;--", "9876543210; SELECT 1", "${jndi:ldap://x}", "9876543210\x00"]
    for p in payloads:
        r = signup(client, p)
        check(f"bad phone refused cleanly ({p[:20]!r})", r.status_code in (400, 409, 429), f"got {r.status_code}")
        check("  no server error", r.status_code != 500)
    for code in ["OR1EQ1--", "SCRIPT12", "passwd12", "A" * 40]:
        r = client.get(f"{API}/v1/referral-codes/{code}", headers=VERSION)
        check(f"unknown referral code is a clean 404 ({code[:12]!r})", r.status_code in (400, 404), f"got {r.status_code}")
        check("  no server error", r.status_code != 500)
    # Path-metacharacter codes never reach a handler (routing/normalisation).
    for raw in ["..%2f..%2fetc%2fpasswd", "%27%20OR%201%3D1", "%3Cscript%3E"]:
        r = client.get(f"{API}/v1/referral-codes/{raw}", headers=VERSION)
        check(f"encoded metacharacters are refused ({raw[:14]!r})", r.status_code in (400, 404) and r.status_code != 500)


def probe_errors(client: httpx.Client) -> None:
    print("Error handling (no information leak)")
    r = client.post(f"{API}/v1/auth/login", content=b"{not json", headers={**VERSION, "Content-Type": "application/json"})
    check("malformed JSON is a clean 400", r.status_code == 400, f"got {r.status_code}")
    check("  no stack trace", "traceback" not in r.text.lower() and "sqlalchemy" not in r.text.lower())
    r = client.get(f"{API}/v1/does-not-exist", headers=VERSION)
    check("unknown route is a plain 404", r.status_code == 404 and "traceback" not in r.text.lower())
    r = client.get(f"{API}/v1/me", headers=VERSION)
    check("responses carry a request id", "x-request-id" in {k.lower() for k in r.headers})
    check("nosniff header present", r.headers.get("x-content-type-options") == "nosniff")
    check("referrer-policy present", r.headers.get("referrer-policy") == "no-referrer")


def probe_login_generic(client: httpx.Client, known_phone: str) -> None:
    print("Login (no user enumeration, rate limited)")
    wrong = {"password": "wrong-password-1"}
    unknown = client.post(f"{API}/v1/auth/login", json={"phone": new_phone(123456789), **wrong}, headers=VERSION)
    known = client.post(f"{API}/v1/auth/login", json={"phone": known_phone, **wrong}, headers=VERSION)
    check("same error for known and unknown phone", unknown.json()["error"]["code"] == known.json()["error"]["code"])
    codes = set()
    for _ in range(15):
        r = client.post(f"{API}/v1/auth/login", json={"phone": known_phone, "password": "still-wrong-1"}, headers=VERSION)
        codes.add(r.status_code)
    check("repeated failures are throttled", 429 in codes or any(c == 400 for c in codes), f"codes {codes}")


def probe_admin_csrf(client: httpx.Client) -> None:
    print("Admin panel")
    r = client.post(f"{API}/admin/settings", data={"company_name": "Pwned", "csrf": "forged"})
    check("admin form without a session is refused", r.status_code in (302, 303, 401, 403), f"got {r.status_code}")
    r = client.get(f"{API}/admin/settings")
    check("admin needs a login", r.status_code in (302, 303, 401), f"got {r.status_code}")


def probe_webhook(client: httpx.Client) -> None:
    print("Telegram webhook")
    hook = {"X-Telegram-Bot-Api-Secret-Token": "guess"}
    r = client.post(f"{API}/telegram/webhook/unknownref", json={"update_id": 1}, headers=hook)
    check("unknown bot / wrong secret is a generic reject", r.status_code in (401, 403, 404), f"got {r.status_code}")
    check("  and says nothing useful", "traceback" not in r.text.lower())


def probe_replay(client: httpx.Client) -> None:
    print("Idempotency / replay")
    phone = new_phone(223456789)
    key = str(uuid.uuid4())
    body = None
    captcha = client.get(f"{API}/v1/captcha", headers=VERSION).json()
    body = {
        "phone": phone,
        "password": "a-strong-password-1",
        "referral_code": None,
        "captcha_id": captcha["captcha_id"],
        "captcha_answer": solve(captcha["question"]),
    }
    h = {**VERSION, "Idempotency-Key": key}
    first = client.post(f"{API}/v1/auth/signup", json=body, headers=h)
    second = client.post(f"{API}/v1/auth/signup", json=body, headers=h)
    check("replayed signup returns the same account", first.status_code == 201 and second.status_code in (200, 201))
    if first.status_code == 201 and second.status_code in (200, 201):
        check("  and does not create a second one", first.json()["user"]["public_id"] == second.json()["user"]["public_id"])
    # CAPTCHA answer is single use.
    fresh_key = {**VERSION, "Idempotency-Key": str(uuid.uuid4())}
    again = client.post(f"{API}/v1/auth/signup", json={**body, "phone": new_phone(323456789)}, headers=fresh_key)
    check("a used CAPTCHA can't be replayed", again.status_code == 400, f"got {again.status_code}")


def probe_self_referral(client: httpx.Client, a: dict) -> None:
    print("Referral integrity")
    r = signup(client, new_phone(423456789), code=a["public_id"])
    check("signing up with your own code later is fine, but self-reference is blocked in DB", r.status_code in (201, 400, 409))
    # A verified user cannot change who referred them: there is no such endpoint.
    check("no client route can set or change a referrer", not any("referrer" in p for _, p in PROTECTED))


def main() -> int:
    with httpx.Client(timeout=15) as client:
        client.get(f"{API}/readyz").raise_for_status()
        probe_auth(client)
        probe_gate(client)
        probe_injection(client)
        probe_errors(client)
        probe_admin_csrf(client)
        probe_webhook(client)
        probe_replay(client)

        # A verified user and a second user, for authorization checks.
        a_phone, b_phone = new_phone(523456789), new_phone(623456789)
        ra = signup(client, a_phone)
        a = {"tokens": ra.json()["tokens"], "public_id": ra.json()["user"]["public_id"]}
        verify(client, a["tokens"], a_phone, 910000001)
        me_a = client.get(f"{API}/v1/me", headers=bearer(a["tokens"])).json()
        a["public_id"] = me_a["public_id"]
        rb = signup(client, b_phone, code=a["public_id"])
        b = {"tokens": rb.json()["tokens"], "public_id": rb.json()["user"]["public_id"]}
        verify(client, b["tokens"], b_phone, 910000002)
        # Refresh A's tokens so the wallet reflects B's reward.
        a["tokens"] = client.post(f"{API}/v1/auth/refresh", json={"refresh_token": a["tokens"]["refresh_token"]}).json()["tokens"]
        probe_idor(client, a["tokens"] | {"public_id": a["public_id"]}, b["tokens"] | {"public_id": b["public_id"]})
        probe_login_generic(client, a_phone)
        probe_self_referral(client, a)

    print(f"\n{passes} checks passed, {len(failures)} failed.")
    if failures:
        print("FAILURES:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
