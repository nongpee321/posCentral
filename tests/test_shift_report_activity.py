import pytest
from ui.receipt_dialog import ShiftReportDialog

def test_shift_report_activity_rendering(qtbot):
    shift_data = {
        'id': 99,
        'shift_no': '99',
        'branch_name': 'สาขาทดสอบ',
        'cashier_name': 'สมชาย',
        'status': 'closed',
        'opened_at': '2026-11-03 08:00:00',
        'closed_at': '2026-11-03 17:00:00',
        'total_sales': 1500.0,
        'receipt_count': 10,
        'held_bill_count': 4,
        'resumed_bill_count': 3,
        'voided_bill_count': 2,
        'edited_bill_count': 1,
        'cash_sales': 1000.0,
        'transfer_sales': 500.0,
        'card_sales': 0.0,
        'opening_cash': 1000.0,
        'counted_cash': 2000.0,
        'cash_difference': 0.0
    }
    dlg = ShiftReportDialog(None, shift_data)
    qtbot.addWidget(dlg)
    html = dlg.report_text.toHtml()
    assert "สรุปกิจกรรมภายในกะ" in html
    assert "บิลขายสำเร็จ" in html
    assert "10 บิล" in html
    assert "บิลพักทั้งหมด" in html
    assert "4 บิล" in html
    assert "บิลพักที่เรียกกลับมาขายต่อ" in html
    assert "3 บิล" in html
    assert "บิลยกเลิก" in html
    assert "2 บิล" in html
    assert "บิลที่แก้ไข" in html
    assert "1 บิล" in html
