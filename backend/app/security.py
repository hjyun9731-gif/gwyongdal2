import base64, hashlib, hmac, secrets, struct, time
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .config import settings

ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
serializer = URLSafeTimedSerializer(settings.session_secret, salt="registration-ticket")


def utcnow():
    return datetime.now(timezone.utc)


def sha256_bytes(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def pin_material(member_id: int, pin: str) -> str:
    digest = hmac.new(settings.pin_pepper.encode(), f"{member_id}|{pin}".encode(), hashlib.sha256).hexdigest()
    return digest


def hash_pin(member_id: int, pin: str) -> str:
    return ph.hash(pin_material(member_id, pin))


def verify_pin(member_id: int, pin: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        return ph.verify(encoded, pin_material(member_id, pin))
    except VerifyMismatchError:
        return False


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return ph.verify(encoded, password)
    except VerifyMismatchError:
        return False


def make_registration_ticket(member_id: int) -> str:
    return serializer.dumps({"member_id": member_id, "purpose": "driver-register"})


def read_registration_ticket(ticket: str, max_age: int = 600) -> int:
    try:
        data = serializer.loads(ticket, max_age=max_age)
    except (BadSignature, SignatureExpired) as e:
        raise ValueError("invalid_or_expired_ticket") from e
    if data.get("purpose") != "driver-register":
        raise ValueError("invalid_ticket_purpose")
    return int(data["member_id"])


def totp_code(secret: str, at: int | None = None, step: int = 30, digits: int = 6) -> str:
    if at is None:
        at = int(time.time())
    counter = at // step
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff) % (10 ** digits)
    return str(code_int).zfill(digits)


def verify_totp(secret: str | None, code: str, window: int = 1) -> bool:
    if settings.app_env != "production" and settings.dev_admin_totp_bypass and code == "000000":
        return True
    if not secret or not code.isdigit():
        return False
    now = int(time.time())
    return any(hmac.compare_digest(totp_code(secret, now + i*30), code) for i in range(-window, window+1))



def ensure_aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

def session_expiry(days: int = 180):
    return utcnow() + timedelta(days=days)
