from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .deps import current_driver
from ..db import get_db
from ..models import (Member, DriverAccount, TrustedDevice, DriverSession, ChecklistVersion, InspectionItem,
                      Inspection, InspectionResult, InspectionRevision, ComplianceEvent, MemberChangeRequest, SystemSetting, LoginAttempt)
from ..security import (make_registration_ticket, read_registration_ticket, hash_pin, verify_pin, random_token,
                        sha256_bytes, session_expiry, utcnow)
from ..utils import normalize_vehicle, today_kst
from ..config import settings
from ..services.auth_limits import is_locked, fail, reset_lock, ip_scan_limited

router=APIRouter(prefix="/api/driver",tags=["driver"])

class LookupIn(BaseModel):
    vehicle_number:str
    name:str
class RegisterIn(BaseModel):
    ticket:str
    pin:str=Field(pattern=r"^\d{4}$")
    pin_confirm:str=Field(pattern=r"^\d{4}$")
    address_change:str|None=None
class LoginIn(BaseModel):
    vehicle_number:str
    pin:str=Field(pattern=r"^\d{4}$")
class InspectionIn(BaseModel):
    target_date:date
    status:str
    issue_item_ids:list[int]=[]
    action_note:str|None=None
class ComplianceIn(BaseModel):
    target_date:date
    event_type:str="inspection_not_performed"
class ChangeRequestIn(BaseModel):
    new_address:str


def member_public(m:Member):
    return {"id":m.id,"name":m.name,"vehicle_number":m.vehicle_number,"vehicle_type":m.vehicle_type,"mobile":m.mobile,"address":m.address,"category":m.category,"region":m.region,"tracking_start_date":m.tracking_start_date.isoformat() if m.tracking_start_date else None}

def current_checklist(db:Session):
    v=db.scalar(select(ChecklistVersion).where(ChecklistVersion.is_current.is_(True)).order_by(ChecklistVersion.id.desc()))
    if not v: raise HTTPException(500,detail="CHECKLIST_NOT_CONFIGURED")
    return v

def late_allowed(db:Session,target:date):
    if target>=today_kst(): return True
    mode=db.get(SystemSetting,"late_entry_mode")
    if not mode or mode.value is None: raise HTTPException(409,detail="POLICY_NOT_SET")
    if mode.value=="admin_only": raise HTTPException(403,detail="LATE_ENTRY_ADMIN_ONLY")
    if mode.value=="days":
        days=db.get(SystemSetting,"late_entry_days")
        if days and days.value is not None and (today_kst()-target).days>int(days.value):
            raise HTTPException(403,detail="LATE_WINDOW_EXCEEDED")
    return True

@router.post("/register/lookup")
def register_lookup(body:LookupIn,request:Request,db:Session=Depends(get_db)):
    ip=request.client.host if request.client else "unknown"
    if is_locked(db,"registration_ip",ip): raise HTTPException(429,detail="TOO_MANY_ATTEMPTS")
    norm=normalize_vehicle(body.vehicle_number)
    m=db.scalar(select(Member).where(Member.active.is_(True),Member.vehicle_number_norm==norm,Member.name==body.name.strip()))
    if not m:
        db.add(LoginAttempt(attempt_type="register_lookup",vehicle_number_norm_input=norm,ip=ip,user_agent=request.headers.get("user-agent"),result="no_match"));fail(db,"registration_ip",ip,20);db.commit()
        raise HTTPException(404,detail="MEMBER_NOT_FOUND")
    db.add(LoginAttempt(attempt_type="register_lookup",member_id=m.id,vehicle_number_norm_input=norm,ip=ip,user_agent=request.headers.get("user-agent"),result="success"));reset_lock(db,"registration_ip",ip);db.commit()
    acct=db.scalar(select(DriverAccount).where(DriverAccount.member_id==m.id))
    if acct and acct.state=="active" and acct.pin_hash: raise HTTPException(409,detail="ALREADY_REGISTERED")
    return {"ticket":make_registration_ticket(m.id),"member":member_public(m)}

@router.post("/register/complete")
def register_complete(body:RegisterIn,request:Request,response:Response,db:Session=Depends(get_db)):
    if body.pin!=body.pin_confirm: raise HTTPException(422,detail="PIN_MISMATCH")
    try: member_id=read_registration_ticket(body.ticket)
    except ValueError: raise HTTPException(400,detail="INVALID_TICKET")
    m=db.get(Member,member_id)
    if not m or not m.active: raise HTTPException(403,detail="MEMBER_INACTIVE")
    acct=db.scalar(select(DriverAccount).where(DriverAccount.member_id==m.id))
    if acct and acct.pin_hash and acct.state=="active": raise HTTPException(409,detail="ALREADY_REGISTERED")
    if not acct:
        acct=DriverAccount(member_id=m.id);db.add(acct);db.flush()
    acct.pin_hash=hash_pin(m.id,body.pin);acct.state="active";acct.pin_set_at=utcnow();acct.registered_at=acct.registered_at or utcnow()
    if not m.tracking_start_date: m.tracking_start_date=today_kst()
    if body.address_change and body.address_change.strip() and body.address_change.strip()!=m.address:
        db.add(MemberChangeRequest(member_id=m.id,request_type="address",old_value=m.address,new_value=body.address_change.strip(),status="pending",requested_via="registration"))
    device_token=random_token(); device=TrustedDevice(member_id=m.id,token_hash=sha256_bytes(device_token),platform="web",user_agent=request.headers.get("user-agent"),last_ip=request.client.host if request.client else None);db.add(device);db.flush()
    session_token=random_token(); sess=DriverSession(member_id=m.id,device_id=device.id,token_hash=sha256_bytes(session_token),expires_at=session_expiry(180),login_ip=request.client.host if request.client else None);db.add(sess);db.commit()
    response.set_cookie("gd_session",session_token,httponly=True,secure=settings.app_env=="production",samesite="lax",max_age=180*86400)
    response.set_cookie("gd_device",device_token,httponly=True,secure=settings.app_env=="production",samesite="lax",max_age=365*86400)
    return {"ok":True,"member":member_public(m)}

@router.post("/auth/login")
def login(body:LoginIn,request:Request,response:Response,db:Session=Depends(get_db)):
    ip=request.client.host if request.client else "unknown"; norm=normalize_vehicle(body.vehicle_number)
    if ip_scan_limited(db,ip) or is_locked(db,"ip",ip): raise HTTPException(429,detail="IP_RATE_LIMITED")
    m=db.scalar(select(Member).where(Member.active.is_(True),Member.vehicle_number_norm==norm))
    if not m:
        db.add(LoginAttempt(attempt_type="login",vehicle_number_norm_input=norm,ip=ip,user_agent=request.headers.get("user-agent"),result="no_match"));db.commit();raise HTTPException(401,detail="INVALID_LOGIN")
    acct=db.scalar(select(DriverAccount).where(DriverAccount.member_id==m.id))
    if not acct or acct.state=="reset_required":
        db.add(LoginAttempt(attempt_type="login",member_id=m.id,vehicle_number_norm_input=norm,ip=ip,user_agent=request.headers.get("user-agent"),result="reset_required"));db.commit();raise HTTPException(409,detail="RESET_REQUIRED")
    device_cookie=request.cookies.get("gd_device");trusted=None
    if device_cookie:
        trusted=db.scalar(select(TrustedDevice).where(TrustedDevice.member_id==m.id,TrustedDevice.token_hash==sha256_bytes(device_cookie),TrustedDevice.revoked_at.is_(None)))
    scope_type="member_device" if trusted else "member_untrusted";scope_key=f"{m.id}:{trusted.id}" if trusted else str(m.id)
    if is_locked(db,scope_type,scope_key): raise HTTPException(429,detail="LOGIN_LOCKED")
    if not verify_pin(m.id,body.pin,acct.pin_hash):
        threshold=5 if trusted else 10;fail(db,scope_type,scope_key,threshold);db.add(LoginAttempt(attempt_type="login",member_id=m.id,vehicle_number_norm_input=norm,device_id=trusted.id if trusted else None,ip=ip,user_agent=request.headers.get("user-agent"),result="bad_pin",lock_scope=scope_type));ip_scan_limited(db,ip);db.commit();raise HTTPException(401,detail="INVALID_LOGIN")
    reset_lock(db,scope_type,scope_key);token=random_token();sess=DriverSession(member_id=m.id,device_id=trusted.id if trusted else None,token_hash=sha256_bytes(token),expires_at=session_expiry(180),login_ip=ip);db.add(sess);acct.last_login_at=utcnow();db.add(LoginAttempt(attempt_type="login",member_id=m.id,vehicle_number_norm_input=norm,device_id=trusted.id if trusted else None,ip=ip,user_agent=request.headers.get("user-agent"),result="success"));db.commit()
    response.set_cookie("gd_session",token,httponly=True,secure=settings.app_env=="production",samesite="lax",max_age=180*86400)
    return {"ok":True}

@router.post("/auth/logout")
def logout(response:Response,request:Request,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    tok=request.cookies.get("gd_session")
    if tok:
        s=db.scalar(select(DriverSession).where(DriverSession.token_hash==sha256_bytes(tok),DriverSession.revoked_at.is_(None)))
        if s: s.revoked_at=utcnow();s.revoke_reason="logout";db.commit()
    response.delete_cookie("gd_session");return {"ok":True}

@router.get("/me")
def me(member:Member=Depends(current_driver)):
    return member_public(member)

@router.get("/home")
def home(db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    t=today_kst();today_rec=db.scalar(select(Inspection).where(Inspection.member_id==member.id,Inspection.inspection_date==t))
    missing=[]
    if member.tracking_start_date:
        d=t-timedelta(days=1);guard=0
        while d>=member.tracking_start_date and guard<400:
            rec=db.scalar(select(Inspection.id).where(Inspection.member_id==member.id,Inspection.inspection_date==d))
            ev=db.scalar(select(ComplianceEvent.id).where(ComplianceEvent.member_id==member.id,ComplianceEvent.target_date==d,ComplianceEvent.event_type=="inspection_not_performed"))
            void=db.scalar(select(ComplianceEvent.id).where(ComplianceEvent.member_id==member.id,ComplianceEvent.target_date==d,ComplianceEvent.event_type=="inspection_not_performed_voided"))
            if not rec and not (ev and not void): missing.append(d.isoformat())
            d-=timedelta(days=1);guard+=1
    return {"member":member_public(member),"today":inspection_json(db,today_rec) if today_rec else None,"missing_count":len(missing),"missing_dates":missing[:10]}

@router.get("/checklist")
def checklist(db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    v=current_checklist(db);items=db.scalars(select(InspectionItem).where(InspectionItem.checklist_version_id==v.id).order_by(InspectionItem.seq)).all()
    return {"version":{"id":v.id,"code":v.code,"form_name":v.form_name},"items":[{"id":i.id,"seq":i.seq,"code":i.code,"group":i.group_name,"label":i.label_display} for i in items]}

def inspection_json(db:Session,r:Inspection|None):
    if not r:return None
    issues=db.scalars(select(InspectionResult).where(InspectionResult.inspection_id==r.id)).all()
    return {"id":r.id,"date":r.inspection_date.isoformat(),"status":r.status,"late":r.is_late_entry,"entry_channel":r.entry_channel,"entered_at":r.first_entered_at.isoformat() if r.first_entered_at else None,"proxy_method":r.proxy_method,"proxy_reason":r.proxy_reason,"issues":[{"item_id":x.item_id,"action_note":x.action_note} for x in issues]}

@router.post("/inspections")
def create_inspection(body:InspectionIn,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    if body.target_date>today_kst():raise HTTPException(422,detail="FUTURE_DATE")
    late_allowed(db,body.target_date)
    if body.status not in {"normal","issue","not_driving"}:raise HTTPException(422,detail="INVALID_STATUS")
    active_not_done=db.scalar(select(ComplianceEvent).where(ComplianceEvent.member_id==member.id,ComplianceEvent.target_date==body.target_date,ComplianceEvent.event_type=="inspection_not_performed"))
    void=db.scalar(select(ComplianceEvent).where(ComplianceEvent.member_id==member.id,ComplianceEvent.target_date==body.target_date,ComplianceEvent.event_type=="inspection_not_performed_voided"))
    if active_not_done and not void and body.status!="not_driving":raise HTTPException(409,detail="NOT_PERFORMED_EVENT_EXISTS")
    version=current_checklist(db)
    r=Inspection(member_id=member.id,inspection_date=body.target_date,checklist_version_id=version.id,status=body.status,entry_channel="driver",is_late_entry=body.target_date<today_kst())
    db.add(r)
    try:db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,detail="ALREADY_RECORDED")
    if body.status=="issue":
        if not body.issue_item_ids:raise HTTPException(422,detail="ISSUE_ITEM_REQUIRED")
        valid=set(db.scalars(select(InspectionItem.id).where(InspectionItem.checklist_version_id==version.id)).all())
        for item_id in body.issue_item_ids:
            if item_id not in valid:raise HTTPException(422,detail="INVALID_ITEM")
            db.add(InspectionResult(inspection_id=r.id,item_id=item_id,action_note=body.action_note))
    rev=InspectionRevision(inspection_id=r.id,revision_no=1,status=body.status,problem_items=[{"item_id":x,"action_note":body.action_note} for x in body.issue_item_ids],actor_type="driver",actor_member_id=member.id,entry_channel="driver")
    db.add(rev);db.commit();return inspection_json(db,r)

@router.get("/inspections/{target_date}")
def get_inspection(target_date:date,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    r=db.scalar(select(Inspection).where(Inspection.member_id==member.id,Inspection.inspection_date==target_date));
    if not r:raise HTTPException(404,detail="NOT_FOUND")
    return inspection_json(db,r)

@router.get("/inspections")
def month_inspections(month:str,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    try:y,m=map(int,month.split("-"));start=date(y,m,1);end=date(y+1,1,1) if m==12 else date(y,m+1,1)
    except:raise HTTPException(422,detail="INVALID_MONTH")
    rows=db.scalars(select(Inspection).where(Inspection.member_id==member.id,Inspection.inspection_date>=start,Inspection.inspection_date<end).order_by(Inspection.inspection_date)).all()
    return {"month":month,"items":[inspection_json(db,r) for r in rows]}

@router.get("/inspections-missing")
def missing(db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    return home(db,member)["missing_dates"]

@router.post("/compliance-events")
def compliance(body:ComplianceIn,request:Request,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    if body.target_date>=today_kst():raise HTTPException(422,detail="PAST_DATE_ONLY")
    if db.scalar(select(Inspection.id).where(Inspection.member_id==member.id,Inspection.inspection_date==body.target_date)):raise HTTPException(409,detail="INSPECTION_EXISTS")
    existing=db.scalar(select(ComplianceEvent).where(ComplianceEvent.member_id==member.id,ComplianceEvent.target_date==body.target_date,ComplianceEvent.event_type==body.event_type))
    if existing:return {"id":existing.id,"existing":True}
    ev=ComplianceEvent(member_id=member.id,target_date=body.target_date,event_type=body.event_type,actor_type="driver",actor_member_id=member.id,source="driver_app",ip=request.client.host if request.client else None)
    db.add(ev);db.commit();return {"id":ev.id,"existing":False}

@router.post("/change-requests")
def change_address(body:ChangeRequestIn,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    req=MemberChangeRequest(member_id=member.id,request_type="address",old_value=member.address,new_value=body.new_address.strip(),status="pending",requested_via="driver_app")
    db.add(req);db.commit();return {"id":req.id,"status":req.status}
