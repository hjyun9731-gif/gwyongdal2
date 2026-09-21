import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
KST = ZoneInfo("Asia/Seoul")

def normalize_vehicle(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", value).upper()

def normalize_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")

def today_kst():
    return datetime.now(timezone.utc).astimezone(KST).date()

def now_utc():
    return datetime.now(timezone.utc)
