from __future__ import annotations
import hashlib, io
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Member, MemberImportBatch, MemberImportRow, AdminActionLog
from ..utils import normalize_vehicle, normalize_phone

EXPECTED_HEADERS = [
    "management_number","region","vehicle_number","name","category","address","phone","mobile",
    "membership_status","certificate_number","vehicle_type"
]
SAFE_COPY_HEADERS = set(EXPECTED_HEADERS)

class RosterError(ValueError):
    pass

def _value(v):
    if v is None: return None
    if isinstance(v, datetime): return v.isoformat()
    return str(v).strip() if str(v).strip() else None

def parse_xlsx(content: bytes) -> tuple[list[dict[str,Any]], list[str]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    try: header_row = next(rows)
    except StopIteration: raise RosterError("empty_file")
    headers = [str(x).strip() if x is not None else "" for x in header_row]
    missing = [h for h in ["vehicle_number","name","category"] if h not in headers]
    if missing: raise RosterError("missing_headers:"+",".join(missing))
    idx = {h:i for i,h in enumerate(headers)}
    out=[]
    for row_no,row in enumerate(rows,start=2):
        obj={h:_value(row[idx[h]]) if h in idx and idx[h] < len(row) else None for h in SAFE_COPY_HEADERS}
        if not any(obj.get(h) for h in SAFE_COPY_HEADERS): continue
        obj["row_no"]=row_no
        obj["vehicle_number_norm"]=normalize_vehicle(obj.get("vehicle_number"))
        obj["mobile_norm"]=normalize_phone(obj.get("mobile"))
        out.append(obj)
    return out, headers

def preview_import(db: Session, content: bytes, filename: str, import_type: str, admin_id: int) -> MemberImportBatch:
    if import_type not in {"full_snapshot","partial_update"}: raise RosterError("invalid_import_type")
    parsed, headers = parse_xlsx(content)
    categories = {r.get("category") for r in parsed if r.get("category")}
    category_scope = next(iter(categories)) if len(categories)==1 else None
    warnings=[]
    if import_type=="full_snapshot" and not category_scope:
        warnings.append("full_snapshot인데 category가 하나로 확정되지 않아 파일 누락자 inactive 후보를 만들지 않습니다.")
    digest=hashlib.sha256(content).hexdigest()
    batch=MemberImportBatch(uploaded_by_admin_id=admin_id,original_filename=filename,file_sha256=digest,file_size=len(content),parser_version="1",import_type=import_type,category_scope=category_scope,column_mapping={h:h for h in headers if h in SAFE_COPY_HEADERS},status="review",total_rows=len(parsed),guard_warnings=warnings)
    db.add(batch); db.flush()

    existing = db.scalars(select(Member)).all()
    by_vehicle={}
    for m in existing:
        if m.vehicle_number_norm:
            by_vehicle.setdefault(m.vehicle_number_norm,[]).append(m)
    file_vehicle_counts=Counter(r.get("vehicle_number_norm") for r in parsed if r.get("vehicle_number_norm"))
    by_mgmt_cat={}
    for m in existing:
        if m.management_number and m.category:
            by_mgmt_cat.setdefault((m.management_number,m.category),[]).append(m)

    seen_member_ids=set(); counts=Counter()
    file_vehicle_set=set()
    for r in parsed:
        vehicle_norm=r["vehicle_number_norm"]
        if vehicle_norm: file_vehicle_set.add(vehicle_norm)
        match = None
        review_reason=None
        classification="new"; diff={}; decision="apply"
        if not r.get("vehicle_number") or not r.get("name"):
            classification="invalid"; decision="skip"; review_reason="필수값(vehicle_number/name) 누락"
        else:
            if file_vehicle_counts.get(vehicle_norm,0) > 1:
                review_reason="업로드 파일 내 차량번호 중복"
            else:
                vehicle_candidates=by_vehicle.get(vehicle_norm,[])
                if len(vehicle_candidates)==1:
                    match=vehicle_candidates[0]
                elif len(vehicle_candidates)>1:
                    review_reason="기존 DB 활성 차량번호 중복"
            if not match and not review_reason and r.get("management_number") and r.get("category"):
                candidates=by_mgmt_cat.get((r["management_number"],r["category"]),[])
                if len(candidates)==1: match=candidates[0]
                elif len(candidates)>1: review_reason="management_number+category 중복"
        if classification != "invalid" and match:
            seen_member_ids.add(match.id)
            fields={
                "management_number":r.get("management_number"),"region":r.get("region"),"vehicle_number":r.get("vehicle_number"),
                "name":r.get("name"),"category":r.get("category"),"address":r.get("address"),"phone":r.get("phone"),
                "mobile":r.get("mobile"),"master_membership_status":r.get("membership_status"),"certificate_number":r.get("certificate_number"),"vehicle_type":r.get("vehicle_type")
            }
            for f,new in fields.items():
                old=getattr(match,f,None)
                if (old or None)!=(new or None): diff[f]={"old":old,"new":new}
            classification="changed" if diff else "same"
            decision="apply" if diff else "skip"
        elif classification != "invalid" and review_reason:
            classification="needs_review"; decision="skip"
        counts[classification]+=1
        db.add(MemberImportRow(batch_id=batch.id,row_no=r["row_no"],source="file_row",raw={k:v for k,v in r.items() if k in SAFE_COPY_HEADERS},management_number=r.get("management_number"),name=r.get("name"),vehicle_number=r.get("vehicle_number"),vehicle_number_norm=vehicle_norm,mobile=r.get("mobile"),address=r.get("address"),category=r.get("category"),matched_member_id=match.id if match else None,classification=classification,review_reason=review_reason,diff=diff or None,decision=decision))

    if import_type=="full_snapshot" and category_scope:
        scoped=[m for m in existing if m.active and m.category==category_scope]
        if len(parsed) < max(1,int(len(scoped)*0.9)):
            warnings.append(f"업로드 행수({len(parsed)})가 현재 {category_scope} 활성회원({len(scoped)})의 90% 미만이라 누락 inactive 후보 자동생성을 차단했습니다.")
        else:
            for m in scoped:
                if m.id not in seen_member_ids and m.vehicle_number_norm not in file_vehicle_set:
                    counts["status_change"]+=1
                    db.add(MemberImportRow(batch_id=batch.id,row_no=None,source="missing_in_file",raw=None,management_number=m.management_number,name=m.name,vehicle_number=m.vehicle_number,vehicle_number_norm=m.vehicle_number_norm,mobile=m.mobile,address=m.address,category=m.category,matched_member_id=m.id,classification="status_change",review_reason="full_snapshot 파일에 없음 → inactive 후보",diff={"active":{"old":True,"new":False}},decision="pending"))

    batch.counts=dict(counts); batch.guard_warnings=warnings
    db.add(AdminActionLog(admin_user_id=admin_id,action="import_upload",target_type="member_import_batch",target_id=str(batch.id),after_value={"filename":filename,"import_type":import_type,"category_scope":category_scope,"counts":dict(counts)},reason="명부 비교 미리보기 생성"))
    db.commit(); db.refresh(batch)
    return batch

def apply_import(db: Session, batch_id: int, admin_id: int) -> dict:
    batch=db.get(MemberImportBatch,batch_id)
    if not batch or batch.status!="review": raise RosterError("batch_not_reviewable")
    rows=db.scalars(select(MemberImportRow).where(MemberImportRow.batch_id==batch_id)).all()
    applied=0; skipped=0
    for r in rows:
        if r.classification in {"invalid","same"}: skipped+=1; continue
        if r.classification=="needs_review" and r.decision!="apply": skipped+=1; continue
        if r.classification=="status_change":
            if r.decision!="apply": skipped+=1; continue
            m=db.get(Member,r.matched_member_id)
            if m:
                before={"active":m.active}; m.active=False; m.status_changed_at=datetime.now(timezone.utc); m.inactive_reason="full_snapshot 파일에 없음"; m.last_import_batch_id=batch.id; r.applied_at=datetime.now(timezone.utc); applied+=1
                db.add(AdminActionLog(admin_user_id=admin_id,action="member_status_change",target_type="member",target_id=str(m.id),member_id=m.id,before_value=before,after_value={"active":False},reason="full_snapshot 누락자 관리자 승인 반영"))
            continue
        raw=r.raw or {}
        if r.matched_member_id:
            m=db.get(Member,r.matched_member_id)
            if not m: skipped+=1; continue
            before={k:getattr(m,k,None) for k in ["management_number","region","vehicle_number","name","category","address","phone","mobile","master_membership_status","certificate_number","vehicle_type"]}
        else:
            m=Member(vehicle_number=raw.get("vehicle_number") or "",vehicle_number_norm=normalize_vehicle(raw.get("vehicle_number")),name=raw.get("name") or "",active=True)
            db.add(m); db.flush(); before=None
        mapping={"management_number":"management_number","region":"region","vehicle_number":"vehicle_number","name":"name","category":"category","address":"address","phone":"phone","mobile":"mobile","membership_status":"master_membership_status","certificate_number":"certificate_number","vehicle_type":"vehicle_type"}
        for src,dst in mapping.items(): setattr(m,dst,raw.get(src))
        m.vehicle_number_norm=normalize_vehicle(m.vehicle_number); m.active=True; m.last_import_batch_id=batch.id
        r.matched_member_id=m.id; r.applied_at=datetime.now(timezone.utc); applied+=1
        after={k:getattr(m,k,None) for k in ["management_number","region","vehicle_number","name","category","address","phone","mobile","master_membership_status","certificate_number","vehicle_type"]}
        db.add(AdminActionLog(admin_user_id=admin_id,action="member_import_apply",target_type="member",target_id=str(m.id),member_id=m.id,before_value=before,after_value=after,reason=f"{batch.original_filename} 반영"))
    batch.status="applied"; batch.applied_by_admin_id=admin_id; batch.applied_at=datetime.now(timezone.utc)
    db.add(AdminActionLog(admin_user_id=admin_id,action="import_apply",target_type="member_import_batch",target_id=str(batch.id),after_value={"applied":applied,"skipped":skipped},reason="검토된 명부 차이 반영"))
    db.commit()
    return {"applied":applied,"skipped":skipped}
