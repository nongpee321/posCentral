# -*- coding: utf-8 -*-
from ui.receipt_dialog import (
    ReceiptDialog,
    _format_receipt_qty,
    _format_total_qty,
    _receipt_date_label,
    _receipt_raster_commands,
)


def test_receipt_helper_formatters():
    assert _format_receipt_qty(0.27) == "0.2 **"
    assert _format_receipt_qty(0.37) == "0.3 **"
    assert _format_receipt_qty(2) == "2"
    assert _format_total_qty(0.64) == "0.64"
    assert _format_total_qty(2.0) == "2"
    assert _receipt_date_label("2026-10-26 16:04:00") == "26/10/2569 16:04"


def test_no_satang_rounding_calculation():
    from ui.main_window import MainWindow
    dummy = type('Dummy', (), {'discount_amount': 0.0})()
    totals = MainWindow._compute_rounded_totals(dummy, 319.80)
    assert totals['subtotal'] == 319.80
    assert totals['satang_discount'] == 0.0
    assert totals['total_discount'] == 0.0
    assert totals['grand_total'] == 319.80


def test_receipt_dialog_matches_reference_slip(qtbot):
    receipt_data = {
        "doc_number": "000201254756",
        "date": "2026-10-26 16:04:00",
        "total": 59.00,
        "satang_discount": 0.18,
        "discount_amount": 0.00,
        "payment_method": "cash",
        "cash_received": 59.00,
        "change_amount": 0.00,
        "cashier": "01",
        "items": [
            {"name": "ตับไก่ (ชั่งน้ำหนัก)", "qty": 0.27, "price": 89.00, "total": 24.03},
            {"name": "ปีกบนไก่ (ชั่งน้ำหนัก)", "qty": 0.37, "price": 95.00, "total": 35.15},
        ],
    }
    dlg = ReceiptDialog(None, receipt_data)
    qtbot.addWidget(dlg)
    plain = dlg.receipt_text.toPlainText()
    assert "POP STAR SHOP" in plain
    assert "ใบรับเงิน" in plain
    assert "0.2 ** ตับไก่" in plain
    assert "24.03#" in plain
    assert "35.15#" in plain
    assert "ลดจากปัดเศษสตางค์" not in plain
    assert "ยอดรวม" in plain
    assert "59.18" in plain
    assert "เงินสด" in plain
    assert "รวมรายการ" in plain
    assert "รวมชิ้น" in plain
    assert "0.64" in plain
    assert "Cashier :" in plain
    assert "01" in plain
    assert "000201254756" in plain
    assert "26/10/2569 16:04" in plain


def test_version_string_and_receipt_jumbo_sizing(qtbot):
    from ui.token_dialog import VERSION_STRING
    assert VERSION_STRING == "1.2.21"

    dlg = ReceiptDialog(None, {
        "doc_number": "POS-0001-20260417100516-247",
        "date": "2026-04-17 10:05:00",
        "total": 180.00,
        "items": [
            {"name": "ANATOLI เส้นสปาเก็ตตี้", "qty": 1, "price": 130.00, "total": 130.00},
            {"name": "Ponn น้ำจิ้มแจ่ว 200G", "qty": 1, "price": 50.00, "total": 50.00},
        ],
    })
    qtbot.addWidget(dlg)
    dlg.update_receipt_ui({"receipt_font_scale": "large"})
    assert dlg.receipt_paper_size == "80mm"
    raw = _receipt_raster_commands(dlg.receipt_text.document(), dlg.receipt_paper_size)
    # 576 dots = 72 bytes per raster row (0x48, 0x00)
    assert b"\x1dv0\x00\x48\x00" in raw


def test_receipt_settings_dialog_copies_and_printer(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    from ui.receipt_dialog import ReceiptSettingsDialog
    config = {'receipt_printer': '', 'receipt_copies': 2}
    dlg = ReceiptSettingsDialog(None, config)
    qtbot.addWidget(dlg)

    # Check only printer and copies are present
    assert hasattr(dlg, 'printer_combo')
    assert hasattr(dlg, 'copies_spin')
    assert not hasattr(dlg, 'header_edit')
    assert not hasattr(dlg, 'footer_edit')
    assert not hasattr(dlg, 'paper_size_combo')
    assert not hasattr(dlg, 'font_scale_combo')

    assert dlg.copies_spin.value() == 2
    dlg.copies_spin.setValue(3)
    dlg.save_settings(and_test=False)

    assert dlg.config['receipt_copies'] == 3

