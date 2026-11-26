import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TOKEN_URL = "https://sso.earthlink.iq/auth/realms/globaltek/protocol/openid-connect/token"
CLIENT_ID = "gtk-client"
BOARD_VIEW_URL = "https://fmsapi.el.earthlink.iq/api/tasks/tasks/board-view"

# أضف هنا أي taskGroup إضافي لـ FOC Maintenance إذا كان له معرّف مستقل
TASK_GROUP_IDS = [
    "760cb42f-796d-753d-154d-6d22a88b3244",  # GT-FTTH Fiber Maintenance (Sabah)
]

STATE_FILE = "seen_tasks.json"
BAGHDAD_TZ = timezone(timedelta(hours=3))


def get_access_token_by_password(username: str, password: str) -> str:
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": username,
        "password": password,
        "scope": "openid profile email",
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://globaltek.go2field.iq",
            "Referer": "https://globaltek.go2field.iq/",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"فشل تسجيل الدخول المباشر ({e.code}): {err_body}") from e

    token = payload.get("access_token")
    if not token:
        raise RuntimeError("لم يتم استلام access_token من سيرفر المصادقة")
    return token


def fetch_tasks(access_token: str) -> list[dict]:
    params = [("pageSize", "250"), ("pageNumber", "1")]
    for gid in TASK_GROUP_IDS:
        params.append(("taskGroups", gid))

    url = f"{BOARD_VIEW_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Origin": "https://globaltek.go2field.iq",
            "Referer": "https://globaltek.go2field.iq/",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", [])


def classify_board(task: dict) -> str | None:
    groups_text = " ".join(
        (g.get("displayValue") or "") for g in (task.get("groups") or [])
    ).lower()
    category_text = ((task.get("taskCategory") or {}).get("displayValue") or "").lower()
    combined = f"{groups_text} {category_text}"

    if "foc" in combined:
        return "FOC Maintenance"
    if "sabah" in combined:
        return "Sabah"
    return None


def format_start_date(raw_date: str | None) -> str:
    if not raw_date:
        return "-"
    try:
        cleaned = raw_date.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_baghdad = dt.astimezone(BAGHDAD_TZ)
        return dt_baghdad.strftime("%d-%m-%Y %I:%M %p")
    except ValueError:
        return raw_date


def extract_leader(task: dict) -> str:
    for key in ("leader", "assignee", "assignedTo", "teamLeader"):
        val = task.get(key)
        if isinstance(val, dict) and val.get("displayValue"):
            return val["displayValue"]
        if isinstance(val, str) and val.strip():
            return val.strip()

    assignees = task.get("assignees") or task.get("leaders") or []
    if isinstance(assignees, list) and assignees:
        names = [
            a.get("displayValue") if isinstance(a, dict) else str(a)
            for a in assignees
        ]
        names = [n for n in names if n]
        if names:
            return ", ".join(names)

    return "No leader assigned"


def build_message(task: dict) -> str:
    groups_list = [
        g.get("displayValue") for g in (task.get("groups") or []) if g.get("displayValue")
    ]
    board_title = ", ".join(groups_list) if groups_list else "-"
    task_code = task.get("taskCode") or "-"
    description = (task.get("description") or "").strip() or "-"
    title_ref = (
        task.get("title")
        or task.get("subject")
        or task.get("reference")
        or task.get("externalReference")
        or "-"
    )
    task_type = ((task.get("taskType") or {}).get("displayValue")) or "-"
    category = ((task.get("taskCategory") or {}).get("displayValue")) or "-"
    sites = ", ".join(
        s.get("displayValue") for s in (task.get("sites") or []) if s.get("displayValue")
    ) or "-"
    leader = extract_leader(task)
    start_date = format_start_date(
        task.get("startDate") or task.get("createdDate") or task.get("creationDate")
    )

    return (
        f"🚨 <b>تاسك جديد في عمود New</b>\n"
        f"📋 <b>اللوحة:</b> {html.escape(board_title)}\n"
        f"📌 <b>الكود:</b> <code>{html.escape(str(task_code))}</code>\n"
        f"📝 <b>الوصف (Description):</b>\n{html.escape(str(description))}\n"
        f"🏷️ <b>المرجع/العنوان:</b> {html.escape(str(title_ref))}\n"
        f"🔧 <b>النوع:</b> {html.escape(str(task_type))}\n"
        f"🗂️ <b>التصنيف:</b> {html.escape(str(category))}\n"
        f"📍 <b>الموقع:</b> {html.escape(str(sites))}\n"
        f"👤 <b>المسؤول (Leader):</b> {html.escape(str(leader))}\n"
        f"🕒 <b>تاريخ البدء:</b> {html.escape(str(start_date))}"
    )


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    if not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main() -> None:
    tg_token = os.environ["TG_BOT_TOKEN"]
    chat_sabah = os.environ.get("TG_CHAT_ID_SABAH", "").strip()
    chat_foc = os.environ.get("TG_CHAT_ID_FOC", "").strip()

    username = os.environ["G2F_USERNAME"].strip()
    password = os.environ["G2F_PASSWORD"]

    access_token = get_access_token_by_password(username, password)

    items = fetch_tasks(access_token)
    seen = load_state()
    notifications: list[tuple[str, str]] = []

    for task in items:
        board_name = classify_board(task)
        if not board_name:
            continue

        status = (((task.get("status") or {}).get("displayValue")) or "").strip()
        if status.lower() != "new":
            continue

        task_id = str((task.get("self") or {}).get("id") or task.get("taskCode") or "")
        if not task_id or task_id in seen:
            continue

        msg = build_message(task)
        notifications.append((board_name, msg))
        seen[task_id] = status

    save_state(seen)

    for board_name, msg in notifications:
        target_chat = chat_sabah if board_name == "Sabah" else chat_foc
        send_telegram(tg_token, target_chat, msg)


if __name__ == "__main__":
    main()
