# 배포 순서

1. GitHub 새 저장소 `gwyongdal-v2` 생성
2. 이 프로젝트 전체 push
3. Railway 새 프로젝트 생성
4. PostgreSQL 서비스 추가
5. GitHub 서비스 연결
6. Railway Variables 입력
7. 배포 후 `/health` 확인
8. 관리자 로그인 후 실제 `개인회원`, `택배회원` Excel을 각각 Import
   - 첫 전체 반영은 각 파일별 `full_snapshot`
   - 이후 변경자만 담긴 파일이면 `partial_update`
9. 기사 파일럿 5~10명
10. 파일럿 통과 후 Google Play TWA 패키징
