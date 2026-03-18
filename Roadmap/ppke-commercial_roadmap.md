# PPKE — Full Commercial Launch Roadmap
### Panel Review: Engineering · Product · Marketing · Revenue · Legal
> **Document status:** Living roadmap — update after each phase completion.
> **Prepared for:** Solo founder / indie developer
> **Codebase status as of review:** Production-grade. 91% test coverage. Docker Compose stack. Shippable today with productization work only.

---

## Panel Members & Their Lens

| Expert | Focus | Brutal truth they bring |
|---|---|---|
| **CTO / Engineering** | Code quality, infra, security | "Ship it, but don't skip the security audit." |
| **CPO / Product** | UX, onboarding, retention | "Nobody reads your README. Fix the empty state." |
| **CMO / Marketing** | Distribution, SEO, community | "The Obsidian community will find you. Let them." |
| **CFO / Revenue** | Pricing, unit economics, LTV | "Charge more. You're worth it." |
| **Legal / Compliance** | AGPL, IP, data privacy | "GDPR and your dual license need work before you onboard Europeans." |

---

## Phase Overview

```
Phase 0   Weeks 1–2    Internal audit & hardening
Phase 1   Weeks 3–4    Hosted deployment & billing
Phase 2   Weeks 5–6    Onboarding, UX polish, landing page
Phase 3   Weeks 7–8    Soft launch — community channels
Phase 4   Weeks 9–12   Growth, templates, enterprise prep
Phase 5   Months 4–6   Scale, autonomai + ChainGuard integration
Phase 6   Months 7–12  Enterprise tier, partnerships, team
```

---

## Phase 0 — Internal Audit & Hardening
### Weeks 1–2 | Before a single user touches it

> **CTO says:** You have 91% test coverage. That's excellent. But coverage tells you lines were executed — not that the product is safe to hand to strangers with real documents. Run the full audit below before you open registration.

---

### 0.1 Feature Audit — Test Everything End-to-End

Work through every item in your README feature table as a **real user**, not as the developer who built it. Create a fresh account, a fresh vault, and execute each flow from scratch.

#### Document Ingestion
- [ ] PDF — native text extraction
- [ ] PDF — scanned/image (OCR path via Tesseract)
- [ ] DOCX upload and parsing
- [ ] EPUB ingest
- [ ] HTML / URL scraping (test 5 different real URLs)
- [ ] YouTube transcript extraction (test 3 different video types)
- [ ] CSV and Excel ingest
- [ ] ZIP archive with mixed files
- [ ] LaTeX file import
- [ ] Image with embedded text (OCR)
- [ ] Very large document (500+ pages) — does chunking hold?
- [ ] Document with unusual encoding (UTF-16, non-ASCII-heavy)
- [ ] Zotero `.bib`, `.json`, `.rdf` import
- [ ] Resume-on-failure (`--resume` flag) — kill the process mid-ingest, verify resumption

#### Query & RAG
- [ ] Single-book query with verbatim citation returned
- [ ] Cross-book query across 3+ ingested documents
- [ ] Follow-up question in chat history (context preserved)
- [ ] Query on an empty vault — graceful error, not a crash
- [ ] Very long question (500+ chars)
- [ ] Query in a non-English language (if multi-language is claimed)
- [ ] Hybrid search: confirm vector + BM25 fusion returns different results than either alone
- [ ] Semantic search — confirm conceptually related results surface without keyword match

#### Knowledge Graph
- [ ] Graph renders correctly after ingesting 1 book
- [ ] Graph renders correctly after ingesting 5+ books
- [ ] Cluster detection fires
- [ ] Path finder between two concepts works
- [ ] Gap detection — verify it surfaces a real gap on a known text
- [ ] Contradiction detection — verify it fires on a text with known contradictions
- [ ] D3.js graph is responsive on mobile and tablet (not just desktop)

#### Export Suite
- [ ] PDF export — check formatting, no broken characters
- [ ] DOCX export — verify opens cleanly in Word and LibreOffice
- [ ] PPTX export — verify opens cleanly in PowerPoint and Google Slides
- [ ] LaTeX `.tex` export — compile with `pdflatex`, confirm no errors
- [ ] BibTeX `.bib` export — verify loads into Zotero
- [ ] APA, MLA, Chicago bibliography generation — spot-check format accuracy
- [ ] Obsidian sync — two-way, SHA-256 manifest: push and pull, verify no data loss
- [ ] Literature review generation across 3 books
- [ ] Argument map generation on a known argumentative text

#### Audio
- [ ] TTS audio overview — single book
- [ ] Podcast-style cross-book episode
- [ ] RSS feed import
- [ ] Whisper transcription of uploaded audio file
- [ ] Speaker diarization on a multi-speaker recording

#### Auth & Multi-User
- [ ] Register → login → upload → query flow for a brand-new account
- [ ] JWT expiry and refresh — does the session expire cleanly?
- [ ] OAuth Google login (with env vars set)
- [ ] OAuth GitHub login (with env vars set)
- [ ] Per-user vault isolation — user A cannot see user B's documents
- [ ] Workspace creation and switching
- [ ] Annotation creation and persistence
- [ ] Password reset flow

#### Plugin Marketplace
- [ ] Browse catalog
- [ ] Install a plugin from GitHub
- [ ] Rate and review a plugin
- [ ] Submit a domain template
- [ ] Validate a custom domain template with `ppke validate-plugin`

#### CLI
- [ ] All 15 commands execute without error on a clean install
- [ ] `ppke doctor` catches a missing API key correctly
- [ ] `ppke tui` renders correctly in at least 2 terminal emulators
- [ ] `ppke cheat` prints correctly
- [ ] `ppke menu` interactive mode navigates all options

#### Infrastructure
- [ ] Docker Compose full stack starts cleanly on a fresh machine (no prior state)
- [ ] Redis connectivity — Celery workers pick up background jobs
- [ ] PostgreSQL migrations run without error
- [ ] Prometheus metrics endpoint responds
- [ ] Sentry error reporting fires on a test exception
- [ ] S3 / GCS storage integration (if configured)
- [ ] Application recovers from Redis restart without manual intervention
- [ ] Application recovers from PostgreSQL restart without manual intervention

---

### 0.2 Security Audit

> **Legal/CTO says:** Users will upload sensitive documents — legal contracts, financial reports, medical records. A breach before you have 10 users ends the company. Do this before you open registration.

#### Authentication & Access
- [ ] JWT tokens expire and cannot be replayed after logout
- [ ] No user can access another user's vault via API endpoint manipulation (IDOR test — try `/api/vault/{other_user_id}`)
- [ ] All API endpoints require authentication — check every route manually or with a script
- [ ] Rate limiting on login endpoint (prevent brute force)
- [ ] Password hashing uses bcrypt or Argon2 — not MD5/SHA1
- [ ] OAuth state parameter is validated (CSRF protection)

#### Data Isolation
- [ ] Vector DB namespaces are per-user — confirm with a direct DB query that user A's embeddings are not queryable by user B
- [ ] PostgreSQL row-level security or application-level filtering enforced on all queries
- [ ] File uploads stored with non-guessable paths (UUIDs, not sequential IDs)
- [ ] Uploaded files not accessible via direct URL without auth

#### API & Input Security
- [ ] All file upload endpoints validate MIME type and file extension (prevent `.exe` upload)
- [ ] File size limits enforced on upload
- [ ] SQL injection not possible via query parameters (test with `' OR 1=1 --`)
- [ ] XSS not possible via document titles or user-supplied text rendered in UI
- [ ] CSRF tokens on all state-changing forms (if using session cookies)
- [ ] No sensitive data (API keys, passwords) logged in application logs
- [ ] Environment variables not exposed in API responses or error messages

#### Infrastructure Security
- [ ] Production `.env` never committed to git (verify with `git log -p | grep API_KEY`)
- [ ] Docker containers run as non-root user
- [ ] No unnecessary ports exposed publicly (PostgreSQL, Redis must NOT be publicly accessible)
- [ ] HTTPS enforced on all endpoints — HTTP redirects to HTTPS
- [ ] `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` headers present
- [ ] Dependency audit: `pip audit` and `npm audit` — resolve all HIGH/CRITICAL findings

---

### 0.3 Performance Baseline

Document these numbers before launch. You need them to catch regressions and to answer enterprise questions.

| Metric | Test method | Target |
|---|---|---|
| Query response time (p50) | 10 concurrent queries on a 100-page doc | < 3 seconds |
| Query response time (p95) | same | < 8 seconds |
| Ingestion speed | 200-page PDF | < 5 min (with small_model) |
| Concurrent users | Locust load test | 50 users without errors |
| Memory per worker | `docker stats` under load | < 512MB per Celery worker |
| Cold start time | Docker Compose `up` to first request | < 30 seconds |

---

### 0.4 Legal & Compliance Foundation

> **Legal says:** Do this before the first paying user. Fixing it retroactively after you have 500 users is a nightmare.

- [ ] **Privacy Policy** — Write one. Explicitly state: what data you collect, where it's stored (country/region), how long it's retained, how users can delete their data. Use a generator like Iubenda or Termly as a starting point, then customise.
- [ ] **Terms of Service** — Minimum clauses: acceptable use, IP ownership (users own their documents and outputs), your liability limitation, cancellation/refund policy.
- [ ] **AGPL Compliance** — Your dual-license is correct. Ensure: (a) the AGPL notice is in every source file, (b) the commercial license terms are clearly written in DUAL-LICENSE.md with a contact email for enterprise sales, (c) the hosted SaaS version makes clear that AGPL-licensed use requires source disclosure.
- [ ] **GDPR (if serving EU users)** — Minimum: cookie consent banner, right-to-erasure endpoint (`DELETE /api/user/me`), data processing addendum template ready for enterprise customers, explicit statement of data residency.
- [ ] **Data Retention Policy** — Define: how long are uploaded documents stored after account cancellation? (Recommended: 30-day grace period, then permanent deletion.) State this in Privacy Policy.
- [ ] **API Key Storage** — Verify user-provided LLM API keys are encrypted at rest (not stored in plaintext in the DB). If not, fix this before launch.

---

## Phase 1 — Hosted Deployment & Billing
### Weeks 3–4 | The single most important phase

> **CPO says:** The gap between "runs on my machine" and "stranger can sign up and pay" is where most solo developer products die. This phase is entirely about closing that gap.

---

### 1.1 Cloud Infrastructure Setup

**Recommended stack for solo dev (cost-optimised):**

| Service | Purpose | Cost |
|---|---|---|
| Railway or Render | FastAPI app + Celery workers | $20–50/mo |
| Supabase | PostgreSQL + pgvector | Free–$25/mo |
| Upstash | Redis (serverless) | Free–$10/mo |
| Cloudflare R2 | File storage (S3-compatible) | $0 for first 10GB |
| Vercel | React frontend (if separated) | Free |
| Cloudflare | CDN + DDoS protection | Free |
| **Total** | | **~$30–85/mo** |

**Deployment checklist:**
- [ ] Docker Compose stack deployed and healthy
- [ ] Environment variables set securely (not hardcoded)
- [ ] Custom domain configured (e.g. `app.ppke.io`)
- [ ] HTTPS certificate provisioned and auto-renewing
- [ ] Health check endpoint (`GET /health`) returning 200
- [ ] Basic uptime monitoring (UptimeRobot — free tier is sufficient)
- [ ] Error alerting via Sentry (already in your codebase — just configure the DSN)
- [ ] Daily automated database backup (pg_dump to R2/S3)

---

### 1.2 Stripe Billing Integration

**Plan:**
- Three tiers: Researcher ($19/mo), Team ($79/mo), Enterprise ($499/mo)
- Annual discount: 20% off (increases LTV, reduces churn)
- Free trial: 14 days on Researcher and Team, no credit card required for first 7 days

**Implementation checklist:**
- [ ] Create Stripe products and price IDs for all 6 variants (3 tiers × monthly + annual)
- [ ] Stripe Checkout for new subscriptions (hosted page — fastest to implement)
- [ ] Stripe Customer Portal for self-service plan changes and cancellation
- [ ] Webhook handler for key events:
  - `checkout.session.completed` → activate workspace, set tier
  - `customer.subscription.updated` → update tier limits
  - `customer.subscription.deleted` → downgrade to free, retain data for 30 days
  - `invoice.payment_failed` → email user, grace period 3 days before suspension
- [ ] Usage metering middleware: check document count + query count against tier limits before processing; return clear `402` with upgrade CTA if exceeded
- [ ] Billing page in app settings: shows current plan, usage, next billing date, upgrade/downgrade buttons

---

### 1.3 Workspace Tier Limits (Enforcement)

| Limit | Researcher | Team | Enterprise |
|---|---|---|---|
| Users per workspace | 1 | 10 | Unlimited |
| Documents | 100 | 1,000 | Unlimited |
| Storage | 5 GB | 20 GB | Custom |
| Queries / month | 500 | 5,000 | Unlimited |
| Cross-book synthesis | No | Yes | Yes |
| Audio overviews | Yes | Yes | Yes |
| ChainGuard audit log | No | No | Yes |
| autonomai agent | No | No | Yes |
| Custom domain templates | No | Yes | Yes |
| Obsidian sync | Yes | Yes | Yes |
| API access | No | No | Yes |
| SLA | None | None | 99.9% uptime |

---

## Phase 2 — Onboarding, UX Polish & Landing Page
### Weeks 5–6

> **CPO says:** Your README is a developer manual. That is not an onboarding experience. A user who signs up and sees an empty screen with no guidance will leave in 60 seconds and never come back.

---

### 2.1 In-App Onboarding Flow

**Empty state design:**
- First login shows a welcome modal: "Welcome to PPKE. Let's set up your first workspace."
- Step 1: Choose your use case (Research, Legal, Business, Personal)
- Step 2: Upload your first document (drag-and-drop target, prominent)
- Step 3: Select domain template (based on use case chosen)
- Step 4: Watch ingestion progress in real-time (SSE stream already implemented)
- Step 5: First query prompted: "Ask anything about [document title]..."

**Pre-loaded sample workspace:**
- Every new account gets a sample workspace pre-loaded with a short public domain document (e.g. a philosophy paper or short legal brief)
- User can immediately query it, see the knowledge graph, and try export — all before uploading their own content
- Sample workspace is clearly labelled "Sample — replace with your own documents"

**Progress indicators:**
- Onboarding checklist visible in sidebar until completed (5 items: upload, query, view graph, export, invite a colleague)
- Each completed item gets a checkmark; completing all triggers a "You're set up" celebration and removes the checklist

---

### 2.2 Email Sequences

**Onboarding sequence (triggered on sign-up):**

| Day | Subject | Content |
|---|---|---|
| 0 | "Your PPKE workspace is ready" | Welcome, direct link to workspace, link to 2-min video walkthrough |
| 1 | "How to get the most out of your documents" | Explain hybrid search, show example query with citation |
| 3 | "Have you tried the knowledge graph?" | Feature spotlight on D3.js graph + contradiction detection |
| 7 | "Your trial ends in 7 days" | Soft upgrade nudge, show what they'd lose on free tier |
| 13 | "Last day of your trial" | Hard upgrade nudge, offer 20% off first month |

**Post-trial sequence (for users who don't convert):**
- Day 1 after trial ends: "What stopped you?" (single-question survey, Typeform link)
- Day 7: "We fixed [most common complaint from surveys]" (only send once you have real feedback)
- Day 30: "Come back — we've added [new feature]"

**Tool:** Use Resend (free up to 3,000 emails/month) or Postmark. Store sequences in your app or use a simple drip tool like ConvertKit.

---

### 2.3 Landing Page

**URL:** Your primary domain (not `app.ppke.io` — the marketing site is the root)

**Structure (single scroll page):**

```
HERO
  Headline: "Your documents, fully queryable.
             Cited answers. No hallucinations."
  Sub: "Upload any document. Ask anything.
        Get exact answers with verbatim citations —
        not AI guesses."
  CTA: [Start free — no credit card] [See a demo]
  Hero asset: 60-second screen recording of a real query
              returning a cited answer on a real document

SOCIAL PROOF (add after first 5 users)
  3 quotes from beta users with name, role, company

USE CASES
  Research teams      — Cross-book synthesis + argument maps
  Legal teams         — Contract analysis + audit trail
  Knowledge workers   — Obsidian sync + personal vault

FEATURE HIGHLIGHTS (3 cards)
  Verbatim citations  — "Every answer links to the exact paragraph"
  Knowledge graph     — "See how ideas connect across all your docs"
  23 formats          — "PDF, DOCX, EPUB, YouTube, HTML, and 18 more"

PRICING TABLE
  Three tiers, monthly/annual toggle, Stripe links

FOOTER
  Links: Docs, GitHub, Privacy, Terms, Contact
  "Built by [your name] · AGPL-3.0 + Commercial License"
```

**Technical implementation:**
- Build with Next.js on Vercel (free hosting, fast CDN)
- Or a single HTML file if you want to ship in 1 day — content beats tech here
- Add Plausible Analytics (privacy-first, GDPR-compliant, €9/mo) — not Google Analytics

---

### 2.4 Documentation Site

- [ ] Minimal public docs at `docs.ppke.io` (or `/docs` on main domain)
- [ ] Getting started guide (5-minute walkthrough, non-developer audience)
- [ ] Domain templates reference (what each template extracts and why)
- [ ] API reference (auto-generate from FastAPI's OpenAPI schema — already built in)
- [ ] FAQ: "Is my data private?", "Which LLM is used?", "Can I self-host?", "What's the AGPL license mean for me?"
- [ ] Use Mintlify or Docusaurus — both free, both look professional

---

## Phase 3 — Soft Launch (Community Channels)
### Weeks 7–8

> **CMO says:** You have three natural communities where PPKE is a perfect fit. Hit all three in the same week for compounding effect.

---

### 3.1 Channel Strategy

#### Channel A — Hacker News (Show HN)
**Why:** Developers, researchers, technically sophisticated users. High conversion to paying customers if the post resonates.

**Post title:** `Show HN: I built an open-source AI knowledge engine — cited answers from your own documents`

**Post body structure:**
1. The problem (2 sentences)
2. What PPKE does (3 bullet points, concrete)
3. What makes it different (verbatim citations, 23 formats, hybrid search)
4. Link to GitHub and hosted version
5. Your honest status ("solo dev, launched this week, all feedback welcome")

**Timing:** Tuesday–Thursday, 8–10am US Eastern. Never Friday or weekend.

**Do:** Respond to every comment within 2 hours. Be direct. Acknowledge criticism.
**Don't:** Ask friends to upvote. Don't post twice. Don't over-sell.

---

#### Channel B — PKM / Obsidian Community
**Why:** Your Obsidian two-way sync is a unique, high-value feature for this exact audience. They are obsessive document people who pay for good tools.

**Communities to post in:**
- r/ObsidianMD (200k+ members)
- r/PKM (50k+ members)
- r/Zettelkasten (30k+ members)
- Obsidian Discord server (#showcases channel)

**Post angle:** "I built a tool that ingests any document (PDF, EPUB, YouTube, web pages) into a queryable knowledge base and syncs it to your Obsidian vault with backlinks"

**Lead with the Obsidian sync.** Show a GIF: document ingested → knowledge graph → vault synced with `[[wikilinks]]`. That's the hook. Everything else is a bonus.

---

#### Channel C — Academic / Research Community
**Why:** Your cross-book synthesis, literature review generation, BibTeX export, Zotero import, and argument maps are purpose-built for researchers.

**Communities:**
- r/academia
- r/GradSchool
- r/PhD
- Academic Twitter/X (search for "reading papers" frustration tweets and reply helpfully)
- ResearchGate groups in relevant disciplines

**Post angle:** "I built an AI research assistant that extracts insights from papers, builds a concept graph, generates literature reviews, and exports to BibTeX — and it actually cites sources verbatim"

---

#### Channel D — LinkedIn (Professional / Enterprise angle)
**Why:** Consultants, lawyers, and business users who pay more per seat.

**Post strategy:**
- Post once per week, not once per month
- Each post highlights one specific use case with a real example
- Week 1: "How I analysed a 400-page legal contract in 10 minutes"
- Week 2: "The tool that replaced 3 hours of research with a 2-minute query"
- Week 3: Show the knowledge graph on a corpus of business documents
- Week 4: Feature spotlight on the audit trail (ChainGuard) for compliance teams

---

### 3.2 Product Hunt Launch

**Timing:** 4–6 weeks after soft launch (use soft launch feedback to polish first)

**Preparation:**
- [ ] Create a maker profile on Product Hunt well in advance
- [ ] Build a "hunter" relationship — find someone with 1,000+ followers to hunt you, or post yourself
- [ ] Prepare: 60-second demo video, 5 product screenshots, concise tagline
- [ ] Line up 20–30 people who will genuinely upvote on launch day (beta users, friends in the space — not fake accounts)
- [ ] Schedule launch for Tuesday, 12:01am US Pacific (the start of a new Product Hunt day)
- [ ] Respond to every comment on launch day

**Tagline options:**
- "AI knowledge workspace with verbatim citations — no hallucinations"
- "Turn any document into a queryable knowledge base"
- "The knowledge engine for serious document work"

---

### 3.3 Content Marketing (Starting Week 7)

> **CMO says:** Write one piece of content per week. Not for SEO (that takes months). For credibility and distribution in the communities above.

**Content calendar — first 8 weeks:**

| Week | Content | Primary channel |
|---|---|---|
| 1 | "How PPKE extracts knowledge from a 500-page book" | Hacker News, dev.to |
| 2 | "Obsidian sync deep dive — how the SHA-256 manifest works" | r/ObsidianMD, Obsidian Discord |
| 3 | "Building a knowledge graph from 20 academic papers" | r/academia, academic Twitter |
| 4 | "Why verbatim citations matter (and why RAG usually fails at this)" | LinkedIn, dev.to |
| 5 | "From PDF to podcast: PPKE's audio overview feature" | r/PKM, LinkedIn |
| 6 | "How I built hybrid search (BM25 + vector) — what I learned" | Hacker News, dev.to |
| 7 | "PPKE vs. Elicit vs. Notion AI — an honest comparison" | r/academia, LinkedIn |
| 8 | "The argument map feature: turning a legal brief into a visual logic tree" | LinkedIn, legal subreddits |

---

## Phase 4 — Growth, Templates & Enterprise Prep
### Weeks 9–12

---

### 4.1 Domain Template Library (Distribution Engine)

> **CMO says:** Each domain template is a targeted distribution channel. "AI for legal contracts" reaches lawyers. "AI for medical literature" reaches clinicians. Launch them as separate micro-announcements.

**Templates to build and launch (one per week):**

| Template | Target audience | Key extractions | Distribution channel |
|---|---|---|---|
| Legal contracts | Lawyers, legal ops | Obligations, parties, deadlines, risk clauses | r/LegalAdvice, LinkedIn legal groups |
| Scientific papers | Researchers, PhD | Hypotheses, methods, findings, limitations | r/academia, ResearchGate |
| Financial reports | Analysts, CFOs | KPIs, risks, forward guidance, comparatives | r/finance, LinkedIn finance |
| Medical literature | Clinicians, researchers | Interventions, outcomes, patient populations | r/medicine, medical Twitter |
| HR policies | HR managers, legal | Policies, obligations, compliance requirements | HR LinkedIn groups |
| Regulatory docs | Compliance teams | Requirements, deadlines, penalties, changes | Compliance LinkedIn groups |
| Investor reports | VCs, analysts | Thesis, portfolio, market views | r/investing, VC Twitter |
| Technical specs | Engineers | Requirements, constraints, interfaces, risks | Hacker News, dev.to |

**Each template launch:**
1. Post in the relevant community: "I built a domain-specific AI template for [audience]"
2. Show a real example with a real (public) document
3. Link to the hosted version with a 14-day trial CTA

---

### 4.2 SEO Foundation

> **CMO says:** SEO is a 6–12 month investment. Start now so it pays off in Month 6.

**Target keywords (low competition, high intent):**

| Keyword | Search volume | Difficulty | Content type |
|---|---|---|---|
| "AI PDF question answering" | 2,400/mo | Low | Landing page section |
| "knowledge graph from documents" | 880/mo | Low | Blog post + feature page |
| "AI research assistant citations" | 720/mo | Low | Blog post |
| "Obsidian AI plugin" | 1,600/mo | Medium | Blog post |
| "document chat with citations" | 590/mo | Low | Feature page |
| "legal contract AI analysis" | 1,900/mo | Medium | Template landing page |
| "literature review generator AI" | 2,100/mo | Medium | Feature page |
| "Elicit alternative" | 480/mo | Low | Comparison page |

**Actions:**
- [ ] Submit sitemap to Google Search Console on launch day
- [ ] Write 1 long-form SEO article per month (2,000+ words, target one keyword)
- [ ] Create individual landing pages for the 3 highest-volume domain templates
- [ ] Add structured data (FAQ schema) to landing page

---

### 4.3 Metrics & Analytics Setup

> **CPO says:** You cannot improve what you cannot measure. Set this up before you have users, not after.

**Product metrics to track (weekly):**

| Metric | Tool | Why it matters |
|---|---|---|
| Sign-ups | Plausible + DB query | Top of funnel health |
| Trial → paid conversion rate | Stripe + DB | Should be 15–25% for a B2B tool |
| Documents ingested per user | DB query | Activation metric |
| Queries per user per week | DB query | Engagement / retention signal |
| Day 7 retention | DB query | Predicts long-term retention |
| Day 30 retention | DB query | Revenue predictor |
| MRR + MRR growth | Stripe | Revenue health |
| Churn rate | Stripe | Sustainability |
| NPS score | In-app survey (Delighted) | Product-market fit signal |

**Target benchmarks for a B2B SaaS:**
- Trial → paid: 15–25%
- Day 30 retention: 40%+
- Monthly churn: < 5%
- NPS: > 30

---

### 4.4 Customer Support Infrastructure

- [ ] **Helpdesk:** Crisp (free tier) or Intercom (paid) — live chat on the app
- [ ] **Support email:** support@[yourdomain].io — use Missive or HelpScout
- [ ] **Status page:** Instatus (free) — show uptime and incidents at status.[yourdomain].io
- [ ] **Response time SLA (self-imposed):** 
  - Researcher: 48 hours email
  - Team: 24 hours email + live chat
  - Enterprise: 4 hours + dedicated Slack channel

---

## Phase 5 — autonomai + ChainGuard Integration
### Months 4–6

> **CTO says:** These are your two strongest competitive moats. Both are already built. The work here is integration and productization — not invention.

---

### 5.1 autonomai Agent Layer

**What it adds to PPKE:**
Every workspace has a "retrieval personality" — a set of instructions for how to retrieve and rank results. autonomai's critic-actor loop watches query feedback (thumbs up/down, explicit corrections) and gradually rewrites these instructions per workspace. The longer a team uses PPKE, the better it gets at their specific documents and query patterns.

**Integration plan:**

1. **Feedback collection** (Week 1 of this phase)
   - Add thumbs up/down to every query response
   - Add optional free-text feedback: "What was wrong with this answer?"
   - Store all feedback events in a `query_feedback` table with query_id, rating, correction, timestamp

2. **Critic pipeline** (Week 2)
   - Batch feedback events per workspace daily
   - Critic LLM (autonomai) evaluates: "Given these queries and feedback, what retrieval instructions should change?"
   - Output: scored list of instruction patches

3. **Actor pipeline** (Week 3)
   - Actor LLM applies top-scored patches to workspace retrieval instructions
   - New instructions stored per-workspace in DB
   - Next queries use updated instructions

4. **Monitoring** (Week 4)
   - Track per-workspace query satisfaction score over time
   - Show users a "Your workspace has improved X times" indicator
   - Admin dashboard shows which workspaces have most active critic loops

**Tier placement:** Enterprise only at launch. Graduate to Team tier after 3 months of stability data.

---

### 5.2 ChainGuard Audit Layer

**What it adds to PPKE:**
Every document upload, query, answer, export, and user action is written to a tamper-evident append-only log. Each entry is cryptographically chained. Any modification to historical records is immediately detectable. This is what lawyers, compliance teams, and regulated enterprises need.

**Integration plan:**

1. **Port ChainGuard to Python sidecar** (or keep as .NET and call via HTTP internally)
   - Expose `POST /audit/log` endpoint (internal only, not public)
   - PPKE calls this endpoint for every auditable event

2. **Define auditable events:**
   - `document.uploaded` — user_id, workspace_id, filename, hash, timestamp
   - `query.executed` — user_id, workspace_id, query_text, answer_hash, model_used, timestamp
   - `document.exported` — user_id, workspace_id, format, timestamp
   - `user.login` — user_id, IP, timestamp
   - `user.invite_sent` — sender_id, recipient_email, timestamp
   - `workspace.settings_changed` — user_id, field, old_value, new_value, timestamp

3. **Audit log viewer** in the Enterprise dashboard:
   - Filterable by user, event type, date range
   - Export to CSV for compliance reporting
   - "Verify integrity" button that re-validates the entire chain
   - Tamper alert if any record has been modified

4. **Compliance marketing copy:**
   - "Every action your team takes with your documents is immutably logged"
   - "Pass legal discovery, SOX audits, and GDPR data access requests in minutes"
   - This copy is what makes a lawyer say yes to a $499/mo contract

---

## Phase 6 — Enterprise Tier, Partnerships & Team
### Months 7–12

> **CFO says:** Two Enterprise customers ($499/mo each) equal 52 Researcher customers. Every enterprise deal you close this year is worth fighting for.

---

### 6.1 Enterprise Sales Motion

**Target companies:**
- Law firms: 5–50 attorneys, no existing document AI tooling
- Consultancies: 20–200 employees, heavy document workload
- Compliance teams at mid-size financial firms
- Academic publishers and research institutes

**Outreach process:**

1. **Find 50 targets** on LinkedIn using Sales Navigator (free 30-day trial):
   - Title: "Knowledge Manager", "Legal Operations", "Research Director", "Chief Compliance Officer"
   - Company size: 20–500 employees
   - Industry: Legal, Consulting, Financial Services, Research

2. **Personalised LinkedIn DM (not a template blast):**
   > "Hi [name], I noticed [firm] works heavily with [contracts / research / regulatory docs]. I built a tool that lets teams query their entire document library with verbatim citations and a full audit trail — no Glean-scale contract needed. Would you try it free for 30 days? Happy to set it up personally."

3. **Discovery call (30 min):**
   - Ask: "What does your current document workflow look like?"
   - Ask: "Where do you lose the most time in research or review?"
   - Show: live demo with a document similar to what they use
   - Close: "What would it take for this to be worth $499/month to your team?"

4. **Follow-up:**
   - Send a personalised workspace set up with their sample documents before the next call
   - If they ask for a security review: send your privacy policy, data residency statement, and offer a private deployment option

---

### 6.2 Partnership Channels

| Partner type | Who | What they get | What you get |
|---|---|---|---|
| Obsidian plugin ecosystem | Obsidian community developers | Revenue share on referrals | Distribution to 1M+ Obsidian users |
| Zotero power users | Academic Twitter influencers | Free Enterprise account | Posts to research community |
| Legal tech consultants | Independent legal ops consultants | 20% referral commission | Warm intros to law firm buyers |
| Academic librarians | University library associations | Institutional pricing | Access to university procurement channels |
| Note-taking YouTubers | Ali Abdaal, Tiago Forte adjacent creators | Affiliate commissions | Exposure to PKM audience |

---

### 6.3 Pricing Evolution

**Year 1 pricing (launch):**

| Tier | Monthly | Annual | Annual savings |
|---|---|---|---|
| Researcher | $19/mo | $182/yr | $46 (20%) |
| Team | $79/mo | $758/yr | $190 (20%) |
| Enterprise | $499/mo | $4,790/yr | $1,198 (20%) |

**When to raise prices (signals to watch for):**
- Trial → paid conversion exceeds 30% (demand exceeds friction — room to raise)
- 3+ enterprise customers asking for features you don't have yet (they're committed)
- Churn rate below 3% for 3 consecutive months (strong retention = strong value)

**Year 2 pricing target:**
- Researcher: $29/mo
- Team: $119/mo
- Enterprise: $799/mo
- New tier: **Agency / White-label** at $1,499/mo (resellers who embed PPKE for clients)

---

### 6.4 Hiring (When, Not If)

**Do not hire until:**
- MRR exceeds $8,000/month consistently for 3 months
- You are personally spending more than 30% of your time on support or ops

**First hire: Part-time customer success / community manager**
- Remote, async-first
- Owns: community posts, support tickets, user onboarding calls
- Cost: $1,500–2,500/mo (part-time)
- Frees you to: build, sell, write

**Second hire: Full-stack developer (if MRR > $15k)**
- Owns: features requested by enterprise customers
- Enables: faster iteration on the template library and integrations

---

## Advertising Strategy

> **CMO says:** Do not spend on ads until you have product-market fit signals (Day 30 retention > 40%, NPS > 30, trial → paid > 15%). Ads amplify what's already working — they don't fix what isn't.

### Pre-PMF (Months 1–3): Zero paid advertising

Spend your budget on:
- Crisp chat ($0 free tier)
- Plausible Analytics ($9/mo)
- Resend email ($0 free tier)
- Mintlify docs ($0 free tier)
- Your time on community posts and direct outreach

### Post-PMF (Months 4–6): Small, targeted experiments

**Budget: $300–500/month total**

| Channel | Budget | Target | Why |
|---|---|---|---|
| Reddit ads | $100/mo | r/ObsidianMD, r/academia | High intent, low CPM, your exact audience |
| Twitter/X promoted posts | $100/mo | Researchers, PKM community | Boost your best organic posts |
| Google Search | $200/mo | "AI PDF question answering", "knowledge graph documents" | High intent, direct CTR to trial |

**What to measure:** Cost per trial sign-up (target: < $15). Cost per paid conversion (target: < $150). If either metric is worse after 30 days, pause and fix the product first.

### Scale (Months 7–12): Invest what's working

- Double budget on the channel with lowest cost-per-conversion
- Add LinkedIn ads only for Enterprise targeting (higher CPM, worth it for $499/mo deals)
- Explore sponsorships: Obsidian-related YouTube channels, academic newsletters

---

## Financial Model

### Unit Economics

| Metric | Researcher | Team | Enterprise |
|---|---|---|---|
| Monthly price | $19 | $79 | $499 |
| Est. LTV (12-month) | $180 | $758 | $4,790 |
| Est. CAC (community) | $10–20 | $20–50 | $100–300 |
| LTV:CAC ratio | 9–18× | 15–38× | 16–48× |
| LLM API cost/user/mo (est.) | $1–3 | $5–15 | $20–80 |
| Gross margin | ~80–85% | ~80–85% | ~80–85% |

### Revenue Projections (Conservative)

| Month | Researcher | Team | Enterprise | MRR |
|---|---|---|---|---|
| 1 | 15 | 3 | 0 | $522 |
| 2 | 30 | 8 | 0 | $1,202 |
| 3 | 60 | 15 | 1 | $2,824 |
| 4 | 100 | 25 | 2 | $4,875 |
| 6 | 200 | 50 | 5 | $8,245 |
| 9 | 350 | 90 | 10 | $17,760 |
| 12 | 500 | 140 | 20 | $29,560 |

**Key milestone:** $3,000/mo MRR (Month 3) = ramen profitable for a solo dev in most European cities. $10,000/mo MRR (Month 7) = comfortable full-time income, no day job needed.

### Infrastructure Cost Scaling

| MRR range | Est. infra cost | Notes |
|---|---|---|
| $0–2k | $50–80/mo | Single Railway instance, Supabase free |
| $2k–10k | $150–300/mo | Scale Celery workers, upgrade Supabase |
| $10k–30k | $400–800/mo | Add read replicas, dedicated Redis, CDN |
| $30k+ | $1,000–2,000/mo | Consider dedicated servers for Enterprise |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| OpenAI / Anthropic API price change | Medium | High | Multi-LLM routing already built — switch providers in config |
| Large competitor copies the product | Medium | Medium | Your moat is the combination + community + templates — not any single feature |
| AGPL compliance challenge | Low | High | Ensure every commercial customer signs the commercial license; keep AGPL notice in all files |
| Data breach (user documents) | Low | Critical | Phase 0 security audit; encryption at rest and in transit; no shared embeddings between tenants |
| Churn above 10%/month | Medium | High | Fix onboarding first; survey every churned user within 48 hours |
| LLM hallucination causing harm | Medium | Medium | Verbatim citations are your defense; prominently state "verify all AI-generated content" in UI |
| Solo dev burnout | High | Critical | Scope Phase 0–2 tightly; don't add features until Phase 1 revenue is live; take Sundays off |

---

## Success Metrics by Phase

| Phase | Key metric | Target |
|---|---|---|
| Phase 0 | All audit checklists complete | 100% |
| Phase 1 | Hosted version live, Stripe billing working | First $1 charged |
| Phase 2 | Onboarding complete rate | > 60% of sign-ups complete all 5 steps |
| Phase 3 | Trial sign-ups from community launch | > 200 in first 2 weeks |
| Phase 3 | Paying customers | > 10 |
| Phase 4 | Day 30 retention | > 40% |
| Phase 4 | Trial → paid conversion | > 15% |
| Phase 5 | Enterprise customers | > 3 |
| Phase 5 | MRR | > $5,000 |
| Phase 6 | MRR | > $10,000 |
| Phase 6 | NPS | > 30 |

---

## The One Thing Per Week (Anti-Overwhelm Summary)

| Week | Single most important action |
|---|---|
| 1 | Complete Phase 0 security checklist — don't skip this |
| 2 | Complete feature audit, fix all P0 bugs |
| 3 | Deploy hosted version at a real domain |
| 4 | Wire in Stripe — charge the first dollar |
| 5 | Build onboarding flow and empty state |
| 6 | Write the landing page and deploy it |
| 7 | Post on Hacker News and r/ObsidianMD on the same day |
| 8 | Email every trial user personally and book 3 discovery calls |
| 9 | Launch first domain template (legal contracts) with targeted post |
| 10 | Set up analytics dashboard — know your conversion rate |
| 11 | Launch Product Hunt |
| 12 | Send 20 personalised LinkedIn DMs to enterprise targets |

---

*Last updated: March 2026*
*Review this document after each phase. Update targets based on real data, not projections.*
*The goal is not to follow the roadmap perfectly — it is to ship, learn, and adjust.*
