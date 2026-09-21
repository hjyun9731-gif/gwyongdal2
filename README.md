# gwyongdal 기사앱 v3.2 UI 패치

목적:
- 승인된 v3.2 디자인을 운영 FastAPI 기사앱에 반영
- API / DB / 점검 저장 로직은 변경하지 않음
- 관리자 화면은 변경하지 않음

교체 파일:
- backend/app/static/driver.html
- backend/app/static/driver.js
- backend/app/static/common.css
- backend/app/static/truck.webp

적용:
1. ZIP 압축 해제
2. 기존 프로젝트 루트에 backend 폴더 덮어쓰기
3. git add .
4. git commit -m "Match driver app to v3.2 UI"
5. git push
6. Railway Active 후 기사앱에서 Ctrl+F5

검증:
- JavaScript syntax: node --check
- 기존 API 엔드포인트 문자열 유지 확인
