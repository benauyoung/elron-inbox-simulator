import base64
import email.mime.text
import json
import os
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Flask, jsonify, render_template_string

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)

SCOPES = ["https://mail.google.com/"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
TARGET_EMAIL = "relaylegacy@gmail.com"

# ---------------------------------------------------------------------------
# Gmail auth
# ---------------------------------------------------------------------------

def get_gmail_service():
    creds = None

    # Production (Vercel): load from environment variables
    token_env = os.environ.get("GOOGLE_TOKEN")
    creds_env = os.environ.get("GOOGLE_CREDENTIALS")

    if token_env:
        creds = Credentials.from_authorized_user_info(json.loads(token_env), SCOPES)
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif creds_env:
            # On Vercel with no valid token — token env var needs updating
            raise Exception("Token missing or expired. Re-run auth locally and update the GOOGLE_TOKEN env var on Vercel.")
        else:
            # Local dev: open browser flow
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Email generation
# ---------------------------------------------------------------------------

TENANTS = [
    ("James Smith", "james.smith.tenant@gmail.com"),
    ("Maria Garcia", "maria.garcia.apt4b@gmail.com"),
    ("David Chen", "david.chen.renter@gmail.com"),
    ("Sarah Johnson", "sarah.j.tenant@gmail.com"),
    ("Michael Brown", "mbrown.tenant@gmail.com"),
    ("Emily Davis", "emily.davis.lease@gmail.com"),
    ("Robert Wilson", "rwilson.apt@gmail.com"),
    ("Jessica Martinez", "jessica.m.renter@gmail.com"),
    ("William Anderson", "william.a.tenant@gmail.com"),
    ("Linda Taylor", "linda.taylor.apt@gmail.com"),
    ("Christopher Thomas", "c.thomas.renter@gmail.com"),
    ("Patricia Jackson", "p.jackson.tenant@gmail.com"),
    ("Daniel White", "d.white.apt12@gmail.com"),
    ("Barbara Harris", "barbara.h.lease@gmail.com"),
    ("Matthew Martin", "matt.martin.tenant@gmail.com"),
]

CONTRACTORS = [
    ("Bob's Plumbing", "bob.plumbing.co@gmail.com"),
    ("Ace HVAC Services", "ace.hvac.quotes@gmail.com"),
    ("City Electric Co.", "cityelectric.bids@gmail.com"),
    ("ProFix Contractors", "profix.contractors@gmail.com"),
    ("QuickRepair LLC", "quickrepair.quotes@gmail.com"),
]

EMAIL_TEMPLATES = [
    # Leaky faucet
    {
        "subject_templates": [
            "Leaking faucet in unit {unit} - urgent",
            "Water dripping from kitchen tap - Unit {unit}",
            "Bathroom faucet won't stop dripping - {unit}",
            "Faucet leak getting worse, need repair ASAP",
        ],
        "body_templates": [
            (
                "Hi,\n\nI'm reaching out about a leaking faucet in my kitchen (Unit {unit}). "
                "It's been dripping constantly for {days} days now and my water bill is going up. "
                "Could you please send someone to fix it this week?\n\nThanks,\n{name}"
            ),
            (
                "Hello,\n\nThe bathroom faucet in Unit {unit} has started leaking pretty badly. "
                "There's water pooling under the sink cabinet. I've put a bucket down but I really "
                "need maintenance to look at it.\n\nBest,\n{name}"
            ),
        ],
        "sender_pool": "tenants",
    },
    # Late rent
    {
        "subject_templates": [
            "Rent payment for {month} - delay notice",
            "Late rent - Unit {unit}",
            "Regarding this month's rent",
            "Payment coming {days} days late - heads up",
        ],
        "body_templates": [
            (
                "Hi,\n\nI wanted to let you know that my rent for {month} will be {days} days late. "
                "I had an unexpected expense come up but I will have it paid in full by {date}. "
                "I apologize for any inconvenience.\n\nRegards,\n{name}"
            ),
            (
                "Hello,\n\nUnfortunately my paycheck from work was delayed this week. "
                "I won't be able to pay rent for Unit {unit} until {date}. "
                "I can pay a portion now if that helps. Please let me know.\n\n{name}"
            ),
        ],
        "sender_pool": "tenants",
    },
    # Lease renewal
    {
        "subject_templates": [
            "Lease renewal inquiry - Unit {unit}",
            "Renewing my lease - questions",
            "Lease ending {month} - renewal options?",
            "Interested in renewing for another year",
        ],
        "body_templates": [
            (
                "Hi,\n\nMy current lease for Unit {unit} is up at the end of {month}. "
                "I'd love to stay another year. Could you send me the renewal paperwork and let me "
                "know if there will be any rent increase?\n\nThanks,\n{name}"
            ),
            (
                "Hello,\n\nI received the notice that my lease expires {month} {year}. "
                "I'm very happy here and would like to renew. What's the process? "
                "Is the rent going up?\n\nBest regards,\n{name}"
            ),
        ],
        "sender_pool": "tenants",
    },
    # Noise complaint
    {
        "subject_templates": [
            "Noise complaint - unit above me",
            "Ongoing noise issue - please help",
            "Loud neighbors in Unit {unit} again",
            "Noise disturbance - {time} last night",
        ],
        "body_templates": [
            (
                "Hi,\n\nI'm writing to complain about excessive noise coming from the unit above mine "
                "(Unit {unit}). This has been going on for {days} days. Last night it went until {time}. "
                "Could you please speak with them?\n\nThank you,\n{name}"
            ),
            (
                "Hello,\n\nI hate to complain but the noise from Unit {unit} has been really disruptive. "
                "There's loud music and what sounds like furniture being dragged at all hours. "
                "I work early mornings and this is affecting my sleep. Please advise.\n\n{name}"
            ),
        ],
        "sender_pool": "tenants",
    },
    # Contractor quote
    {
        "subject_templates": [
            "Quote for {job} - {address}",
            "Estimate for {job} work at {address}",
            "Re: Service request - {job}",
            "{job} repair estimate enclosed",
        ],
        "body_templates": [
            (
                "Hi,\n\nThank you for reaching out. Please find our estimate for {job} at {address} below.\n\n"
                "Labour: ${labour}\nMaterials: ${materials}\nTotal: ${total}\nEstimated time: {days} days\n\n"
                "We can start as early as next week. Please confirm at your convenience.\n\nBest,\n{name}\n{company}"
            ),
            (
                "Hello,\n\nFollowing our site visit on {date}, here is our formal quote for {job}:\n\n"
                "- Parts & materials: ${materials}\n- Labour ({hours} hrs @ $85/hr): ${labour}\n"
                "- Total: ${total}\n\nValid for 30 days. Let us know how you'd like to proceed.\n\n{name}\n{company}"
            ),
        ],
        "sender_pool": "contractors",
    },
]

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
JOBS = ["roof repair", "HVAC servicing", "plumbing inspection",
        "electrical panel upgrade", "drywall repair", "window replacement",
        "parking lot resurfacing", "boiler maintenance"]
ADDRESSES = ["12 Oak Street", "45 Maple Ave", "78 Pine Rd", "231 Elm Blvd", "9 Cedar Lane"]
TIMES = ["midnight", "1:00 AM", "2:30 AM", "11:45 PM", "12:30 AM"]


def _random_date(month_name: str) -> str:
    day = random.randint(15, 28)
    return f"{month_name} {day}, 2026"


def generate_email(index: int) -> dict:
    template = random.choice(EMAIL_TEMPLATES)
    month = random.choice(MONTHS)
    unit = f"{random.randint(1, 8)}{random.choice(['A', 'B', 'C', 'D'])}"
    days = random.randint(2, 14)
    hours = random.randint(3, 12)
    materials = random.randint(80, 800)
    labour = hours * 85
    total = materials + labour
    job = random.choice(JOBS)
    address = random.choice(ADDRESSES)

    if template["sender_pool"] == "contractors":
        company, sender_email = random.choice(CONTRACTORS)
        name = company.split("'")[0].split(" ")[0] + " (Estimator)"
        subject = random.choice(template["subject_templates"]).format(
            job=job, address=address
        )
        body = random.choice(template["body_templates"]).format(
            job=job, address=address, name=name, company=company,
            materials=materials, labour=labour, total=total,
            days=days, hours=hours, date=_random_date(month)
        )
    else:
        name, sender_email = random.choice(TENANTS)
        subject = random.choice(template["subject_templates"]).format(
            unit=unit, month=month, days=days, time=random.choice(TIMES)
        )
        body = random.choice(template["body_templates"]).format(
            unit=unit, month=month, name=name.split()[0], days=days,
            date=_random_date(month), time=random.choice(TIMES), year=2026
        )

    return {"from_name": name, "from_email": sender_email, "subject": subject, "body": body}


def build_raw_message(from_name: str, from_email: str, subject: str, body: str) -> str:
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = TARGET_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML_DASHBOARD)


@app.route("/inject", methods=["POST"])
def inject_emails():
    try:
        service = get_gmail_service()
        injected = 0
        errors = []

        for i in range(50):
            data = generate_email(i)
            raw = build_raw_message(
                data["from_name"], data["from_email"], data["subject"], data["body"]
            )
            try:
                service.users().messages().insert(
                    userId="me",
                    body={"labelIds": ["INBOX", "UNREAD"], "raw": raw},
                ).execute()
                injected += 1
            except HttpError as e:
                errors.append(str(e))

        return jsonify({
            "success": True,
            "injected": injected,
            "errors": errors,
            "message": f"Successfully injected {injected} emails into inbox.",
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset_inbox():
    try:
        service = get_gmail_service()
        deleted = 0

        # Page through all inbox messages and batch-delete
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

        # batchDelete accepts up to 1000 IDs at a time
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
            "message": f"Deleted {deleted} messages. Inbox is now clean.",
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
      justify-content: center;
      gap: 2rem;
      padding: 2rem;
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

    .card-grid {
      display: flex;
      gap: 1.5rem;
      flex-wrap: wrap;
      justify-content: center;
    }

    .card {
      background: #1a1a24;
      border: 1px solid #2a2a3a;
      border-radius: 16px;
      padding: 2.5rem 2rem;
      width: 260px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
      transition: border-color 0.2s;
    }
    .card:hover { border-color: #4a4a6a; }

    .card-icon { font-size: 2.5rem; }
    .card-title { font-size: 1rem; font-weight: 600; text-align: center; }
    .card-desc { font-size: 0.82rem; color: #8888aa; text-align: center; line-height: 1.5; }

    button {
      margin-top: 0.5rem;
      width: 100%;
      padding: 0.75rem 1.5rem;
      border: none;
      border-radius: 10px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s, transform 0.1s;
    }
    button:active { transform: scale(0.97); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }

    .btn-inject {
      background: linear-gradient(135deg, #7c3aed, #2563eb);
      color: #fff;
    }
    .btn-reset {
      background: linear-gradient(135deg, #dc2626, #b45309);
      color: #fff;
    }

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
  <p class="subtitle">Populate or reset the Gmail inbox for <strong>relaylegacy@gmail.com</strong></p>

  <div class="card-grid">

    <div class="card">
      <div class="card-icon">📬</div>
      <div class="card-title">Inject 50 Morning Emails</div>
      <div class="card-desc">
        Floods the inbox with realistic property management emails — maintenance requests,
        late rent, lease renewals, noise complaints & contractor quotes.
      </div>
      <button class="btn-inject" onclick="runAction('/inject', this)">
        Inject 50 Emails
      </button>
    </div>

    <div class="card">
      <div class="card-icon">🗑️</div>
      <div class="card-title">Reset / Clear Inbox</div>
      <div class="card-desc">
        Permanently deletes every message currently in the inbox, restoring a
        clean slate for the next demo run.
      </div>
      <button class="btn-reset" onclick="runAction('/reset', this)">
        Clear Inbox
      </button>
    </div>

  </div>

  <div id="status"></div>

  <script>
    async function runAction(url, btn) {
      const status = document.getElementById('status');
      const allBtns = document.querySelectorAll('button');

      allBtns.forEach(b => b.disabled = true);
      status.className = 'info';
      status.style.display = 'block';
      status.innerHTML = '<span class="spinner"></span> Working… this may take a few seconds.';

      try {
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          status.className = 'ok';
          status.textContent = '✓ ' + data.message;
        } else {
          status.className = 'error';
          status.textContent = '✗ ' + data.message;
        }
      } catch (err) {
        status.className = 'error';
        status.textContent = '✗ Network error: ' + err.message;
      } finally {
        allBtns.forEach(b => b.disabled = false);
      }
    }
  </script>

</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=False, port=port)
