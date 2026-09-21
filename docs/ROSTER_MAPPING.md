# 실제 전체면허자 명부 매핑

확인한 파일:
- 택배회원: 2,248 데이터행
- 개인회원: 1,608 데이터행
- 총 3,856 데이터행

두 파일 모두 30개 컬럼이며 앱은 개인정보 최소화를 위해 필요한 컬럼만 읽습니다.

| Excel | 시스템 | 공개 범위 |
|---|---|---|
| management_number | members.management_number | 관리자 전용 |
| region | members.region | 관리자 |
| vehicle_number | members.vehicle_number | 기사/관리자 |
| name | members.name | 기사/관리자 |
| category | members.category | 관리자 |
| address | members.address | 본인/관리자 |
| phone | members.phone | 관리자 |
| mobile | members.mobile | 본인/관리자 |
| membership_status | members.master_membership_status | 관리자 |
| certificate_number | members.certificate_number | 관리자 전용 |
| vehicle_type | members.vehicle_type | 본인/관리자 |

원본 파일에 포함된 주민등록번호, 운전면허번호, 대리인 주민번호 등은 일상점검 시스템 Import 대상에서 제외합니다.
