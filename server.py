"""Local app server: serves the UI, keeps shared outreach state, and sends email.

  python server.py            then open http://localhost:8000

Listens on 127.0.0.1 only, because the data includes owners' phone numbers and emails.
Outreach state (status, call outcomes, emails sent, do-not-contact list) lives in data/outreach.json.

Email settings go in .env (see .env.example):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_NAME, FROM_EMAIL, POSTAL_ADDRESS, EMAIL_DAILY_CAP
Every email gets a footer with your postal address and an opt-out line. The server refuses to send without them.
"""
import json, os, pathlib, re, smtplib, ssl, sys, threading, time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
WEB = ROOT / "web"
STATE = ROOT / "data" / "outreach.json"
LOCK = threading.Lock()

def env():
    e = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); e[k.strip()] = v.strip().strip('"\'')
    e.update({k: v for k, v in os.environ.items() if k.startswith(("SMTP_", "FROM_", "POSTAL_", "EMAIL_"))})
    return e

def load():
    if STATE.exists(): s = json.loads(STATE.read_text(encoding="utf-8"))
    else: s = {}
    s.setdefault("lots", {}); s.setdefault("suppress", {"emails": [], "phones": []}); s.setdefault("sent", [])
    return s

def save(s):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, indent=1), encoding="utf-8"); tmp.replace(STATE)

def digits(p): return re.sub(r"\D", "", p or "")[-10:]
def now(): return time.strftime("%Y-%m-%d %H:%M")

def email_config(e):
    need = ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "FROM_EMAIL", "FROM_NAME", "POSTAL_ADDRESS"]
    return [k for k in need if not e.get(k)]

def sent_today(s):
    d = time.strftime("%Y-%m-%d")
    return sum(1 for x in s["sent"] if x["t"].startswith(d) and not x.get("test"))

def footer(e):
    return f'\n\n--\n{e["FROM_NAME"]}\n{e["POSTAL_ADDRESS"]}\nNot interested? Reply "stop" and I will not contact you again.'

def smtp_send(e, to, subject, body):
    m = EmailMessage()
    m["From"] = formataddr((e["FROM_NAME"], e["FROM_EMAIL"])); m["To"] = to; m["Subject"] = subject
    m["Reply-To"] = e.get("REPLY_TO") or e["FROM_EMAIL"]; m["Message-ID"] = make_msgid(domain=e["FROM_EMAIL"].split("@")[-1])
    m.set_content(body + footer(e))
    port = int(e.get("SMTP_PORT") or 587)
    if port == 465:
        with smtplib.SMTP_SSL(e["SMTP_HOST"], port, context=ssl.create_default_context(), timeout=30) as c:
            c.login(e["SMTP_USER"], e["SMTP_PASS"]); c.send_message(m)
    else:
        with smtplib.SMTP(e["SMTP_HOST"], port, timeout=30) as c:
            c.starttls(context=ssl.create_default_context()); c.login(e["SMTP_USER"], e["SMTP_PASS"]); c.send_message(m)

def api_state():
    e = env(); s = load(); missing = email_config(e)
    return {"server": True, "lots": s["lots"], "suppress": s["suppress"],
            "email": {"ready": not missing, "missing": missing, "from": e.get("FROM_EMAIL", ""), "name": e.get("FROM_NAME", ""),
                      "cap": int(e.get("EMAIL_DAILY_CAP") or 40), "sent_today": sent_today(s),
                      "sent_to": sorted({x["to"].lower() for x in s["sent"] if not x.get("test")})}}

def api_lot(b):
    """{ids:[...], patch:{status, lien}, log:{type, detail}}"""
    with LOCK:
        s = load()
        for i in b.get("ids") or [b["id"]]:
            lot = s["lots"].setdefault(i, {})
            lot.update({k: v for k, v in (b.get("patch") or {}).items() if k in ("status", "lien")})
            if b.get("log"): lot.setdefault("log", []).append({"t": now(), **b["log"]})
        save(s)
    return {"ok": True}

def api_suppress(b):
    with LOCK:
        s = load()
        if b.get("email") and b["email"].lower() not in s["suppress"]["emails"]: s["suppress"]["emails"].append(b["email"].lower())
        if b.get("phone") and digits(b["phone"]) not in s["suppress"]["phones"]: s["suppress"]["phones"].append(digits(b["phone"]))
        save(s)
    return {"ok": True, "suppress": s["suppress"]}

def api_email(b):
    """{ids:[lot ids], to, subject, body, test:bool, force:bool}"""
    e = env(); missing = email_config(e)
    if missing: return {"ok": False, "error": "Email is not set up. Missing in .env: " + ", ".join(missing)}
    to = (b.get("to") or "").strip()
    if b.get("test"): to = e["FROM_EMAIL"]
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to): return {"ok": False, "error": f"Not a valid email address: {to}"}
    if not b.get("subject") or not b.get("body"): return {"ok": False, "error": "Empty subject or body"}
    with LOCK:
        s = load()
        if not b.get("test"):
            if to.lower() in s["suppress"]["emails"]: return {"ok": False, "error": "On the do-not-contact list"}
            if not b.get("force") and any(x["to"].lower() == to.lower() for x in s["sent"] if not x.get("test")):
                return {"ok": False, "error": "Already emailed"}
            cap = int(e.get("EMAIL_DAILY_CAP") or 40)
            if sent_today(s) >= cap: return {"ok": False, "error": f"Daily cap of {cap} reached. Raise EMAIL_DAILY_CAP in .env or continue tomorrow."}
        try: smtp_send(e, to, b["subject"], b["body"])
        except Exception as ex: return {"ok": False, "error": f"Send failed: {type(ex).__name__}: {str(ex)[:200]}"}
        s["sent"].append({"t": now(), "to": to, "subject": b["subject"], "ids": b.get("ids", []), "test": bool(b.get("test"))})
        if not b.get("test"):
            for i in b.get("ids", []):
                lot = s["lots"].setdefault(i, {})
                if lot.get("status", "") in ("", "queued"): lot["status"] = "emailed"
                lot.setdefault("log", []).append({"t": now(), "type": "email", "detail": f"Offer emailed to {to}"})
        save(s)
    return {"ok": True, "to": to, "sent_today": sent_today(s)}

ROUTES = {"/api/lot": api_lot, "/api/suppress": api_suppress, "/api/email": api_email}

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(WEB), **k)
    def log_message(self, fmt, *args):
        if args and "/api/" in str(args[0]): sys.stderr.write("  " + fmt % args + "\n")
    def end_headers(self):
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def _json(self, obj, code=200):
        d = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        if self.path.split("?")[0] == "/api/state": return self._json(api_state())
        super().do_GET()
    def do_POST(self):
        fn = ROUTES.get(self.path)
        if not fn: return self._json({"ok": False, "error": "Unknown route"}, 404)
        if self.headers.get("Origin") and "localhost" not in self.headers["Origin"] and "127.0.0.1" not in self.headers["Origin"]:
            return self._json({"ok": False, "error": "Cross-site request refused"}, 403)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self._json(fn(body))
        except Exception as ex:
            self._json({"ok": False, "error": f"{type(ex).__name__}: {ex}"}, 500)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    miss = email_config(env())
    print(f"Jake Effective Land running at http://localhost:{port}   (Ctrl+C to stop)")
    print("Email: " + ("ready, sending as " + env()["FROM_EMAIL"] if not miss else "not set up yet. Missing in .env: " + ", ".join(miss)))
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
