# Security Architecture

Standards: OWASP ASVS (target Level 2; Level 3 for credential and tenancy handling), OWASP Top 10, OWASP API
Security Top 10, OWASP LLM Top 10 for the AI service.

## 1. Assets, ranked
1. **Broker credentials** (client PIN, TOTP secret, API keys). A PIN plus TOTP secret is enough to log in as the
   user; the same Angel session can place orders (placeOrder is in the published rate-limit table) [V]. Highest-value asset.
2. User accounts, saved strategies and research (intellectual property).
3. Licensed market data (contractual exposure if leaked).
4. Platform availability and integrity of data (a wrong price is a security and safety issue).

## 2. Threat model (STRIDE summary)

| Threat | Example | Primary controls |
|---|---|---|
| Spoofing | Stolen session, credential stuffing | Argon2id, MFA, device/session binding, login throttling |
| Tampering | Edited backtest or scan results, poisoned data | Immutable `data_version`, hash-chained audit log, signed exports |
| Repudiation | "I never changed that strategy" | Append-only audit log with actor, IP, diff |
| Information disclosure | Leaked broker keys, cross-tenant read | Envelope encryption, row-level tenancy, no secrets in logs |
| Denial of service | Scan flooding, expensive backtests | Cloudflare, per-tenant quotas, job caps, timeouts |
| Elevation | Role bypass, SSRF, injection | RBAC deny-by-default, validation, egress allow-list |
| LLM-specific | Prompt injection producing unsafe output | DSL-only output, schema validation, no tool access to secrets |

## 3. Secrets and credentials

**Rule: credentials are never pasted into chat, issues, commits, or logs.** When Phase 1 reaches the Angel
integration I will define a secure intake (for example a local `.env` file or a secrets manager entry you create
yourself). Listing the variable names is fine; the values are not to be shared with me.

- **Self-hosted / personal mode.** Secrets live in environment variables or a secrets manager; `.env` is
  git-ignored; file mode 600.
- **SaaS mode.** Prefer **not holding users' TOTP secrets at all**: let the user complete the daily login in their
  own browser or device and pass only the resulting short-lived session token. If TOTP secrets must be stored
  for unattended login, use a Vault transit engine or cloud KMS with envelope encryption (per-user data keys),
  an isolated "credential service" with no inbound internet access, and strict audit.
- **Least privilege.** Use read-only or data-only key scopes where a provider offers them (verify per provider;
  Delta requires IP whitelisting for trading-permission keys [V]). This product implements **no order
  placement**, so no execution keys are required or accepted.
- Rotation: documented procedure, automated reminders, immediate revocation path.
- Secret scanning in CI (gitleaks or equivalent) and pre-commit.

## 4. Identity and access
- Auth: email + passwordless or Argon2id password, mandatory TOTP/WebAuthn for paid and admin accounts,
  short-lived access tokens, rotating refresh tokens, server-side revocation.
- **RBAC** roles: `learner`, `trader`, `pro`, `team_admin`, `org_admin`, `platform_admin`, `support (read-only,
  time-boxed, audited)`. Deny by default; permission checks at the service layer, not only the route.
- Tenancy: `tenant_id` on every row, enforced by Postgres row-level security as a second line of defence.
- API keys for B2B: hashed at rest, scoped, per-key rate limits, IP allow-lists.

## 5. Data protection
- TLS 1.2+ everywhere (1.3 preferred), HSTS; mTLS between internal services at S2+.
- Encryption at rest for databases, object storage and backups; encrypted backups tested by restore drills.
- PII minimised; retention schedule; deletion on request; data-residency note for India (DPDP Act obligations
  to be reviewed by counsel [U]).

## 6. Application security (OWASP)
- Input validation with strict schemas (Pydantic, Zod); allow-lists for symbols, intervals, units.
- **No dynamic evaluation of user input.** Strategies are validated logic graphs interpreted by a fixed engine
  (already the model in the current app).
- Parameterised SQL only; ORM or query builder; no string-built queries (DuckDB included).
- CSP with no inline scripts, strict CORS, CSRF protection for cookie sessions, secure cookie flags.
- SSRF: outbound requests only to allow-listed provider hosts.
- File exports: generated server-side from validated data, content-type forced, filenames sanitised.
- Rate limiting at three layers: Cloudflare, gateway, per-tenant application limits (scan, backtest, AI).
- Error handling that never leaks stack traces or internals.

## 7. AI-specific controls
- The model returns **JSON matching a schema**; it cannot execute code, call arbitrary tools or read secrets.
- Treat user text and any retrieved content as untrusted (prompt injection). No instructions from data.
- Output filter enforces the language policy (no BUY/SELL/HOLD/targets) before display.
- Per-user token and cost budgets; logs redact secrets; evaluation suite includes adversarial prompts.

## 8. Supply chain and pipeline
- Pinned dependencies with hashes, Dependabot/Renovate, `pip-audit` and `npm audit` in CI (the current app
  already runs bandit and pip-audit), Trivy image scanning, SBOM generation, signed images (cosign).
- Branch protection, mandatory review, CI required checks, no direct pushes to main, secrets only via the CI
  secret store, OIDC to cloud instead of long-lived keys.
- **Security review gate** at the end of every phase (see TEST_PLAN) and a third-party penetration test before
  the first paying customer.

## 9. Logging, audit and monitoring
- Append-only, hash-chained audit log: logins, role changes, credential access, strategy edits, exports,
  admin actions. Retention per policy.
- Security monitoring: failed-login spikes, impossible travel, unusual export volume, credential-service access.
- Incident response runbook with severity levels, contact tree, key-rotation steps, user notification template.

## 10. DDoS and resilience
Cloudflare WAF and rate rules, origin locked to Cloudflare IPs, autoscaling limits, queue-based heavy jobs,
timeouts and circuit breakers on every provider call, graceful degradation (cached data with a visible
"stale" label) rather than blank screens.

## 11. Regulatory notes (not legal advice)
- SEBI's retail algo framework (effective 2026-04-01) concerns order execution: static IP registered with the
  broker, a 10 orders-per-second threshold, no market or IOC algo orders [V Angel One notice]. A data-only
  educational product avoids execution, but **confirm with Angel support that read-only SmartAPI use is
  unaffected**.
- Output language ("context, scenarios, teaching notes") reduces but does not remove the risk of being treated as
  investment advice or research. Obtain an opinion on SEBI Research Analyst / Investment Adviser rules before
  launch; publish clear disclaimers.
- Exchange data licensing (NSE Non-Display / redistribution) is a legal precondition for SaaS (RESEARCH §5.4).
