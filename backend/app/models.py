from datetime import datetime, date
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, LargeBinary,
    String, Text, UniqueConstraint, JSON, func, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Member(Base, TimestampMixin):
    __tablename__ = "members"
    id: Mapped[int] = mapped_column(primary_key=True)
    management_number: Mapped[str|None] = mapped_column(String(80), index=True)
    region: Mapped[str|None] = mapped_column(String(80), index=True)
    vehicle_number: Mapped[str] = mapped_column(String(80))
    vehicle_number_norm: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str|None] = mapped_column(String(40), index=True)
    address: Mapped[str|None] = mapped_column(Text)
    phone: Mapped[str|None] = mapped_column(String(40))
    mobile: Mapped[str|None] = mapped_column(String(40), index=True)
    master_membership_status: Mapped[str|None] = mapped_column(String(40))
    certificate_number: Mapped[str|None] = mapped_column(String(80), index=True)
    vehicle_type: Mapped[str|None] = mapped_column(String(160), index=True)
    business_name: Mapped[str|None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    tracking_start_date: Mapped[date|None] = mapped_column(Date)
    status_changed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    inactive_reason: Mapped[str|None] = mapped_column(Text)
    extra: Mapped[dict|None] = mapped_column(JSON)
    last_import_batch_id: Mapped[int|None] = mapped_column(ForeignKey("member_import_batches.id"))
    __table_args__ = (Index("uq_members_active_vehicle", "vehicle_number_norm", unique=True, postgresql_where=text("active = true"), sqlite_where=text("active = 1")),)

class DriverAccount(Base, TimestampMixin):
    __tablename__ = "driver_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), unique=True, index=True)
    pin_hash: Mapped[str|None] = mapped_column(Text)
    pepper_version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(30), default="active")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    pin_set_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    reset_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    reset_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))

class TrustedDevice(Base, TimestampMixin):
    __tablename__ = "trusted_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    platform: Mapped[str] = mapped_column(String(30), default="web")
    user_agent: Mapped[str|None] = mapped_column(Text)
    app_version: Mapped[str|None] = mapped_column(String(40))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_ip: Mapped[str|None] = mapped_column(String(64))
    revoked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str|None] = mapped_column(Text)

class DriverSession(Base, TimestampMixin):
    __tablename__ = "driver_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    device_id: Mapped[int|None] = mapped_column(ForeignKey("trusted_devices.id"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    login_ip: Mapped[str|None] = mapped_column(String(64))
    revoked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str|None] = mapped_column(Text)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    attempt_type: Mapped[str] = mapped_column(String(40))
    member_id: Mapped[int|None] = mapped_column(ForeignKey("members.id"), index=True)
    vehicle_number_norm_input: Mapped[str|None] = mapped_column(String(100))
    device_id: Mapped[int|None] = mapped_column(ForeignKey("trusted_devices.id"))
    ip: Mapped[str|None] = mapped_column(String(64), index=True)
    user_agent: Mapped[str|None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(40))
    lock_scope: Mapped[str|None] = mapped_column(String(40))
    request_id: Mapped[str|None] = mapped_column(String(64))

class AuthLockout(Base, TimestampMixin):
    __tablename__ = "auth_lockouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(40))
    scope_key: Mapped[str] = mapped_column(String(160))
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), index=True)
    last_fail_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    window_started_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    released_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    released_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint("scope_type","scope_key",name="uq_auth_lock_scope"),)

class ChecklistVersion(Base, TimestampMixin):
    __tablename__ = "checklist_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    form_name: Mapped[str] = mapped_column(String(160))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date|None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source_note: Mapped[str|None] = mapped_column(Text)

class InspectionItem(Base, TimestampMixin):
    __tablename__ = "inspection_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_version_id: Mapped[int] = mapped_column(ForeignKey("checklist_versions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(40))
    group_name: Mapped[str] = mapped_column(String(40))
    label_official: Mapped[str] = mapped_column(Text)
    label_display: Mapped[str] = mapped_column(Text)
    official_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__=(UniqueConstraint("checklist_version_id","seq"), UniqueConstraint("checklist_version_id","code"))

class Inspection(Base, TimestampMixin):
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    inspection_date: Mapped[date] = mapped_column(Date, index=True)
    checklist_version_id: Mapped[int] = mapped_column(ForeignKey("checklist_versions.id"))
    status: Mapped[str] = mapped_column(String(30), index=True)
    first_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    current_revision_no: Mapped[int] = mapped_column(Integer, default=1)
    entry_channel: Mapped[str] = mapped_column(String(30), default="driver")
    entered_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    is_late_entry: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    proxy_method: Mapped[str|None] = mapped_column(String(40))
    proxy_reason: Mapped[str|None] = mapped_column(Text)
    memo: Mapped[str|None] = mapped_column(Text)
    __table_args__=(UniqueConstraint("member_id","inspection_date",name="uq_inspection_member_date"), CheckConstraint("status in ('normal','issue','not_driving')"))

class InspectionResult(Base, TimestampMixin):
    __tablename__ = "inspection_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inspection_items.id"))
    action_note: Mapped[str|None] = mapped_column(Text)
    __table_args__=(UniqueConstraint("inspection_id","item_id"),)

class InspectionRevision(Base, TimestampMixin):
    __tablename__ = "inspection_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    problem_items: Mapped[list|None] = mapped_column(JSON)
    memo: Mapped[str|None] = mapped_column(Text)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_member_id: Mapped[int|None] = mapped_column(ForeignKey("members.id"))
    actor_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    entry_channel: Mapped[str] = mapped_column(String(30))
    change_reason: Mapped[str|None] = mapped_column(Text)
    client_request_id: Mapped[str|None] = mapped_column(String(80), unique=True)
    __table_args__=(UniqueConstraint("inspection_id","revision_no"),)

class ComplianceEvent(Base, TimestampMixin):
    __tablename__ = "compliance_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_member_id: Mapped[int|None] = mapped_column(ForeignKey("members.id"))
    actor_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    original_event_id: Mapped[int|None] = mapped_column(ForeignKey("compliance_events.id"))
    source: Mapped[str|None] = mapped_column(String(40))
    ip: Mapped[str|None] = mapped_column(String(64))
    note: Mapped[str|None] = mapped_column(Text)

class MemberChangeRequest(Base, TimestampMixin):
    __tablename__ = "member_change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(40), default="address")
    old_value: Mapped[str|None] = mapped_column(Text)
    new_value: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    requested_via: Mapped[str] = mapped_column(String(30), default="driver_app")
    decided_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    decided_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str|None] = mapped_column(Text)

class MemberImportBatch(Base, TimestampMixin):
    __tablename__ = "member_import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(20), default="1")
    import_type: Mapped[str] = mapped_column(String(30))
    category_scope: Mapped[str|None] = mapped_column(String(40))
    column_mapping: Mapped[dict|None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="review")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    counts: Mapped[dict|None] = mapped_column(JSON)
    guard_warnings: Mapped[list|None] = mapped_column(JSON)
    applied_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    applied_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))

class MemberImportRow(Base, TimestampMixin):
    __tablename__ = "member_import_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("member_import_batches.id"), index=True)
    row_no: Mapped[int|None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30), default="file_row")
    raw: Mapped[dict|None] = mapped_column(JSON)
    management_number: Mapped[str|None] = mapped_column(String(80))
    name: Mapped[str|None] = mapped_column(String(80))
    vehicle_number: Mapped[str|None] = mapped_column(String(80))
    vehicle_number_norm: Mapped[str|None] = mapped_column(String(80))
    mobile: Mapped[str|None] = mapped_column(String(40))
    address: Mapped[str|None] = mapped_column(Text)
    category: Mapped[str|None] = mapped_column(String(40))
    matched_member_id: Mapped[int|None] = mapped_column(ForeignKey("members.id"))
    classification: Mapped[str] = mapped_column(String(40), index=True)
    review_reason: Mapped[str|None] = mapped_column(Text)
    diff: Mapped[dict|None] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(20), default="pending")
    applied_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))

class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    login_id: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30), default="staff")
    status: Mapped[str] = mapped_column(String(30), default="active")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret: Mapped[str|None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    created_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))

class AdminSession(Base, TimestampMixin):
    __tablename__ = "admin_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    csrf_token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str|None] = mapped_column(String(64))
    user_agent: Mapped[str|None] = mapped_column(Text)
    revoked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str|None] = mapped_column(Text)

class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    admin_user_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"), index=True)
    admin_role: Mapped[str|None] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str|None] = mapped_column(String(60))
    target_id: Mapped[str|None] = mapped_column(String(80))
    member_id: Mapped[int|None] = mapped_column(ForeignKey("members.id"), index=True)
    before_value: Mapped[dict|None] = mapped_column(JSON)
    after_value: Mapped[dict|None] = mapped_column(JSON)
    reason: Mapped[str|None] = mapped_column(Text)
    request_id: Mapped[str|None] = mapped_column(String(80))
    ip: Mapped[str|None] = mapped_column(String(64))
    user_agent: Mapped[str|None] = mapped_column(Text)

class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict|str|int|bool|None] = mapped_column(JSON)
    value_type: Mapped[str] = mapped_column(String(30), default="json")
    policy_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str|None] = mapped_column(Text)
    updated_by_admin_id: Mapped[int|None] = mapped_column(ForeignKey("admin_users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
