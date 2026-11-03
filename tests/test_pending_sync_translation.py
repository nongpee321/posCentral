import json
from ui.pending_sync_dialog import translate_sync_error


def test_translate_discount_approval_error():
    raw = '{"message": "The discount approved by field must be a string.", "errors": {"discount_approved_by": ["The discount approved by field must be a string."]}}'
    translated = translate_sync_error(raw)
    assert "สิทธิ์อนุมัติส่วนลดไม่ถูกต้อง" in translated
    assert "ผู้จัดการ" in translated


def test_translate_held_for_review_error():
    raw = 'held_for_discount_review'
    translated = translate_sync_error(raw)
    assert "บิลถูกพักไว้เพื่อตรวจสอบส่วนลด" in translated


def test_translate_timeout_and_network_error():
    assert "Timeout" in translate_sync_error("HTTPSConnectionPool(host='erp.popstarcenter.com', port=443): Read timed out.")
    assert "ไม่สามารถเชื่อมต่ออินเทอร์เน็ต" in translate_sync_error("Failed to establish a new connection: [WinError 10061] Connection refused")


def test_translate_branch_and_shift_error():
    assert "สาขา" in translate_sync_error('{"message": "The selected branch id is invalid."}')
    assert "กะขาย" in translate_sync_error('{"message": "Shift is closed or not found"}')


def test_translate_user_discarded_bill():
    assert "ผู้ใช้ยกเลิกบิลค้างนี้แล้ว" in translate_sync_error("ผู้ใช้ยกเลิกบิลค้าง")
