# Elron Inbox Simulator

A tool that injects realistic, pre-scripted property management emails into any Gmail inbox. Built for demoing [Elron AI](https://elron.ai) — an AI assistant for property managers.

**Live:** [elron-inbox-simulator.vercel.app](https://elron-inbox-simulator.vercel.app)

---

## What It Does

The simulator populates a Gmail inbox with **530 interconnected emails** that tell a coherent story of managing 20 rental properties with 50 tenants. Emails are injected in **7 sequential batches** that simulate a realistic timeline:

| Batch | Emails | Timeline | Description |
|-------|--------|----------|-------------|
| **History** | 300 | Past 28 days | Baseline inbox — old threads, rent confirmations, resolved issues |
| **Day 1** | 50 | Today | Monday morning flood — new incidents, tenant complaints |
| **Day 2** | 40 | Tomorrow | Follow-ups, contractor responses |
| **Day 3** | 35 | +2 days | Quotes, invoices arriving |
| **Day 4** | 30 | +3 days | Closures, more invoices |
| **Month +1** | 40 | +30 days | Lease renewals, monthly invoices |
| **Month +2** | 35 | +60 days | Wrap-ups, seasonal items |

### Key Features

- **Pre-authored storylines** — 30 interconnected storylines (elevator breakdown, burst pipe, late rent, lease renewals, pest control, noise complaints, etc.)
- **Gmail threading** — Emails thread correctly using `Message-ID`, `In-Reply-To`, and `References` headers
- **Realistic timestamps** — Each batch gets fake dates matching its timeline position
- **Character consistency** — Recurring characters like Derek Cooper (rude tenant at 92 Hawthorn Gardens) maintain their personality across all interactions
- **Mixed email types** — Storyline emails, routine correspondence, spam, and time-wasters
- **One-click reset** — Delete all emails and start fresh

---

## Architecture

```
app.py            Flask app — OAuth, routes, email injection, inline HTML dashboard
storylines.py     All 530 pre-authored emails, organized by storyline and batch
vercel.json       Vercel deployment config
credentials.json  Google OAuth client credentials (not in repo)
```

### Tech Stack

- **Backend:** Python / Flask
- **Auth:** Google OAuth 2.0 (web flow, session-based tokens)
- **API:** Gmail API (`messages.insert` for injection, `messages.batchDelete` for reset)
- **Hosting:** Vercel (Python serverless functions)
- **UI:** Inline HTML/CSS/JS (no build step)

### How Threading Works

Each storyline has a `thread_subject`. The first email in a thread gets a deterministic `Message-ID` (MD5 hash of storyline ID + subject + index). Reply emails reference the parent via `In-Reply-To` and `References` headers. Gmail groups these into conversation threads automatically.

### How Timestamps Work

Emails get fake `Date` headers based on their batch:
- **History:** Spread linearly across the past 28 days
- **Day 1–4:** Fixed day offset from "now", spread across 7:00–18:00 with jitter
- **Month +1/+2:** 30/60 days from "now"

---

## Setup (Local Development)

### Prerequisites

- Python 3.11+
- A Google Cloud project with Gmail API enabled
- OAuth 2.0 credentials (Web application type)

### 1. Clone and install

```bash
git clone https://github.com/benauyoung/elron-inbox-simulator.git
cd elron-inbox-simulator
pip install -r requirements.txt
```

### 2. Configure Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Gmail API**
4. Create **OAuth 2.0 credentials** (Web application)
5. Add `http://localhost:5050/oauth2callback` as an authorized redirect URI
6. Download the credentials JSON and save as `credentials.json` in the project root

The file should look like:
```json
{
  "web": {
    "client_id": "...",
    "client_secret": "...",
    "redirect_uris": ["http://localhost:5050/oauth2callback"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token"
  }
}
```

### 3. Add test users

If your OAuth consent screen is in "Testing" mode, add the Gmail accounts you want to test with under **APIs & Services → OAuth consent screen → Test users**.

### 4. Run

```bash
python app.py
```

Open [http://localhost:5050](http://localhost:5050), sign in with Google, and start injecting.

---

## Deployment (Vercel)

The app is configured for Vercel via `vercel.json`. Environment variables needed:

| Variable | Description |
|----------|-------------|
| `GOOGLE_CREDENTIALS` | Full JSON contents of `credentials.json` |
| `GOOGLE_REDIRECT_URI` | e.g. `https://elron-inbox-simulator.vercel.app/oauth2callback` |
| `FLASK_SECRET_KEY` | Any random string for session signing |

```bash
vercel --prod
```

---

## Project Structure

```
elron-inbox-simulator/
├── app.py                 # Flask app (routes, OAuth, injection logic, UI)
├── storylines.py          # All email content (30 storylines + filler)
├── requirements.txt       # Python dependencies
├── vercel.json            # Vercel deployment config
├── credentials.json       # Google OAuth creds (gitignored)
├── TENANTS.md             # Tenant roster reference (50 tenants, 20 properties)
├── HANDOFF.md             # Teammate onboarding guide
├── ROADMAP.md             # Future plans and next steps
└── .gitignore
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/auth` | Start Google OAuth flow |
| `GET` | `/oauth2callback` | OAuth callback |
| `GET` | `/signout` | Clear session |
| `POST` | `/inject/<batch>` | Inject emails for a batch (`history`, `day1`–`day4`, `month1`, `month2`) |
| `POST` | `/reset` | Delete all inbox emails |

All `POST` endpoints return JSON:
```json
{
  "success": true,
  "injected": 300,
  "message": "Injected 300 emails for Inject History."
}
```

---

## License

Internal tool — Elron AI.
