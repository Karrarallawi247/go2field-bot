from datetime import datetime, timedelta, timezone


def main() -> None:
    baghdad_tz = timezone(timedelta(hours=3))
    now_iq = datetime.now(baghdad_tz).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ALIVE] Monitor check executed in Baghdad time: {now_iq}", flush=True)


if __name__ == "__main__":
    main()
