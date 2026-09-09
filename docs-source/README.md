# Job Referral Platform — Claude Code Specification Pack

Files:
1. `01-PRD.md` — product requirements
2. `02-TRD.md` — technical requirements
3. `03-UI-UX-DESIGN.md` — UI/UX specification
4. `04-BACKEND-SCHEMA.md` — PostgreSQL backend schema
5. `05-ARCHITECTURE.md` — system architecture
6. `06-SKILLS.md` — Claude Code skills structure
7. `07-AGENT-RULES.md` — implementation guardrails

## Recommended Claude Code startup

Tell Claude Code:

> Read all markdown files in this specification pack before making implementation decisions. Treat `07-AGENT-RULES.md` as mandatory project rules. Build the application incrementally, beginning with repository structure, database schema/migrations, authentication, then identity/KYC abstraction, Telegram integration, referral engine, candidate dashboard, admin panel, applications and training. Do not implement raw Aadhaar sharing. Use synthetic data in development.

## Important pre-launch dependencies

The technical specification assumes:
- a legally reviewed identity/KYC approach;
- an approved identity verification provider where required;
- verified employment/vacancy documentation;
- privacy notice and consent language;
- Telegram bot and admin permissions;
- recruitment/admin operating procedures.
