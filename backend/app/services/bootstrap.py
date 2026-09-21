from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import AdminUser, ChecklistVersion, InspectionItem, SystemSetting
from ..security import hash_password
from ..config import settings

ITEMS = [
    (1,"EXT01","외관점검","번호판, 전면유리, 후사경 등의 청결상태"),
    (2,"EXT02","외관점검","후미등, 차폭등 등 등화장치 작동상태"),
    (3,"EXT03","외관점검","창닦이기 작동상태"),
    (4,"EXT04","외관점검","적재함(보조지지대 포함), 측면 보호대, 후부반사판, 트레일러 연결장치의 부착 상태 및 훼손 여부"),
    (5,"COND01","상태점검","타이어 손상 및 마모(1.6mm이상) 여부"),
    (6,"COND02","상태점검","화물, 적재함 지지대(판스프링) 등의 고정상태"),
    (7,"COND03","상태점검","바퀴 너트 등 균열 여부"),
    (8,"ETC01","기타","냉각수, 공기압, 엔진오일 등 차량 이상 여부(계기판 확인)"),
    (9,"ETC02","기타","좌석안전띠 상태"),
    (10,"ETC03","기타","소화기 비치 여부"),
    (11,"ETC04","기타","안전삼각대 등 비치 여부"),
]

DEFAULT_SETTINGS = {
    "late_entry_mode": ("unlimited", False, "과거 입력 모드"),
    "late_entry_days": (None, False, "과거 입력 허용 일수"),
    "driver_same_day_edit_enabled": (False, False, "기사 당일 수정 허용"),
    "admin_correction_enabled": (False, False, "관리자 정정 허용"),
    "session_ttl_days": (180, False, "기사 세션 TTL"),
    "max_devices_per_member": (3, False, "회원당 최대 신뢰기기"),
    "staff_totp_required": (False, False, "staff TOTP 사용 안 함"),
}

def ensure_seed_data(db: Session):
    admin = db.scalar(select(AdminUser).where(AdminUser.login_id == settings.bootstrap_admin_login))
    if not admin:
        admin = AdminUser(
            login_id=settings.bootstrap_admin_login,
            display_name="최고관리자",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="super_admin", status="active", must_change_password=(settings.app_env=="production"),
            totp_secret=None, totp_enabled=False,
        )
        db.add(admin)
    else:
        admin.totp_secret = None
        admin.totp_enabled = False
    version = db.scalar(select(ChecklistVersion).where(ChecklistVersion.code == "FORM14_5_2025_12_29"))
    if not version:
        version = ChecklistVersion(
            code="FORM14_5_2025_12_29", form_name="별지 제14호의5서식",
            effective_from=date(2026,6,30), is_current=True,
            source_note="화물자동차 운수사업법 시행규칙 별지 제14호의5서식"
        )
        db.add(version); db.flush()
        for seq, code, group, label in ITEMS:
            db.add(InspectionItem(checklist_version_id=version.id,seq=seq,code=code,group_name=group,label_official=label,label_display=label,official_verified=True))
    for key,(value,pending,desc) in DEFAULT_SETTINGS.items():
        if not db.get(SystemSetting,key):
            db.add(SystemSetting(key=key,value=value,value_type=type(value).__name__,policy_pending=pending,description=desc))
    db.commit()
