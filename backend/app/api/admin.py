from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .deps import current_admin, require_staff, require_super
from ..db import get_db
from ..models import (AdminUser, AdminSession, AdminActionLog, AuthLockout, Member, DriverAccount, DriverSession,
                      TrustedDevice, Inspection, InspectionResult, InspectionRevision, InspectionItem, ChecklistVersion,
                      ComplianceEvent, MemberChangeRequest, MemberImportBatch, MemberImportRow, SystemSetting, LoginAttempt)
from ..security import verify_password, random_token, sha256_bytes, utcnow
from ..utils import today_kst, normalize_vehicle
from ..config import settings
from ..services.roster import preview_import, apply_import, RosterError
from ..services.auth_limits import is_locked, fail, reset_lock

router=APIRouter(prefix="/api/admin",tags=["admin"])

class AdminLoginIn(BaseModel):
    login_id:str
    password:str
class ProxyIn(BaseModel):
    target_date:date
    status:str
    issue_item_ids:list[int]=[]
    action_note:str|None=None
    proxy_method:str
    proxy_reason:str
class StatusIn(BaseModel):
    active:bool
    reason:str
class ChangeDecisionIn(BaseModel):
    reason:str|None=None
class SettingIn(BaseModel):
    value:object
    policy_pending:bool=False
class ImportDecisionIn(BaseModel):
    decision:str
class VoidEventIn(BaseModel):
    reason:str

def log(db:Session,admin:AdminUser,action:str,target_type:str,target_id:str|None=None,member_id:int|None=None,before=None,after=None,reason=None,request:Request|None=None):
    db.add(AdminActionLog(admin_user_id=admin.id,admin_role=admin.role,action=action,target_type=target_type,target_id=target_id,member_id=member_id,before_value=before,after_value=after,reason=reason,ip=request.client.host if request and request.client else None,user_agent=request.headers.get("user-agent") if request else None))

def member_admin(m:Member,db:Session):
    acct=db.scalar(select(DriverAccount).where(DriverAccount.member_id==m.id))
    return {
        "id":m.id,"management_number":m.management_number,"region":m.region,"vehicle_number":m.vehicle_number,"name":m.name,
        "category":m.category,"address":m.address,"phone":m.phone,"mobile":m.mobile,"master_membership_status":m.master_membership_status,
        "certificate_number":m.certificate_number,"vehicle_type":m.vehicle_type,"active":m.active,
        "app_joined":bool(acct and acct.pin_hash and acct.state=="active"),"pin_state":acct.state if acct else "unregistered",
        "tracking_start_date":m.tracking_start_date.isoformat() if m.tracking_start_date else None,
    }

def current_version(db):
    v=db.scalar(select(ChecklistVersion).where(ChecklistVersion.is_current.is_(True)).order_by(ChecklistVersion.id.desc()))
    if not v:raise HTTPException(500,detail="CHECKLIST_NOT_CONFIGURED")
    return v

@router.post("/auth/login")
def admin_login(body:AdminLoginIn,request:Request,response:Response,db:Session=Depends(get_db)):
    ip=request.client.host if request.client else "unknown"
    if is_locked(db,"admin_ip",ip): raise HTTPException(429,detail="ADMIN_IP_LOCKED")
    u=db.scalar(select(AdminUser).where(func.lower(AdminUser.login_id)==body.login_id.lower(),AdminUser.status=="active"))
    if not u:
        fail(db,"admin_ip",ip,5);db.commit();raise HTTPException(401,detail="INVALID_ADMIN_LOGIN")
    if is_locked(db,"admin_user",str(u.id)): raise HTTPException(429,detail="ADMIN_USER_LOCKED")
    if not verify_password(body.password,u.password_hash):
        fail(db,"admin_user",str(u.id),5);fail(db,"admin_ip",ip,10);db.add(LoginAttempt(attempt_type="admin_login",member_id=None,vehicle_number_norm_input=None,ip=ip,user_agent=request.headers.get("user-agent"),result="bad_pin",lock_scope="admin_user"));db.commit();raise HTTPException(401,detail="INVALID_ADMIN_LOGIN")
    reset_lock(db,"admin_user",str(u.id));reset_lock(db,"admin_ip",ip)
    token=random_token();csrf=random_token();now=utcnow()
    ss=AdminSession(admin_user_id=u.id,token_hash=sha256_bytes(token),csrf_token_hash=sha256_bytes(csrf),idle_expires_at=now+timedelta(minutes=30),absolute_expires_at=now+timedelta(hours=12),ip=ip,user_agent=request.headers.get("user-agent"))
    db.add(ss);u.last_login_at=now;log(db,u,"admin_login","admin_user",str(u.id),reason="비밀번호 인증 성공",request=request);db.commit()
    response.set_cookie("gd_admin",token,httponly=True,secure=settings.app_env=="production",samesite="strict",max_age=12*3600)
    response.set_cookie("gd_admin_csrf",csrf,httponly=False,secure=settings.app_env=="production",samesite="strict",max_age=12*3600)
    return {"ok":True,"admin":{"id":u.id,"name":u.display_name,"role":u.role}}

@router.post("/auth/logout")
def admin_logout(request:Request,response:Response,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    tok=request.cookies.get("gd_admin")
    if tok:
        s=db.scalar(select(AdminSession).where(AdminSession.token_hash==sha256_bytes(tok),AdminSession.revoked_at.is_(None)))
        if s:s.revoked_at=utcnow();s.revoke_reason="logout"
    log(db,admin,"admin_logout","admin_user",str(admin.id),request=request);db.commit();response.delete_cookie("gd_admin");return{"ok":True}

@router.get("/auth/me")
def admin_me(admin:AdminUser=Depends(current_admin)):
    return {"id":admin.id,"name":admin.display_name,"role":admin.role}

@router.get("/checklist")
def admin_checklist(db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    v=current_version(db);items=db.scalars(select(InspectionItem).where(InspectionItem.checklist_version_id==v.id).order_by(InspectionItem.seq)).all()
    return {"version":{"id":v.id,"code":v.code},"items":[{"id":i.id,"seq":i.seq,"group":i.group_name,"label":i.label_display} for i in items]}

@router.get("/dashboard/summary")
def dashboard(date_value:date|None=None,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    d=date_value or today_kst();active=db.scalars(select(Member).where(Member.active.is_(True))).all();joined_ids=set(db.scalars(select(DriverAccount.member_id).where(DriverAccount.pin_hash.is_not(None),DriverAccount.state=="active")).all())
    joined=[m for m in active if m.id in joined_ids];unjoined=len(active)-len(joined);done=missing=off=issue=late=0
    for m in joined:
        r=db.scalar(select(Inspection).where(Inspection.member_id==m.id,Inspection.inspection_date==d))
        if r:
            if r.status=="normal":done+=1
            elif r.status=="not_driving":off+=1
            elif r.status=="issue":issue+=1
            if r.is_late_entry:late+=1
        elif m.tracking_start_date and d>=m.tracking_start_date and d<=today_kst():missing+=1
    return {"date":d.isoformat(),"active":len(active),"app_joined":len(joined),"app_unjoined":unjoined,"completed":done,"missing":missing,"not_driving":off,"issue":issue,"late":late}

@router.get("/members")
def members(q:str="",filter:str="",date_value:date|None=None,limit:int=100,offset:int=0,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    d=date_value or today_kst();stmt=select(Member).where(Member.active.is_(True))
    if q.strip():
        like=f"%{q.strip()}%";stmt=stmt.where(or_(Member.name.ilike(like),Member.vehicle_number.ilike(like),Member.mobile.ilike(like),Member.management_number.ilike(like),Member.certificate_number.ilike(like),Member.vehicle_type.ilike(like)))
    rows=db.scalars(stmt.order_by(Member.name).offset(offset).limit(min(limit,200))).all();out=[]
    joined_ids=set(db.scalars(select(DriverAccount.member_id).where(DriverAccount.pin_hash.is_not(None),DriverAccount.state=="active")).all())
    for m in rows:
        joined=m.id in joined_ids;r=db.scalar(select(Inspection).where(Inspection.member_id==m.id,Inspection.inspection_date==d));status="앱 미가입" if not joined else "점검 미등록"
        if r:
            status={"normal":"완료","not_driving":"미운행","issue":"이상"}[r.status]
            if r.is_late_entry:status+="·지연"
        if filter and filter not in status:continue
        item=member_admin(m,db);item.update({"today_status":status,"today_time":r.first_entered_at.isoformat() if r else None});out.append(item)
    return {"items":out,"offset":offset,"limit":limit}

@router.get("/members/{member_id}")
def member_detail(member_id:int,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    m=db.get(Member,member_id)
    if not m:raise HTTPException(404,detail="MEMBER_NOT_FOUND")
    return member_admin(m,db)

@router.get("/members/{member_id}/inspections")
def member_month(member_id:int,month:str,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    try:y,m=map(int,month.split("-"));start=date(y,m,1);end=date(y+1,1,1) if m==12 else date(y,m+1,1)
    except:raise HTTPException(422,detail="INVALID_MONTH")
    rows=db.scalars(select(Inspection).where(Inspection.member_id==member_id,Inspection.inspection_date>=start,Inspection.inspection_date<end).order_by(Inspection.inspection_date)).all();items=[]
    for r in rows:items.append({"id":r.id,"date":r.inspection_date.isoformat(),"status":r.status,"late":r.is_late_entry,"entry_channel":r.entry_channel,"entered_at":r.first_entered_at.isoformat()})
    return {"month":month,"items":items}

@router.post("/members/{member_id}/proxy-inspections")
def proxy(member_id:int,body:ProxyIn,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    m=db.get(Member,member_id)
    if not m or not m.active:raise HTTPException(404,detail="MEMBER_NOT_FOUND")
    if body.target_date>today_kst():raise HTTPException(422,detail="FUTURE_DATE")
    if body.status not in {"normal","issue","not_driving"}:raise HTTPException(422,detail="INVALID_STATUS")
    v=current_version(db);r=Inspection(member_id=m.id,inspection_date=body.target_date,checklist_version_id=v.id,status=body.status,entry_channel="admin_proxy",entered_by_admin_id=admin.id,is_late_entry=body.target_date<today_kst(),proxy_method=body.proxy_method,proxy_reason=body.proxy_reason)
    db.add(r)
    try:db.flush()
    except IntegrityError:
        db.rollback();log(db,admin,"proxy_entry_skipped","member",str(m.id),member_id=m.id,reason="기존 점검기록 존재",request=request);db.commit();raise HTTPException(409,detail="ALREADY_RECORDED")
    if body.status=="issue":
        if not body.issue_item_ids:raise HTTPException(422,detail="ISSUE_ITEM_REQUIRED")
        for iid in body.issue_item_ids:db.add(InspectionResult(inspection_id=r.id,item_id=iid,action_note=body.action_note))
    db.add(InspectionRevision(inspection_id=r.id,revision_no=1,status=body.status,problem_items=[{"item_id":x,"action_note":body.action_note} for x in body.issue_item_ids],actor_type="admin",actor_admin_id=admin.id,entry_channel="admin_proxy",change_reason=body.proxy_reason))
    log(db,admin,"proxy_entry","inspection",str(r.id),member_id=m.id,after={"date":body.target_date.isoformat(),"status":body.status,"method":body.proxy_method},reason=body.proxy_reason,request=request);db.commit();return{"ok":True,"id":r.id}

@router.post("/members/{member_id}/reset-pin")
def reset_pin(member_id:int,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    acct=db.scalar(select(DriverAccount).where(DriverAccount.member_id==member_id))
    if not acct:raise HTTPException(404,detail="DRIVER_ACCOUNT_NOT_FOUND")
    before={"state":acct.state};acct.pin_hash=None;acct.state="reset_required";acct.reset_at=utcnow();acct.reset_by_admin_id=admin.id
    sessions=db.scalars(select(DriverSession).where(DriverSession.member_id==member_id,DriverSession.revoked_at.is_(None))).all()
    for s in sessions:s.revoked_at=utcnow();s.revoke_reason="pin_reset"
    devices=db.scalars(select(TrustedDevice).where(TrustedDevice.member_id==member_id,TrustedDevice.revoked_at.is_(None))).all()
    for d in devices:d.revoked_at=utcnow();d.revoke_reason="pin_reset"
    log(db,admin,"pin_reset","member",str(member_id),member_id=member_id,before=before,after={"state":"reset_required"},reason="관리자 PIN 초기화",request=request);db.commit();return{"ok":True}

@router.patch("/members/{member_id}/status")
def status(member_id:int,body:StatusIn,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    m=db.get(Member,member_id)
    if not m:raise HTTPException(404,detail="MEMBER_NOT_FOUND")
    before={"active":m.active};m.active=body.active;m.status_changed_at=utcnow();m.inactive_reason=None if body.active else body.reason
    if not body.active:
        for s in db.scalars(select(DriverSession).where(DriverSession.member_id==member_id,DriverSession.revoked_at.is_(None))).all():s.revoked_at=utcnow();s.revoke_reason="member_inactive"
    log(db,admin,"member_status_change","member",str(member_id),member_id=member_id,before=before,after={"active":m.active},reason=body.reason,request=request);db.commit();return{"ok":True}

@router.get("/change-requests")
def change_requests(status:str="pending",db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    rows=db.scalars(select(MemberChangeRequest).where(MemberChangeRequest.status==status).order_by(MemberChangeRequest.requested_at.desc())).all();return{"items":[{"id":r.id,"member":member_admin(db.get(Member,r.member_id),db),"old_value":r.old_value,"new_value":r.new_value,"status":r.status,"requested_at":r.requested_at.isoformat()} for r in rows]}

@router.post("/change-requests/{request_id}/approve")
def approve_change(request_id:int,body:ChangeDecisionIn,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    r=db.get(MemberChangeRequest,request_id)
    if not r or r.status!="pending":raise HTTPException(404,detail="REQUEST_NOT_PENDING")
    m=db.get(Member,r.member_id);before={"address":m.address};m.address=r.new_value;r.status="approved";r.decided_by_admin_id=admin.id;r.decided_at=utcnow();r.decision_reason=body.reason
    log(db,admin,"change_request_approve","member_change_request",str(r.id),member_id=m.id,before=before,after={"address":m.address},reason=body.reason or "주소 변경 승인",request=request);db.commit();return{"ok":True}

@router.post("/change-requests/{request_id}/reject")
def reject_change(request_id:int,body:ChangeDecisionIn,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    r=db.get(MemberChangeRequest,request_id)
    if not r or r.status!="pending":raise HTTPException(404,detail="REQUEST_NOT_PENDING")
    r.status="rejected";r.decided_by_admin_id=admin.id;r.decided_at=utcnow();r.decision_reason=body.reason;log(db,admin,"change_request_reject","member_change_request",str(r.id),member_id=r.member_id,reason=body.reason or "주소 변경 반려",request=request);db.commit();return{"ok":True}

@router.post("/member-imports")
async def upload_import(request:Request,file:UploadFile=File(...),import_type:str=Form("partial_update"),db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    content=await file.read()
    try:b=preview_import(db,content,file.filename or "upload.xlsx",import_type,admin.id)
    except RosterError as e:raise HTTPException(422,detail=str(e))
    return{"id":b.id,"filename":b.original_filename,"import_type":b.import_type,"category_scope":b.category_scope,"status":b.status,"counts":b.counts,"warnings":b.guard_warnings}

@router.get("/member-imports/{batch_id}/rows")
def import_rows(batch_id:int,classification:str|None=None,limit:int=100,offset:int=0,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    limit=max(1,min(limit,200))
    offset=max(0,offset)
    base=(MemberImportRow.batch_id==batch_id)
    filters=[base]
    if classification: filters.append(MemberImportRow.classification==classification)
    total=db.scalar(select(func.count()).select_from(MemberImportRow).where(*filters)) or 0
    stmt=select(MemberImportRow).where(*filters).order_by(MemberImportRow.row_no.nulls_last(),MemberImportRow.id).offset(offset).limit(limit)
    rows=db.scalars(stmt).all()
    return{"items":[{"id":r.id,"row_no":r.row_no,"source":r.source,"name":r.name,"vehicle_number":r.vehicle_number,"management_number":r.management_number,"category":r.category,"classification":r.classification,"review_reason":r.review_reason,"diff":r.diff,"decision":r.decision} for r in rows],"total":total,"limit":limit,"offset":offset}

@router.post("/member-imports/{batch_id}/apply")
def apply_batch(batch_id:int,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    try:return apply_import(db,batch_id,admin.id)
    except RosterError as e:raise HTTPException(409,detail=str(e))

@router.patch("/member-imports/{batch_id}/rows/{row_id}")
def import_row_decision(batch_id:int,row_id:int,body:ImportDecisionIn,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    if body.decision not in {"apply","skip","pending"}: raise HTTPException(422,detail="INVALID_DECISION")
    r=db.get(MemberImportRow,row_id)
    if not r or r.batch_id!=batch_id: raise HTTPException(404,detail="ROW_NOT_FOUND")
    r.decision=body.decision;db.commit();return {"ok":True}

@router.post("/compliance-events/{event_id}/void")
def void_compliance(event_id:int,body:VoidEventIn,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_staff)):
    ev=db.get(ComplianceEvent,event_id)
    if not ev or ev.event_type!="inspection_not_performed": raise HTTPException(404,detail="EVENT_NOT_FOUND")
    existing=db.scalar(select(ComplianceEvent).where(ComplianceEvent.original_event_id==ev.id,ComplianceEvent.event_type=="inspection_not_performed_voided"))
    if existing:return {"ok":True,"id":existing.id,"existing":True}
    v=ComplianceEvent(member_id=ev.member_id,target_date=ev.target_date,event_type="inspection_not_performed_voided",actor_type="admin",actor_admin_id=admin.id,original_event_id=ev.id,source="admin",note=body.reason)
    db.add(v);log(db,admin,"inspection_not_performed_voided","compliance_event",str(ev.id),member_id=ev.member_id,reason=body.reason,request=request);db.commit();return {"ok":True,"id":v.id,"existing":False}

@router.get("/audit-logs")
def audit(limit:int=100,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    rows=db.scalars(select(AdminActionLog).order_by(AdminActionLog.occurred_at.desc()).limit(min(limit,300))).all();return{"items":[{"id":r.id,"occurred_at":r.occurred_at.isoformat(),"admin_user_id":r.admin_user_id,"action":r.action,"target_type":r.target_type,"target_id":r.target_id,"member_id":r.member_id,"before":r.before_value,"after":r.after_value,"reason":r.reason} for r in rows]}

@router.get("/settings")
def settings_get(db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    rows=db.scalars(select(SystemSetting, LoginAttempt).order_by(SystemSetting.key)).all();return{"items":[{"key":r.key,"value":r.value,"policy_pending":r.policy_pending,"description":r.description} for r in rows]}

@router.put("/settings/{key}")
def settings_put(key:str,body:SettingIn,request:Request,db:Session=Depends(get_db),admin:AdminUser=Depends(require_super)):
    s=db.get(SystemSetting,key);before={"value":s.value,"policy_pending":s.policy_pending} if s else None
    if not s:s=SystemSetting(key=key,value=body.value,value_type=type(body.value).__name__,policy_pending=body.policy_pending);db.add(s)
    else:s.value=body.value;s.policy_pending=body.policy_pending;s.updated_by_admin_id=admin.id
    log(db,admin,"setting_change","system_setting",key,before=before,after={"value":body.value,"policy_pending":body.policy_pending},request=request);db.commit();return{"ok":True}
