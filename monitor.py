import time
from datetime import datetime, timezone, timedelta

baghdad_tz = timezone(timedelta(hours=3))

while True:
    now_iq = datetime.now(baghdad_tz).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ALIVE] Server running in Baghdad time: {now_iq}", flush=True)
    time.sleep(30)
