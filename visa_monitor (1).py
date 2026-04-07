#!/usr/bin/env python3
"""
US Visa Appointment Slot Monitor
监控美国签证预约名额

使用方法：
  1. pip3 install requests
  2. 填写下方配置区的信息
  3. python3 visa_monitor.py
"""

import requests
import time
import re
import os
import sys
from datetime import datetime

# ═══════════════════════════════════════════════
#  ✏️  请填写以下配置信息后再运行
# ═══════════════════════════════════════════════

# 【必填】ais.usvisa-info.com 登录邮箱和密码
USERNAME        = "your_email@example.com"
PASSWORD        = "your_password"

# 【必填】预约页面 URL 中的 schedule ID（数字部分）
# 例如 URL 为 /schedule/69415081/appointment，则填 "69415081"
SCHEDULE_ID     = "your_schedule_id"

# 【必填】申请人 ID 列表（URL 中 applicants[] 的值）
APPLICANTS      = ["applicant_id_1", "applicant_id_2"]

# 【必填】只报警早于此日期的名额，格式 YYYY-MM-DD
# 例如希望找 2026 年底前的名额，填 "2026-12-31"
EARLIEST_DATE   = "2027-01-01"

# 检查间隔（秒），建议 ≥ 60，避免被封
CHECK_INTERVAL  = 60

# ───────────────────────────────────────────────
#  通知方式（可同时启用多个）
# ───────────────────────────────────────────────
NOTIFY_SOUND    = True   # 发现名额时播放提示音
NOTIFY_EMAIL    = False  # 发邮件通知（需填写下方 SMTP 配置）
NOTIFY_WEBHOOK  = False  # Webhook 通知（Slack / Discord 等）

# 邮件配置（NOTIFY_EMAIL = True 时填写）
# Gmail 用户需使用「应用专用密码」，在 myaccount.google.com/apppasswords 生成
SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = 587
SMTP_USER       = "your_email@gmail.com"
SMTP_PASS       = "your_app_password"
SMTP_TO         = "your_email@gmail.com"

# Webhook URL（NOTIFY_WEBHOOK = True 时填写）
WEBHOOK_URL     = ""

# ═══════════════════════════════════════════════
#  以下内容无需修改
# ═══════════════════════════════════════════════

BASE_URL   = "https://ais.usvisa-info.com"
LOGIN_URL  = f"{BASE_URL}/en-ca/niv/users/sign_in"
APPT_URL   = (
    f"{BASE_URL}/en-ca/niv/schedule/{SCHEDULE_ID}/appointment"
    f"?applicants[]={'&applicants[]='.join(APPLICANTS)}"
    f"&confirmed_limit_message=1&commit=Continue"
)
SLOTS_API  = (
    f"{BASE_URL}/en-ca/niv/schedule/{SCHEDULE_ID}/appointment/days/"
    "{facility_id}.json?appointments[expedite]=false"
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": APPT_URL,
}


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    icon = {"INFO": "ℹ️ ", "OK": "✅", "WARN": "⚠️ ", "ERR": "❌", "FOUND": "🎉"}.get(level, "  ")
    print(f"[{ts}] {icon}  {msg}", flush=True)


def check_config():
    errors = []
    if USERNAME == "your_email@example.com":
        errors.append("USERNAME 未填写")
    if PASSWORD == "your_password":
        errors.append("PASSWORD 未填写")
    if SCHEDULE_ID == "your_schedule_id":
        errors.append("SCHEDULE_ID 未填写")
    if "applicant_id_1" in APPLICANTS:
        errors.append("APPLICANTS 未填写")
    if errors:
        print("\n❌  请先填写配置信息：")
        for e in errors:
            print(f"   • {e}")
        print("\n用文本编辑器打开 visa_monitor.py，修改顶部配置区后重新运行。\n")
        sys.exit(1)


def send_sound():
    try:
        if sys.platform == "darwin":
            for _ in range(5):
                os.system('afplay /System/Library/Sounds/Glass.aiff')
                time.sleep(0.3)
        elif sys.platform.startswith("linux"):
            os.system('paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null')
        elif sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception as e:
        log(f"Sound error: {e}", "WARN")


def send_email(subject: str, body: str):
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = SMTP_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS.replace(" ", ""))
            server.sendmail(SMTP_USER, [SMTP_TO], msg.as_string())
        log(f"Email sent to {SMTP_TO}", "OK")
    except Exception as e:
        log(f"Email error: {e}", "ERR")


def notify(slots: list):
    dates_str = ", ".join(s["date"] for s in slots[:5])
    subject = f"🎉 US Visa Slot Available! ({dates_str})"
    body = (
        "Available appointment slots found:\n\n"
        + "\n".join(f"  • {s['date']}  (facility {s['facility_id']})" for s in slots)
        + f"\n\nBook now:\n{APPT_URL}"
    )
    print("\n" + "=" * 60)
    log(subject, "FOUND")
    log(f"Dates: {dates_str}", "FOUND")
    log(f"Book now: {APPT_URL}", "FOUND")
    print("=" * 60 + "\n")
    if NOTIFY_SOUND:
        send_sound()
    if NOTIFY_EMAIL:
        send_email(subject, body)
    if NOTIFY_WEBHOOK and WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"text": body}, timeout=10)
        except Exception as e:
            log(f"Webhook error: {e}", "ERR")


class VisaMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.facility_ids: list = []

    def login(self) -> bool:
        log("Logging in …")
        try:
            r = self.session.get(LOGIN_URL, timeout=30)
            r.raise_for_status()
        except Exception as e:
            log(f"Failed to reach login page: {e}", "ERR")
            return False

        csrf = None
        patterns = [
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
            r'<meta\s+content="([^"]+)"\s+name="csrf-token"',
            r'name="authenticity_token"\s+value="([^"]+)"',
            r'"authenticity_token":"([^"]+)"',
        ]
        for pat in patterns:
            m = re.search(pat, r.text)
            if m:
                csrf = m.group(1)
                break

        if not csrf:
            log("Could not extract CSRF token from login page", "ERR")
            return False

        log(f"CSRF token found ({len(csrf)} chars)", "OK")

        login_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": LOGIN_URL,
            "Origin": BASE_URL,
        }
        payload = {
            "utf8": "✓",
            "authenticity_token": csrf,
            "user[email]": USERNAME,
            "user[password]": PASSWORD,
            "policy_confirmed": "1",
            "commit": "Sign In",
        }

        try:
            r2 = self.session.post(
                LOGIN_URL,
                data=payload,
                headers=login_headers,
                timeout=30,
                allow_redirects=True,
            )
        except Exception as e:
            log(f"Login POST failed: {e}", "ERR")
            return False

        if "Invalid Email or password" in r2.text or "Invalid email or password" in r2.text:
            log("Login failed — invalid email or password", "ERR")
            return False

        log(f"Login response: {r2.status_code} → {r2.url}", "OK")
        log("Login successful ✓", "OK")
        return True

    def get_facility_ids(self) -> bool:
        log("Fetching facility IDs …")
        try:
            r = self.session.get(APPT_URL, timeout=30)
            ids = re.findall(r'<option\s+value="(\d{2,6})"', r.text)
            ids += re.findall(r'"facility_id"\s*:\s*"?(\d+)"?', r.text)
            ids = list(dict.fromkeys(ids))
            if ids:
                self.facility_ids = ids
                log(f"Facility IDs: {ids}", "OK")
                return True
        except Exception as e:
            log(f"Could not fetch appointment page: {e}", "ERR")

        # 加拿大常用 facility ID（Toronto=89, Vancouver=90, Calgary=91, Montreal=92）
        self.facility_ids = ["89", "90", "91", "92"]
        log(f"Using default facility IDs: {self.facility_ids}", "WARN")
        return True

    def check_slots(self) -> list:
        available = []
        for fid in self.facility_ids:
            url = SLOTS_API.format(facility_id=fid)
            try:
                r = self.session.get(url, headers=JSON_HEADERS, timeout=20)

                if r.status_code == 401:
                    log("Session expired — re-logging in …", "WARN")
                    if self.login():
                        r = self.session.get(url, headers=JSON_HEADERS, timeout=20)
                    else:
                        continue

                if r.status_code == 404:
                    continue
                if r.status_code != 200:
                    log(f"Facility {fid}: HTTP {r.status_code}", "WARN")
                    continue

                days = r.json()
                if not isinstance(days, list):
                    continue

                count = 0
                for day in days:
                    date = day.get("date", "")
                    if not date:
                        continue
                    if EARLIEST_DATE and date >= EARLIEST_DATE:
                        continue
                    available.append({"facility_id": fid, "date": date})
                    count += 1

                if count:
                    log(f"Facility {fid}: {count} slot(s)!", "OK")
                else:
                    log(f"Facility {fid}: no slots available", "INFO")

            except Exception as e:
                log(f"Facility {fid} error: {e}", "ERR")

        return available

    def run(self):
        log("=" * 55)
        log("  US Visa Appointment Monitor — Starting")
        log(f"  Schedule ID : {SCHEDULE_ID}")
        log(f"  Applicants  : {', '.join(APPLICANTS)}")
        log(f"  Interval    : {CHECK_INTERVAL}s")
        log(f"  Earliest    : {EARLIEST_DATE or 'any date'}")
        log("=" * 55)

        for attempt in range(3):
            if self.login():
                break
            if attempt < 2:
                log(f"Retrying in 10s … (attempt {attempt+2}/3)", "WARN")
                time.sleep(10)
        else:
            log("All login attempts failed. Exiting.", "ERR")
            sys.exit(1)

        self.get_facility_ids()

        check_count = 0
        last_slots: set = set()

        while True:
            check_count += 1
            log(f"── Check #{check_count} ─────────────────────────────")
            slots = self.check_slots()
            slot_keys = {f"{s['facility_id']}:{s['date']}" for s in slots}

            if slots:
                new_slots = [s for s in slots if f"{s['facility_id']}:{s['date']}" not in last_slots]
                if new_slots:
                    notify(slots)
                else:
                    log(f"Slots still open: {', '.join(s['date'] for s in slots)}", "OK")
            else:
                log("No slots found yet.", "INFO")

            last_slots = slot_keys
            log(f"Next check in {CHECK_INTERVAL}s … (Ctrl+C to stop)\n")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    check_config()
    monitor = VisaMonitor()
    try:
        monitor.run()
    except KeyboardInterrupt:
        log("Stopped by user.", "WARN")
