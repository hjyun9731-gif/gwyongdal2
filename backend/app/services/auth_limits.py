from datetime import timedelta
from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session
from ..models import AuthLockout, LoginAttempt
from ..security import utcnow, ensure_aware

LOCK_STEPS = {
    "member_device": [5,15,60,360],
    "member_untrusted": [15,60],
    "ip": [15,60],
    "registration_ip": [15,60],
    "admin_user": [15,60],
    "admin_ip": [15,60],
}


def get_lock(db:Session,scope_type:str,scope_key:str):
    return db.scalar(select(AuthLockout).where(AuthLockout.scope_type==scope_type,AuthLockout.scope_key==scope_key))


def is_locked(db:Session,scope_type:str,scope_key:str):
    l=get_lock(db,scope_type,scope_key)
    if not l or not l.locked_until:return None
    if ensure_aware(l.locked_until) <= utcnow(): return None
    return l


def reset_lock(db:Session,scope_type:str,scope_key:str):
    l=get_lock(db,scope_type,scope_key)
    if l:
        l.fail_count=0;l.level=0;l.locked_until=None;l.window_started_at=utcnow()


def fail(db:Session,scope_type:str,scope_key:str,threshold:int):
    now=utcnow();l=get_lock(db,scope_type,scope_key)
    if not l:
        l=AuthLockout(scope_type=scope_type,scope_key=scope_key,fail_count=0,level=0,window_started_at=now);db.add(l);db.flush()
    # one-hour rolling round for untrusted/admin/registration scopes
    if l.window_started_at and (now-ensure_aware(l.window_started_at))>timedelta(hours=1):
        l.fail_count=0;l.window_started_at=now
    l.fail_count+=1;l.last_fail_at=now
    if l.fail_count>=threshold:
        steps=LOCK_STEPS.get(scope_type,[15,60]);minutes=steps[min(l.level,len(steps)-1)]
        l.locked_until=now+timedelta(minutes=minutes);l.level=min(l.level+1,len(steps)-1);l.fail_count=0;l.window_started_at=now
    return l


def ip_scan_limited(db:Session,ip:str):
    since=utcnow()-timedelta(minutes=10)
    count=db.scalar(select(func.count(distinct(LoginAttempt.member_id))).where(LoginAttempt.ip==ip,LoginAttempt.occurred_at>=since,LoginAttempt.result=="bad_pin",LoginAttempt.member_id.is_not(None))) or 0
    if count>=10:
        fail(db,"ip",ip,1);return True
    return bool(is_locked(db,"ip",ip))
