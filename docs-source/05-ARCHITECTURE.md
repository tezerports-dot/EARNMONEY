# Architecture.md

## 1. High-Level Architecture

```text
                         ┌─────────────────────┐
                         │   Candidate Web App │
                         │ Next.js / TypeScript│
                         └──────────┬──────────┘
                                    │ HTTPS
                                    ▼
                         ┌─────────────────────┐
                         │ API / Auth Service  │
                         │ Node.js + TypeScript│
                         └──────┬───────┬──────┘
                                │       │
                    ┌───────────┘       └──────────────┐
                    ▼                                  ▼
             ┌──────────────┐                  ┌──────────────┐
             │ PostgreSQL   │                  │    Redis     │
             │ System Record│                  │ queue/cache  │
             └──────────────┘                  └──────┬───────┘
                                                      ▼
                                               ┌─────────────┐
                                               │ Worker Jobs │
                                               └──────┬──────┘
                                                      │
                    ┌─────────────────────────────────┼────────────────────┐
                    ▼                                 ▼                    ▼
          ┌─────────────────┐                ┌────────────────┐   ┌────────────────┐
          │ Identity/KYC   │                │ Telegram Bot   │   │ Notifications  │
          │ Provider       │                │ Integration    │   │ Email/SMS/etc. │
          └─────────────────┘                └────────────────┘   └────────────────┘
```

## 2. Service Boundaries

### Web
Responsible for UI only.

### API
Responsible for:
- Authentication
- Authorization
- Business rules
- Referral state transitions
- Applications
- Candidate status

### Worker
Responsible for:
- Identity webhook processing
- Telegram reconciliation
- Challenge generation
- Notifications
- Fraud scoring
- Batch processing

### Admin
Separate route/application boundary with stronger authentication and RBAC.

## 3. Data Boundary

Sensitive identity data should be isolated from ordinary candidate data.

Recommended:
- Operational DB contains provider references, masked values and status.
- Sensitive vault contains only permitted identity data.
- Application servers access sensitive values through narrow service methods.
- Admin access is logged.

## 4. Telegram Flow

```text
Candidate
   │
   ▼
Website → one-time signed token
   │
   ▼
Telegram Bot
   │
   ├─ share contact
   ▼
Backend verifies binding
   │
   ├─ private channel join request
   └─ private group join request
   │
   ▼
Telegram webhook
   │
   ▼
Backend authorization check
   │
   ▼
Approve / reject request
```

## 5. Referral Flow

```text
Referral URL
     │
     ▼
Signup
     │
     ▼
referrer attribution
     │
     ▼
Identity verified
     │
     ▼
Referral eligible
     │
     ▼
Fraud / duplicate checks
     │
     ▼
Referral credited
     │
     ▼
Candidate progress updated
```

## 6. Deployment

Production:
- CDN/WAF
- Load balancer
- 2+ API instances
- 2+ worker instances
- Managed PostgreSQL with automated backups
- Redis with persistence appropriate to workload
- Object storage
- Monitoring/logging
- Secrets manager

## 7. Environments

- local
- development
- staging
- production

Never use production identity data in development.

## 8. Backup / Recovery

Targets should be defined before launch:
- RPO: ≤ 15 minutes
- RTO: ≤ 2 hours

Perform restore drills.

## 9. Failure Handling

Identity provider unavailable:
- Candidate sees `Verification temporarily unavailable`.
- Retry is asynchronous.

Telegram unavailable:
- Keep account state.
- Retry webhook reconciliation.

Database unavailable:
- Fail closed for critical state transitions.
- Never grant referral credit based on cached counters.

## 10. Architecture Principles

- Server authoritative.
- Privacy by design.
- Least privilege.
- Idempotent webhooks.
- Transactional state transitions.
- No sensitive data in logs.
- No direct database access from frontend.
