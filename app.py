import base64
import hashlib
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

from flask import Flask, jsonify, redirect, render_template_string, request, session

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from storylines import get_emails_for_batch

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

SCOPES = ["https://mail.google.com/"]
CREDENTIALS_FILE = "credentials.json"

VALID_BATCHES = ["history", "day1", "day2", "day3", "day4", "month1", "month2"]

# Fixed date ranges for each batch (all dates in 2026).
# Each value is (start_date, end_date) — emails are spread across this range.
BATCH_DATE_RANGES = {
    "history": (datetime(2025, 12, 18, tzinfo=timezone.utc), datetime(2026, 1, 15, 23, 59, tzinfo=timezone.utc)),
    "day1":    (datetime(2026, 1, 16, tzinfo=timezone.utc), datetime(2026, 1, 16, 23, 59, tzinfo=timezone.utc)),
    "day2":    (datetime(2026, 1, 17, tzinfo=timezone.utc), datetime(2026, 1, 17, 23, 59, tzinfo=timezone.utc)),
    "day3":    (datetime(2026, 1, 18, tzinfo=timezone.utc), datetime(2026, 1, 18, 23, 59, tzinfo=timezone.utc)),
    "day4":    (datetime(2026, 1, 19, tzinfo=timezone.utc), datetime(2026, 1, 19, 23, 59, tzinfo=timezone.utc)),
    "month1":  (datetime(2026, 1, 20, tzinfo=timezone.utc), datetime(2026, 2, 1, 23, 59, tzinfo=timezone.utc)),
    "month2":  None,  # special: Feb 1 → today
}

# Batches that should be injected as already-read
READ_BATCHES = {"history"}

BATCH_INFO = {
    "history": {"label": "History", "desc": "Dec 18 – Jan 15 (read)", "icon": "&#128218;", "color": "#4a5568"},
    "day1":    {"label": "Day 1", "desc": "Jan 16 — new incidents", "icon": "&#9728;&#65039;", "color": "#7c3aed"},
    "day2":    {"label": "Day 2", "desc": "Jan 17 — follow-ups", "icon": "&#128197;", "color": "#2563eb"},
    "day3":    {"label": "Day 3", "desc": "Jan 18 — quotes & invoices", "icon": "&#128196;", "color": "#0891b2"},
    "day4":    {"label": "Day 4", "desc": "Jan 19 — closures", "icon": "&#9989;", "color": "#059669"},
    "month1":  {"label": "Month 1", "desc": "Jan 20 – Feb 1", "icon": "&#128197;", "color": "#d97706"},
    "month2":  {"label": "Month 2", "desc": "Feb 1 – today", "icon": "&#128197;", "color": "#dc2626"},
}

# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def _client_config() -> dict:
    creds_env = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_env:
        return json.loads(creds_env)
    with open(CREDENTIALS_FILE) as f:
        return json.load(f)


def _redirect_uri() -> str:
    configured = os.environ.get("GOOGLE_REDIRECT_URI")
    if configured:
        return configured
    return request.host_url.rstrip("/") + "/oauth2callback"


def get_gmail_service():
    """Return an authenticated Gmail service using the session token."""
    token_data = session.get("google_token")
    if not token_data:
        raise PermissionError("NOT_AUTHENTICATED")

    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                session["google_token"] = json.loads(creds.to_json())
            except RefreshError:
                session.pop("google_token", None)
                session.pop("user_email", None)
                raise PermissionError("NOT_AUTHENTICATED")
        else:
            session.pop("google_token", None)
            session.pop("user_email", None)
            raise PermissionError("NOT_AUTHENTICATED")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/auth")
def auth():
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=_redirect_uri()
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
        state=session.get("oauth_state"),
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session["google_token"] = json.loads(creds.to_json())
    session.pop("oauth_state", None)
    try:
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = svc.users().getProfile(userId="me").execute()
        session["user_email"] = profile.get("emailAddress", "")
    except Exception:
        pass
    return redirect("/")


@app.route("/signout")
def signout():
    session.clear()
    return redirect("/")


# ---------------------------------------------------------------------------
# Email building & threading helpers
# ---------------------------------------------------------------------------

def build_raw_message(from_name: str, from_email: str, subject: str,
                      body: str, to_email: str,
                      fake_date: datetime = None) -> str:
    """Build a base64url-encoded RFC 2822 message."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    if fake_date:
        msg["Date"] = formatdate(timeval=fake_date.timestamp(), localtime=False, usegmt=True)
    else:
        msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


def _find_thread_id(service, thread_subject: str) -> str | None:
    """Search Gmail for an existing thread by subject. Returns threadId or None."""
    try:
        # Strip Re:/Fwd: prefixes to find the root subject
        clean = thread_subject
        for prefix in ["Re: ", "RE: ", "Fwd: ", "FWD: "]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
        query = f'subject:"{clean}"'
        result = service.users().messages().list(
            userId="me", q=query, maxResults=1
        ).execute()
        messages = result.get("messages", [])
        if messages:
            return messages[0].get("threadId")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    user_email = session.get("user_email", "")
    authenticated = bool(session.get("google_token"))
    return render_template_string(HTML_DASHBOARD, authenticated=authenticated,
                                  user_email=user_email, batches=BATCH_INFO)


@app.route("/inject/<batch>", methods=["POST"])
def inject_batch(batch):
    if batch not in VALID_BATCHES:
        return jsonify({"success": False, "message": f"Invalid batch: {batch}"}), 400

    try:
        service = get_gmail_service()
    except PermissionError:
        return jsonify({"success": False, "auth_required": True}), 401

    try:
        user_email = session.get("user_email") or "me"
        emails = get_emails_for_batch(batch)
        injected = 0
        errors = []

        # Compute fake dates for this batch
        now = datetime.now(timezone.utc)
        date_range = BATCH_DATE_RANGES.get(batch)
        if date_range is None:
            # month2: Feb 1 → today
            range_start = datetime(2026, 2, 1, tzinfo=timezone.utc)
            range_end = now
        else:
            range_start, range_end = date_range

        total_seconds = max((range_end - range_start).total_seconds(), 1)
        rng = random.Random(f"elron-ts-{batch}")
        is_read_batch = batch in READ_BATCHES

        # Cache: thread_subject -> Gmail threadId (for this request)
        thread_cache: dict[str, str] = {}

        for i, email_data in enumerate(emails):
            # Spread emails evenly across the date range with jitter
            progress = i / max(len(emails) - 1, 1)
            base_dt = range_start + timedelta(seconds=total_seconds * progress)
            # Add business-hours offset (7:00-18:00) for single-day batches
            if range_start.date() == range_end.date():
                hour_offset = 7.0 + (11.0 * progress)
                base_dt = base_dt.replace(hour=0, minute=0, second=0) + timedelta(hours=hour_offset)
            # Per-email jitter
            fake_dt = base_dt + timedelta(seconds=rng.randint(0, 300), minutes=rng.randint(-5, 5))

            raw = build_raw_message(
                from_name=email_data["from_name"],
                from_email=email_data["from_email"],
                subject=email_data["subject"],
                body=email_data["body"],
                to_email=user_email,
                fake_date=fake_dt,
            )

            # Threading: determine if this email should join an existing thread
            thread_subject = email_data.get("thread_subject")
            is_reply = email_data.get("is_reply", False)
            labels = ["INBOX"] if is_read_batch else ["INBOX", "UNREAD"]
            insert_body = {"labelIds": labels, "raw": raw}

            if thread_subject and is_reply:
                # Look up threadId: first in our local cache, then search Gmail
                tid = thread_cache.get(thread_subject)
                if not tid:
                    tid = _find_thread_id(service, thread_subject)
                    if tid:
                        thread_cache[thread_subject] = tid
                if tid:
                    insert_body["threadId"] = tid

            try:
                result = service.users().messages().insert(
                    userId="me",
                    body=insert_body,
                    internalDateSource="dateHeader",
                ).execute()
                injected += 1

                # Cache the threadId for future replies in this batch
                if thread_subject and not is_reply:
                    thread_cache[thread_subject] = result.get("threadId", "")
                elif thread_subject and "threadId" not in thread_cache:
                    thread_cache[thread_subject] = result.get("threadId", "")

            except HttpError as e:
                errors.append(str(e))

        return jsonify({
            "success": True,
            "injected": injected,
            "errors": errors[:5],
            "message": f"Injected {injected} emails for {BATCH_INFO.get(batch, {}).get('label', batch)}.",
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset_inbox():
    try:
        service = get_gmail_service()
    except PermissionError:
        return jsonify({"success": False, "auth_required": True}), 401

    try:
        deleted = 0
        page_token = None
        message_ids = []

        while True:
            params = {"userId": "me", "labelIds": ["INBOX"], "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            result = service.users().messages().list(**params).execute()
            messages = result.get("messages", [])
            message_ids.extend([m["id"] for m in messages])
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        if not message_ids:
            return jsonify({"success": True, "deleted": 0, "message": "Inbox already empty."})

        chunk_size = 1000
        for i in range(0, len(message_ids), chunk_size):
            chunk = message_ids[i : i + chunk_size]
            service.users().messages().batchDelete(
                userId="me", body={"ids": chunk}
            ).execute()
            deleted += len(chunk)

        return jsonify({
            "success": True,
            "deleted": deleted,
            "message": f"Deleted {deleted} messages. Inbox is now empty.",
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/mark-read", methods=["POST"])
def mark_all_read():
    try:
        service = get_gmail_service()
    except PermissionError:
        return jsonify({"success": False, "auth_required": True}), 401

    try:
        page_token = None
        message_ids = []

        while True:
            params = {"userId": "me", "labelIds": ["UNREAD"], "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            result = service.users().messages().list(**params).execute()
            messages = result.get("messages", [])
            message_ids.extend([m["id"] for m in messages])
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        if not message_ids:
            return jsonify({"success": True, "marked": 0, "message": "All emails already read."})

        # Gmail batchModify supports up to 1000 IDs
        marked = 0
        for i in range(0, len(message_ids), 1000):
            chunk = message_ids[i : i + 1000]
            service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "removeLabelIds": ["UNREAD"]},
            ).execute()
            marked += len(chunk)

        return jsonify({
            "success": True,
            "marked": marked,
            "message": f"Marked {marked} emails as read.",
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ---------------------------------------------------------------------------
# Inline HTML dashboard
# ---------------------------------------------------------------------------

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Elron Inbox Simulator</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f0f13;
      color: #e8e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem;
      gap: 1.5rem;
    }

    .logo {
      font-size: 1.1rem;
      font-weight: 700;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: #8888aa;
    }

    h1 {
      font-size: 2rem;
      font-weight: 700;
      text-align: center;
      background: linear-gradient(135deg, #a78bfa, #60a5fa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    p.subtitle {
      color: #8888aa;
      text-align: center;
      font-size: 0.95rem;
    }

    .auth-bar {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 0.85rem;
    }
    .auth-bar .email { color: #a0a0c0; }
    .auth-bar a {
      color: #60a5fa;
      text-decoration: none;
      padding: 0.3rem 0.75rem;
      border: 1px solid #2a4a6a;
      border-radius: 6px;
      transition: background 0.15s;
    }
    .auth-bar a:hover { background: #1a2a3a; }

    .sequence-label {
      color: #6b7280;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-top: 0.5rem;
    }

    .batch-grid {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      justify-content: center;
      max-width: 900px;
    }

    .batch-card {
      background: #1a1a24;
      border: 1px solid #2a2a3a;
      border-radius: 12px;
      padding: 1.25rem 1rem;
      width: 115px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
      transition: border-color 0.2s;
    }
    .batch-card:hover { border-color: #4a4a6a; }

    .batch-icon { font-size: 1.5rem; }
    .batch-title { font-size: 0.8rem; font-weight: 600; text-align: center; }
    .batch-desc { font-size: 0.65rem; color: #8888aa; text-align: center; line-height: 1.4; }

    .arrow { color: #4a4a6a; font-size: 1.2rem; display: flex; align-items: center; }

    button, .btn-google {
      display: block;
      width: 100%;
      padding: 0.5rem 0.75rem;
      border: none;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
      transition: opacity 0.2s, transform 0.1s;
      color: #fff;
    }
    button:active, .btn-google:active { transform: scale(0.97); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }

    .btn-inject { background: linear-gradient(135deg, #7c3aed, #2563eb); }
    .btn-reset {
      background: linear-gradient(135deg, #dc2626, #b45309);
      margin-top: 0.5rem;
      max-width: 200px;
    }
    .btn-google {
      background: #fff;
      color: #222;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      max-width: 280px;
    }
    .btn-google:hover { opacity: 0.9; }

    .reset-section {
      margin-top: 1rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
    }
    .reset-section .hint {
      font-size: 0.7rem;
      color: #6b7280;
    }

    .login-card {
      background: #1a1a24;
      border: 1px solid #2a2a3a;
      border-radius: 16px;
      padding: 3rem 2.5rem;
      width: 320px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1.25rem;
      text-align: center;
    }
    .login-card .lock { font-size: 3rem; }
    .login-card h2 { font-size: 1.1rem; font-weight: 600; }
    .login-card p { font-size: 0.82rem; color: #8888aa; line-height: 1.6; }

    #status {
      max-width: 480px;
      width: 100%;
      padding: 1rem 1.25rem;
      border-radius: 10px;
      font-size: 0.88rem;
      text-align: center;
      display: none;
    }
    #status.info  { background: #1e2a3a; border: 1px solid #2a4a6a; color: #93c5fd; }
    #status.ok    { background: #1a2e1a; border: 1px solid #2a5a2a; color: #86efac; }
    #status.error { background: #2e1a1a; border: 1px solid #5a2a2a; color: #fca5a5; }

    .spinner {
      display: inline-block;
      width: 14px; height: 14px;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      vertical-align: middle;
      margin-right: 6px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>

  <div class="logo">Elron AI &mdash; Demo Tools</div>
  <h1>Inbox Simulator</h1>

  {% if authenticated %}

  <div class="auth-bar">
    <span class="email">{{ user_email }}</span>
    <a href="/signout">Sign out</a>
  </div>

  <p class="subtitle">Simulate <strong>{{ user_email }}</strong>&rsquo;s property management inbox</p>

  <div class="sequence-label">Inject in order &darr;</div>

  <div class="batch-grid">
    {% for batch_key in ["history", "day1", "day2", "day3", "day4", "month1", "month2"] %}
    {% set b = batches[batch_key] %}
    <div class="batch-card">
      <div class="batch-icon">{{ b.icon | safe }}</div>
      <div class="batch-title">{{ b.label }}</div>
      <div class="batch-desc">{{ b.desc }}</div>
      <button class="btn-inject" style="background: {{ b.color }}" onclick="runAction('/inject/{{ batch_key }}', this)">
        Inject
      </button>
    </div>
    {% if not loop.last %}
    <div class="arrow">&rarr;</div>
    {% endif %}
    {% endfor %}
  </div>

  <div class="reset-section">
    <button class="btn-reset" style="background: linear-gradient(135deg, #2563eb, #0891b2); margin-bottom: 0.4rem;" onclick="runAction('/mark-read', this)">
      &#9993;&#65039; Mark All as Read
    </button>
    <button class="btn-reset" onclick="runAction('/reset', this)">
      &#128465;&#65039; Reset Inbox to Zero
    </button>
    <div class="hint">History is injected as read. Day 1+ arrive as unread.</div>
  </div>

  <div id="status"></div>

  <script>
    async function runAction(url, btn) {
      const status = document.getElementById('status');
      const allBtns = document.querySelectorAll('button');

      allBtns.forEach(b => b.disabled = true);
      status.className = 'info';
      status.style.display = 'block';
      status.innerHTML = '<span class="spinner"></span> Working\\u2026 this may take a moment.';

      try {
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        if (data.auth_required) {
          window.location.href = '/auth';
          return;
        }
        if (data.success) {
          status.className = 'ok';
          status.textContent = data.message;
        } else {
          status.className = 'error';
          status.textContent = data.message;
        }
      } catch (err) {
        status.className = 'error';
        status.textContent = 'Network error: ' + err.message;
      } finally {
        allBtns.forEach(b => b.disabled = false);
      }
    }
  </script>

  {% else %}

  <p class="subtitle">Sign in with any Gmail account to get started</p>

  <div class="login-card">
    <div class="lock">&#128274;</div>
    <h2>Connect your Gmail</h2>
    <p>
      The simulator will inject realistic property management emails directly
      into whichever Gmail inbox you sign in with. No password is stored &mdash;
      only a short-lived session token.
    </p>
    <a href="/auth" class="btn-google">
      <svg width="18" height="18" viewBox="0 0 48 48">
        <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.6 2.4 30.1 0 24 0 14.8 0 6.9 5.4 3 13.3l7.8 6C12.8 13 18 9.5 24 9.5z"/>
        <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4 6.9-10 6.9-17z" />
        <path fill="#FBBC05" d="M10.8 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6A23.9 23.9 0 0 0 0 24c0 3.9.9 7.6 2.5 10.8l8.3-6.1z"/>
        <path fill="#34A853" d="M24 48c6.1 0 11.2-2 14.9-5.5l-7.5-5.8c-2 1.4-4.6 2.2-7.4 2.2-6 0-11.1-4-12.9-9.4l-8.3 6.1C6.9 42.6 14.8 48 24 48z"/>
      </svg>
      Sign in with Google
    </a>
  </div>

  {% endif %}

</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=False, port=port)
