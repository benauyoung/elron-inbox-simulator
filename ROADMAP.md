# Roadmap — Elron Inbox Simulator

Current status: **v2.0 — Live and functional** (Feb 2026)

---

## Completed (v2.0)

- [x] Pre-scripted storylines replacing random email generation
- [x] 530 emails across 30 interconnected storylines
- [x] 7 sequential batch injection buttons (History, Day 1–4, Month +1, Month +2)
- [x] Gmail threading via Message-ID / In-Reply-To / References
- [x] Realistic fake timestamps (history = past 28 days, day batches = sequential days)
- [x] Programmatic filler generator for target email counts
- [x] One-click inbox reset
- [x] Dark-themed dashboard UI
- [x] Vercel deployment
- [x] Google OAuth web flow (any Gmail account)

---

## Short-Term (Next 2 Weeks)

### Performance & Reliability

- [ ] **Batch API calls** — Use Gmail API batch requests to inject multiple emails per HTTP call (currently 1 API call per email, ~60s for 300 emails)
- [ ] **Progress indicator** — Show real-time injection progress (e.g., "Injecting 47/300...") via SSE or polling
- [ ] **Vercel timeout handling** — History batch (300 emails) may exceed the 60s serverless timeout; split into smaller chunks or use background jobs
- [ ] **Error recovery** — If injection fails mid-batch, track which emails were sent and allow resuming

### Content Quality

- [ ] **Review all storyline emails** — Proofread for tone consistency, realistic details, and proper threading
- [ ] **Derek Cooper audit** — Ensure Derek's tone is consistently rude across all 30 storylines he appears in
- [ ] **Contractor invoice realism** — Add realistic dollar amounts, invoice numbers, and line items
- [ ] **Date references in email bodies** — Email body text should reference dates that match the fake timestamps (e.g., "as we discussed last Tuesday" should align with the actual fake date)

---

## Medium-Term (1–2 Months)

### Chrome Extension Integration

- [ ] **Coordinate with Chrome extension** — The extension reads the inbox and triggers the AI agent; ensure email format/structure is compatible
- [ ] **Define API contract** — Document exactly what the extension expects (email fields, threading, labels)
- [ ] **Test end-to-end** — Inject → Extension reads → Agent processes → Verify agent responses

### Simulation Realism

- [ ] **Attachments** — Add PDF invoices, photos of damage, lease documents as actual Gmail attachments
- [ ] **CC/BCC** — Some emails should CC other tenants, contractors, or a property management team
- [ ] **Labels/Categories** — Auto-apply Gmail labels (e.g., "Maintenance", "Rent", "Urgent") during injection
- [ ] **Read/unread mix** — History emails should be marked as read; only new batches should be unread
- [ ] **Starred/important** — Mark certain urgent emails as starred to simulate a real inbox state

### Content Expansion

- [ ] **More storylines** — Add seasonal scenarios (snow removal, AC prep, holiday decorations policy)
- [ ] **Tenant personality profiles** — Each tenant has a consistent communication style (formal, casual, anxious, etc.)
- [ ] **Multi-language tenants** — Some tenants write in broken English or include French phrases (realistic for diverse tenant base)
- [ ] **Outbound email history** — Inject "sent" emails from the property manager to show both sides of conversations

---

## Long-Term (3+ Months)

### Dynamic Simulation

- [ ] **Configurable scenarios** — UI to select which storylines to include (e.g., "emergency-heavy" vs "routine day")
- [ ] **Difficulty levels** — Easy (10 emails, clear issues), Medium (50 emails, some ambiguity), Hard (300+ emails, overlapping crises)
- [ ] **Randomized variations** — Same storyline structure but with randomized tenant names, addresses, and details for each demo
- [ ] **Real-time drip** — Instead of batch injection, drip emails in over minutes/hours to simulate a live inbox

### Multi-Channel

- [ ] **SMS simulation** — Inject fake text messages (via a separate tool) for tenants who text instead of email
- [ ] **Voicemail transcripts** — Inject emails that look like voicemail transcription notifications
- [ ] **Portal notifications** — Simulate tenant portal notification emails

### Analytics & Demo Tools

- [ ] **Demo mode** — Pre-configured demo flow with talking points for each batch
- [ ] **Injection log** — Track which batches have been injected, when, and to which account
- [ ] **A/B scenarios** — Multiple scenario sets for different demo audiences (residential, commercial, student housing)

---

## Technical Debt

- [ ] **Move HTML to templates** — Extract inline HTML from `app.py` into Jinja2 template files
- [ ] **Add tests** — Unit tests for `get_emails_for_batch()`, `build_raw_message()`, timestamp logic
- [ ] **Type hints** — Add full type annotations to `storylines.py`
- [ ] **Logging** — Add structured logging for injection/reset operations
- [ ] **Rate limiting** — Prevent accidental double-injection
- [ ] **Database for state** — Replace in-memory `_thread_ids` with Redis or similar for Vercel compatibility

---

## Ideas Parking Lot

- Webhook to notify Slack/Discord when a batch is injected
- "Undo last batch" button
- Email preview mode (see what will be injected before doing it)
- Export storylines as JSON for use in other tools
- Multi-account support (inject into multiple inboxes simultaneously for team demos)
- Integration with Elron AI scoring — after agent processes emails, show a scorecard of how well it handled each storyline
