from calendar import monthrange
from datetime import date
from html import escape
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Member, Inspection, InspectionResult, InspectionItem, ChecklistVersion

CSS='''
@page{size:A4 landscape;margin:7mm}body{font-family:"Malgun Gothic","Noto Sans KR",sans-serif;color:#000;margin:0}.paper{width:100%}.note{font-size:10pt;margin-bottom:2mm}.title{text-align:center;font-size:16pt;font-weight:700;margin:0 0 4mm}.meta,.tbl{border-collapse:collapse;width:100%;table-layout:fixed}.meta th,.meta td,.tbl th,.tbl td{border:1px solid #000}.meta th{font-size:8.5pt;padding:2mm 1mm}.meta td{font-size:9pt;padding:2mm 1mm;text-align:center}.tbl{margin-top:3mm}.tbl th,.tbl td{font-size:6.3pt;padding:1.1mm .4mm;text-align:center;vertical-align:middle}.tbl .cat{width:8mm;font-weight:700;font-size:7.5pt;writing-mode:vertical-rl;letter-spacing:1px}.tbl .item{text-align:left;padding-left:1.5mm;font-size:7.2pt;line-height:1.25;width:47mm}.tbl .day{width:6.3mm}.tbl .symbol{font-size:9pt;font-weight:700}.tbl .action{text-align:left;padding:2mm;font-size:8pt}.controls{margin:0 0 10px}.controls button{padding:8px 14px;font-weight:700}@media print{.controls{display:none}}
'''

def build_legal_form(db:Session,member_id:int,month:str)->str:
    y,m=map(int,month.split('-'));member=db.get(Member,member_id)
    if not member: raise ValueError('member_not_found')
    v=db.scalar(select(ChecklistVersion).where(ChecklistVersion.is_current.is_(True)).order_by(ChecklistVersion.id.desc()))
    items=db.scalars(select(InspectionItem).where(InspectionItem.checklist_version_id==v.id).order_by(InspectionItem.seq)).all()
    start=date(y,m,1);end=date(y+1,1,1) if m==12 else date(y,m+1,1);days=monthrange(y,m)[1]
    inspections=db.scalars(select(Inspection).where(Inspection.member_id==member_id,Inspection.inspection_date>=start,Inspection.inspection_date<end)).all()
    by_date={r.inspection_date:r for r in inspections};issue_map={}
    for r in inspections:
        issue_map[r.id]=set(db.scalars(select(InspectionResult.item_id).where(InspectionResult.inspection_id==r.id)).all())
    def cell(d,item_id):
        if d>days:return''
        r=by_date.get(date(y,m,d))
        if not r:return''
        if r.status=='not_driving':return'미'
        if r.status=='normal':return'○'
        return '×' if item_id in issue_map.get(r.id,set()) else '○'
    groups=[]
    for g in ['외관점검','상태점검','기타']:
        groups.append((g,[i for i in items if i.group_name==g]))
    rows=[]
    for g,group_items in groups:
        for idx,it in enumerate(group_items):
            cat=f'<td class="cat" rowspan="{len(group_items)}">{escape(g)}</td>' if idx==0 else ''
            cells=''.join(f'<td class="symbol">{cell(d,it.id)}</td>' for d in range(1,32))
            rows.append(f'<tr>{cat}<td class="item">{escape(it.label_official)}</td>{cells}</tr>')
    sign='<tr><td colspan="2"><b>점검자 확인(서명)</b></td>'+''.join('<td></td>' for _ in range(1,32))+'</tr>'
    action=[]
    for r in inspections:
        if r.status=='issue':
            results=db.scalars(select(InspectionResult).where(InspectionResult.inspection_id==r.id)).all()
            for res in results:
                item=db.get(InspectionItem,res.item_id);action.append(f'{r.inspection_date.day}일 {item.label_official} - {res.action_note or "조치내용 확인"}')
    day_headers=''.join(f'<th class="day">{d}</th>' for d in range(1,32))
    body=''.join(rows)
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{month} 일상점검표</title><style>{CSS}</style></head><body><div class="controls"><button onclick="window.print()">인쇄 / PDF 저장</button></div><div class="paper"><div class="note">■ 화물자동차 운수사업법 시행규칙 [별지 제14호의5서식] &lt;신설 2025. 12. 29.&gt; [시행일: 2026. 6. 30.]</div><div class="title">운수종사자 일상점검표</div><table class="meta"><tr><th>점검연월</th><td>{y}년 {m}월</td><th>운송사업자명</th><td>{escape(member.business_name or member.name)}</td><th>차량번호</th><td>{escape(member.vehicle_number)}</td><th>운수종사자명</th><td>{escape(member.name)}</td></tr></table><table class="tbl"><tr><th colspan="2" rowspan="2">점검항목</th><th colspan="31">점검결과(양호 ○, 불량 ×, 미운행시 “미” 기입)</th></tr><tr>{day_headers}</tr>{body}{sign}<tr><td colspan="2"><b>불량상태 조치 기록</b></td><td class="action" colspan="31">{escape(' / '.join(action) if action else '(예시) 00일 창닦이기 불량 - 00일 창닦이기 교체')}</td></tr></table></div></body></html>'''
    return html
