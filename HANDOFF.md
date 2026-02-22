# Handoff Guide — Elron Inbox Simulator

Quick-start guide for teammates picking up this project.

---

## TL;DR

This is a **Gmail email injector** that fills an inbox with realistic property management emails for demoing Elron AI. It's a Flask app deployed on Vercel. Users sign in with Google, click buttons to inject batches of emails, and the AI agent processes them.

---

## How to Run Locally

```bash
git clone https://github.com/benauyoung/elron-inbox-simulator.git
cd elron-inbox-simulator
pip install -r requirements.txt
python app.py
# Open http://localhost:5050
```

You need a `credentials.json` file (Google OAuth web client credentials). Ask Ben for the file or create your own in Google Cloud Console (see README.md for details).

---

## Key Files

| File | What it does | When to edit |
|------|-------------|--------------|
| `app.py` | Flask app — OAuth, routes, email building, HTML UI | Changing injection logic, UI, or adding routes |
| `storylines.py` | All 530 emails — 40+ storylines + routine/spam/filler | Adding/editing email content |
| `generate_excel.py` | Generates `Elron_Simulation_Data.xlsx` (5 tabs) | When adding tenants/properties/handymen |
| `Elron_Simulation_Data.xlsx` | Data export for AI onboarding (local only) | Regenerate via `python generate_excel.py` |
| `TENANTS.md` | Reference list of 50 tenants across 20 properties | When adding new tenants |
| `vercel.json` | Vercel deployment config | Rarely |
| `requirements.txt` | Python dependencies | When adding packages |

---

## How Email Injection Works

1. User clicks an **Inject** button (e.g., "Day 1")
2. `app.py` calls `get_emails_for_batch("day1")` from `storylines.py`
3. Returns a flat list of email dicts with `from_name`, `from_email`, `subject`, `body`, `is_reply`, etc.
4. Each email is built into an RFC 2822 message with:
   - **Fake `Date` header** — fixed absolute dates in 2026 (History = Dec 18–Jan 15, Day 1 = Jan 16, etc.)
   - **Threading headers** — `Message-ID`, `In-Reply-To`, `References` for same-sender threads
   - **`threadId` lookup** — For cross-batch replies, searches Gmail for existing threads by subject
5. Injected via `gmail.users.messages.insert()` with `internalDateSource=dateHeader`
6. Labels: History batch → `["INBOX"]` (read); Day 1+ → `["INBOX", "UNREAD"]`

### Important: Per-Tenant Threading

Different tenants reporting the same issue get **separate Gmail threads** with different subjects. This is intentional — the AI must recognize related reports and group them into tickets. Only same-sender follow-ups and contractor replies thread together.

---

## Email Content Structure (storylines.py)

### Storylines

Each storyline is a dict:
```python
{
    "id": "elevator_breakdown",
    "thread_subject": "Elevator out of service - 92 Hawthorn Gardens",
    "emails": [
        {
            "batch": "history",        # which button injects this
            "from_name": "Derek Cooper",
            "from_email": "derek.cooper.apt@gmail.com",
            "subject": "Elevator out of service - 92 Hawthorn Gardens",
            "body": "...",
            "is_reply": False,         # first email in thread
        },
        {
            "batch": "day1",
            "from_name": "Derek Cooper",
            "from_email": "derek.cooper.apt@gmail.com",
            "subject": "Re: Elevator out of service - 92 Hawthorn Gardens",
            "body": "...",
            "is_reply": True,          # threads under the first email
        },
    ]
}
```

### Cluster Scenarios

Several batches include **cluster scenarios** where 2–4 tenants independently email about the same issue:
- **Day 1:** Elevator broken at 92 Hawthorn Gardens (4 tenants)
- **Day 2:** Garage door broken at 103 Birch Court (3 tenants)
- **Day 3:** Hot water outage at 400 Willow Terrace (3 tenants)
- **Day 4:** Hallway lights out at 18 Spruce Way (2 tenants)
- **Month 1:** Heating failure at 78 Pine Road (2 tenants)

These are the key scenarios where the product shows its value — grouping related reports.

### Filler Emails

Beyond the 40+ hand-written storylines, `storylines.py` has:
- **ROUTINE_EMAILS** — rent confirmations, maintenance requests (keyed by batch)
- **SPAM_EMAILS** — office supply promos, software trials (keyed by batch)
- **TIMEWASTER_EMAILS** — stray cats, pigeon complaints, hallway paint colors (keyed by batch)
- **Programmatic filler** — `_generate_filler()` auto-generates rent/maintenance/question emails using a deterministic RNG to hit exact target counts per batch

### Target Counts

| Batch | Target |
|-------|--------|
| history | 300 |
| day1 | 50 |
| day2 | 40 |
| day3 | 35 |
| day4 | 30 |
| month1 | 40 |
| month2 | 35 |
| **Total** | **530** |

---

## Notable Characters

- **Derek Cooper** (Unit 301, 92 Hawthorn Gardens) — The rude tenant. Consistently aggressive, demanding, and threatening in every email. Appears in the elevator breakdown storyline and several others. His tone should never soften.
- **AllPro Maintenance** — The main maintenance contractor. Sends monthly reports and invoices.
- **Contractors** — 20 different contractors (plumbers, electricians, HVAC, pest control, etc.) defined in `storylines.py` under `CONTRACTORS`.

---

## Deployment

Hosted on Vercel. To redeploy:

```bash
vercel --prod --yes
```

Environment variables (set in Vercel dashboard):
- `GOOGLE_CREDENTIALS` — JSON contents of `credentials.json`
- `GOOGLE_REDIRECT_URI` — `https://elron-inbox-simulator.vercel.app/oauth2callback`
- `FLASK_SECRET_KEY` — random string

---

## Common Tasks

### Add a new storyline

1. Add a new dict to the `STORYLINES` list in `storylines.py`
2. Give it a unique `id` and `thread_subject`
3. Add emails with appropriate `batch` values
4. First email in thread: `is_reply: False`; subsequent: `is_reply: True`

### Add more filler emails

- Add to `ROUTINE_EMAILS`, `SPAM_EMAILS`, or `TIMEWASTER_EMAILS` dicts in `storylines.py`
- Or adjust `_BATCH_TARGETS` to change how many auto-generated fillers are created

### Change the timeline

- Edit `BATCH_DATE_RANGES` in `app.py` to change the absolute date range for each batch
- Month 2 is special: `None` means "Feb 1 → today"

### Add a new batch

1. Add to `VALID_BATCHES` and `BATCH_DATE_RANGES` in `app.py`
2. Add to `BATCH_INFO` dict for the UI button
3. Add emails with the new batch key in `storylines.py`
4. Update `_BATCH_TARGETS` if you want filler

---

## Known Limitations

- **Session-based auth** — Tokens are stored in signed cookies. If the cookie expires or the user clears cookies, they need to re-auth.
- **Stateless threading** — Threading across batches uses Gmail search by subject to find existing `threadId`. This works reliably but adds API calls.
- **Gmail API quotas** — Injecting 300 emails (history) takes ~60 seconds due to per-message API calls. No batch insert API exists.
- **Vercel timeout** — `maxDuration: 60` in `vercel.json`. History injection may hit this limit on slow connections.
