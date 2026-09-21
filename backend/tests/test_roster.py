import io
from openpyxl import Workbook
from backend.app.services.roster import parse_xlsx


def make_book(rows):
    wb=Workbook();ws=wb.active
    ws.append(['management_number','region','vehicle_number','name','category','address','phone','mobile','membership_status','certificate_number','vehicle_type'])
    for r in rows: ws.append(r)
    buf=io.BytesIO();wb.save(buf);return buf.getvalue()


def test_parse_real_header_shape():
    data=make_book([['M1','춘천시','강원81자 1234호','홍길동','개인','주소',None,'010-1111-2222','가입','26-001','24,봉고III1.2톤']])
    rows,headers=parse_xlsx(data)
    assert len(rows)==1
    assert rows[0]['vehicle_number_norm']=='강원81자1234호'
    assert rows[0]['certificate_number']=='26-001'
    assert rows[0]['vehicle_type']=='24,봉고III1.2톤'
