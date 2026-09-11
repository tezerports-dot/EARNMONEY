# Skills.md — Claude Code Project Skills

This project should be developed using modular Claude Code skills.

## Required Skills

### 1. frontend
Build and maintain Next.js/TypeScript UI.

Responsibilities:
- Components
- Pages
- Forms
- Validation
- Accessibility
- Responsive layouts
- API integration

### 2. backend
Build Node.js/TypeScript APIs.

Responsibilities:
- Controllers/routes
- Services
- DTOs
- Authorization
- Validation
- Error handling

### 3. database
Manage PostgreSQL schema and migrations.

Responsibilities:
- Schema
- Migrations
- Indexes
- Constraints
- Transactions
- Query performance

### 4. auth-security
Implement:
- Password hashing
- Sessions
- CAPTCHA
- Rate limits
- RBAC
- MFA for admins
- Security headers
- Audit logging

### 5. referral-engine
Implement referral state machine.

Must guarantee:
- No self-referral
- No duplicate credit
- Transactional credit
- Explainable rejection
- Fraud review hooks

### 6. identity-integration
Implement the approved identity/KYC provider abstraction.

Never invent or scrape an Aadhaar API.

### 7. telegram-integration
Implement Telegram Bot API integration:
- deep links
- contact sharing
- webhook handling
- join requests
- membership reconciliation

### 8. admin
Build recruitment operations console.

### 9. testing
Write:
- unit tests
- integration tests
- security tests
- end-to-end tests

### 10. devops
Maintain:
- Docker
- CI/CD
- environment configuration
- migrations
- monitoring
- backups

## Skill Workflow

Before changing code:
1. Read relevant skill.
2. Inspect current architecture.
3. Identify affected modules.
4. Make smallest safe change.
5. Run targeted tests.
6. Run full relevant test suite.
7. Update documentation.

## Definition of Done

A feature is not complete until:
- TypeScript passes.
- Lint passes.
- Tests pass.
- Authorization is tested.
- Error states are handled.
- Sensitive data is not logged.
- Migration is included where needed.
- Documentation is updated.
