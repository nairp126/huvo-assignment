# -*- coding: utf-8 -*-
import json
import urllib.request
import time
import pathlib
import sys

BASE = "http://127.0.0.1:8002"

def post(path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else b""
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} on {path}: {body_txt}", file=sys.stderr)
        raise

def chat(sid, msg):
    r = post("/chat", {"session_id": sid, "message": msg})
    return r["response"]

def new_session():
    return post("/session/start")["session_id"]

results_file = pathlib.Path("test_results.json")
if results_file.exists():
    try:
        results = json.loads(results_file.read_text(encoding="utf-8"))
    except Exception:
        results = {}
else:
    results = {}

def run_scenario(num, title, messages):
    print(f"\n{'='*60}")
    print(f"SCENARIO {num}: {title}")
    print("="*60)
    sid = new_session()
    turns = []
    for m in messages:
        print(f"\nU: {m}")
        r = chat(sid, m)
        print(f"A: {r}")
        turns.append({"user": m, "agent": r})
        time.sleep(3.0)  # Rate limit safety delay
    results[str(num)] = {"title": title, "session_id": sid, "turns": turns}
    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(2.0)
    return sid

# 1. Happy path Hinglish
run_scenario(1, "Happy path Hinglish", [
    "2BHK dekh rahe hain, Gurugram mein. Budget around 1.4 crore hai.",
    "Haan, investment ke liye le rahe hain. Timeline 6 months hai.",
    "Haan, site visit karna chahte hain. Saturday 23 August ko 11 AM ko aana chahte hain.",
    "Naam hai Amit Sharma, phone number 9876543210.",
])

# 2. Price objection
run_scenario(2, "Price objection", [
    "I am interested in a 2BHK at Northstar One.",
    "1.35 crore is too much for a 2BHK. That seems overpriced.",
])

# 3. Call me later
run_scenario(3, "Call me later", [
    "Hi, mujhe Northstar One ke baare mein jaanna hai.",
    "Main abhi busy hoon, please Monday evening 6 baje call karein.",
])

# 4. DND opt-out + post-optout guard
run_scenario(4, "DND opt-out", [
    "Please stop contacting me. I do not want any further calls or messages.",
    "Actually wait, what is the price of 2BHK?",
])

# 5. Unknown question
run_scenario(5, "Unknown question", [
    "Kya clubhouse hai is project mein? Aur swimming pool?",
    "Possession date kab hai?",
])

# 6. Booking failure then recovery
run_scenario(6, "Booking failure then recovery", [
    "I want to book a site visit for Saturday 23 August at 11 AM.",
    "Mera naam Priya Mehta hai, phone 9123456789. Koi alternative slot batao.",
])

# 7. Human escalation
run_scenario(7, "Human escalation", [
    "I want to speak to an actual human, not an AI bot.",
])

# 8. Busy / uninterested
run_scenario(8, "Busy uninterested", [
    "Not interested, sorry.",
    "No really please do not bother me.",
])

# 9. Mid-conversation language switch
run_scenario(9, "Language switch mid-conversation", [
    "Hello, I am looking for a flat in Gurugram.",
    "Haan, mujhe 3BHK chahiye. Budget kaafi zyada hai.",
    "Mera budget 2 crore ke aas paas hai.",
])

print("\n\nAll 9 scenarios finished successfully! Results saved to test_results.json")