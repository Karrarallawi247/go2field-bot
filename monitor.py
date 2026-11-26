import json
import os
import urllib.parse
import urllib.request

TOKEN_URL = "https://sso.earthlink.iq/auth/realms/globaltek/protocol/openid-connect/token"
CLIENT_ID = "gtk-client"
BOARD_VIEW_URL = "https://fmsapi.el.earthlink.iq/api/tasks/tasks/board-view"

# غيّر أو أضف معرّفات المجموعات (taskGroups) حسب البوردات المطلوبة
TASK_GROUP_IDS = [
    "760cb42f-796d-753d-154d-6d22a88b3244",  # GT-FTTH Fiber Maintenance (Sabah)
    # أضف هنا UUID الخاص بـ FOC Maintenance إذا كان له taskGroup مستقل
]

STATE_FILE = "seen_tasks.json"


def refresh_access_token(refresh_token: str) -> str:
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
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
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
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


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
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
    tg_chat_id = os.environ["TG_CHAT_ID"]

    access_token = os.environ.get("G2F_ACCESS_TOKEN", "").strip()
    refresh_token = os.environ.get("G2F_REFRESH_TOKEN", "").strip()

    if refresh_token:
        access_token = refresh_access_token(refresh_token)
    elif not access_token:
        raise RuntimeError("يجب توفير G2F_REFRESH_TOKEN أو G2F_ACCESS_TOKEN في Secrets")

    items = fetch_tasks(access_token)
    seen = load_state()
    notifications = []

    for task in items:
        board_name = classify_board(task)
        if not board_name:
            continue

        task_id = str((task.get("self") or {}).get("id") or task.get("taskCode") or "")
        if not task_id:
            continue

        task_code = task.get("taskCode") or "بدون كود"
        task_type = ((task.get("taskType") or {}).get("displayValue")) or "-"
        status = ((task.get("status") or {}).get("displayValue")) or "-"
        sites = ", ".join(
            s.get("displayValue") for s in (task.get("sites") or []) if s.get("displayValue")
        ) or "-"

        signature = f"{status}|{sites}|{task_type}"
        prev_signature = seen.get(task_id)

        if prev_signature is None:
            notifications.append(
                f"🆕 <b>مهمة جديدة — {board_name}</b>\n"
                f"• الكود: <code>{task_code}</code>\n"
                f"• النوع: {task_type}\n"
                f"• الحالة: {status}\n"
                f"• الموقع: {sites}"
            )
            seen[task_id] = signature
        elif prev_signature != signature:
            notifications.append(
                f"🔄 <b>تحديث مهمة — {board_name}</b>\n"
                f"• الكود: <code>{task_code}</code>\n"
                f"• النوع: {task_type}\n"
                f"• الحالة: {status}\n"
                f"• الموقع: {sites}"
            )
            seen[task_id] = signature

    save_state(seen)

    for msg in notifications:
        send_telegram(tg_token, tg_chat_id, msg)


if __name__ == "__main__":
    main()
