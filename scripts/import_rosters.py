import sys
from pathlib import Path as _Path
sys.path.insert(0,str(_Path(__file__).resolve().parents[1]))
"""관리자 UI 대신 CLI에서 명부를 미리보기/반영할 때 사용하는 보조 스크립트.
원본 Excel은 절대 Git 저장소에 넣지 않습니다.
"""
import argparse
from pathlib import Path
from backend.app.db import SessionLocal
from backend.app.services.roster import preview_import, apply_import
from backend.app.services.bootstrap import ensure_seed_data
from backend.app.models import AdminUser
from sqlalchemy import select
from backend.app.config import settings

p=argparse.ArgumentParser()
p.add_argument('xlsx')
p.add_argument('--type',choices=['full_snapshot','partial_update'],default='partial_update')
p.add_argument('--apply',action='store_true')
a=p.parse_args()
content=Path(a.xlsx).read_bytes()
db=SessionLocal();ensure_seed_data(db)
admin=db.scalar(select(AdminUser).where(AdminUser.login_id==settings.bootstrap_admin_login))
b=preview_import(db,content,Path(a.xlsx).name,a.type,admin.id)
print('batch',b.id,'category',b.category_scope,'counts',b.counts,'warnings',b.guard_warnings)
if a.apply:
    print(apply_import(db,b.id,admin.id))
db.close()
