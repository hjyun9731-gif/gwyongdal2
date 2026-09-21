from datetime import timedelta
from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import DriverSession, AdminSession, Member, AdminUser
from ..security import sha256_bytes, utcnow, ensure_aware


def current_driver(request: Request, db: Session = Depends(get_db), gd_session: str|None = Cookie(default=None)) -> Member:
    if not gd_session:
        raise HTTPException(401, detail="LOGIN_REQUIRED")
    s=db.scalar(select(DriverSession).where(DriverSession.token_hash==sha256_bytes(gd_session),DriverSession.revoked_at.is_(None)))
    if not s or ensure_aware(s.expires_at) < utcnow():
        raise HTTPException(401, detail="SESSION_EXPIRED")
    m=db.get(Member,s.member_id)
    if not m or not m.active:
        raise HTTPException(403, detail="MEMBER_INACTIVE")
    s.last_used_at=utcnow(); db.commit()
    return m


def current_admin(request: Request, db: Session = Depends(get_db), gd_admin: str|None = Cookie(default=None)) -> AdminUser:
    if not gd_admin:
        raise HTTPException(401, detail="ADMIN_LOGIN_REQUIRED")
    s=db.scalar(select(AdminSession).where(AdminSession.token_hash==sha256_bytes(gd_admin),AdminSession.revoked_at.is_(None)))
    if not s or ensure_aware(s.idle_expires_at) < utcnow() or ensure_aware(s.absolute_expires_at) < utcnow():
        raise HTTPException(401, detail="ADMIN_SESSION_EXPIRED")
    u=db.get(AdminUser,s.admin_user_id)
    if not u or u.status!="active": raise HTTPException(403, detail="ADMIN_DISABLED")
    s.last_used_at=utcnow(); s.idle_expires_at=utcnow()+timedelta(minutes=30); db.commit()
    return u


def require_staff(admin: AdminUser = Depends(current_admin)) -> AdminUser:
    if admin.role not in {"super_admin","staff"}: raise HTTPException(403, detail="STAFF_REQUIRED")
    return admin


def require_super(admin: AdminUser = Depends(current_admin)) -> AdminUser:
    if admin.role!="super_admin": raise HTTPException(403, detail="SUPER_ADMIN_REQUIRED")
    return admin
