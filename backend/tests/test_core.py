from backend.app.utils import normalize_vehicle, normalize_phone
from backend.app.security import hash_pin, verify_pin, totp_code, verify_totp


def test_normalize_vehicle():
    assert normalize_vehicle('강원81배 1103호') == '강원81배1103호'
    assert normalize_vehicle(' 강원 81배 1103호 ') == '강원81배1103호'


def test_normalize_phone():
    assert normalize_phone('010-1234-5678') == '01012345678'


def test_pin_hash_roundtrip():
    h=hash_pin(123,'4321')
    assert verify_pin(123,'4321',h)
    assert not verify_pin(123,'1234',h)


def test_totp_generation_shape():
    code=totp_code('JBSWY3DPEHPK3PXP',at=0)
    assert len(code)==6 and code.isdigit()
