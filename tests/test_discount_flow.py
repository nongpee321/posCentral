import pytest
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt
from ui.discount_dialog import DiscountDialog
from ui.customer_display import CustomerDisplayWindow
from database.models import init_db, Sale, Outbox, Product

app = QApplication.instance() or QApplication([])

def test_discount_dialog_touch_keypad_and_presets(qtbot):
    dialog = DiscountDialog(subtotal=650.0, current_discount=0.0)
    qtbot.addWidget(dialog)

    # Test quick preset 50
    dialog.apply_preset("50")
    assert dialog.val_input.text() == "50"
    dialog.recalc()
    assert "-฿50.00" in dialog.preview_disc_lbl.text()
    assert "฿600.00" in dialog.preview_net_lbl.text()

    # Test touch keypad append
    dialog.clear_keypad()
    dialog.append_keypad("1")
    dialog.append_keypad("0")
    dialog.append_keypad("0")
    assert dialog.val_input.text() == "100"
    dialog.recalc()
    assert "-฿100.00" in dialog.preview_disc_lbl.text()
    assert "฿550.00" in dialog.preview_net_lbl.text()

    # Test backspace
    dialog.backspace_keypad()
    assert dialog.val_input.text() == "10"

    # Test percentage mode
    dialog.radio_pct.setChecked(True)
    dialog.on_mode_changed(2)
    dialog.apply_preset("10")
    dialog.recalc()
    assert "-฿65.00 (10%)" in dialog.preview_disc_lbl.text()
    assert "฿585.00" in dialog.preview_net_lbl.text()

    # Confirm
    dialog.on_confirm()
    assert dialog.discount_amount == 65.0
    assert dialog.discount_label == "10%"

def test_customer_display_discount_rendering(qtbot):
    cd = CustomerDisplayWindow()
    qtbot.addWidget(cd)

    # Mock table with 1 item
    tbl = QTableWidget(1, 4)
    tbl.setItem(0, 0, QTableWidgetItem("Cargill 10kg"))
    tbl.setItem(0, 1, QTableWidgetItem("1"))
    tbl.setItem(0, 2, QTableWidgetItem("650.00"))
    tbl.setItem(0, 3, QTableWidgetItem("650.00"))

    # When discount of 50 is applied, total is 600
    cd.update_cart(tbl, total_amount=600.0, subtotal=650.0, discount=50.0)

    assert cd.total_lbl.text() == "600.00"
    assert cd.disc_lbl.text() == "50.00 ฿"
    assert "560.75 ฿" in cd.subtotal_lbl.text()
    assert "39.25 ฿" in cd.vat_lbl.text()

    # Test show_payment accepts float directly
    cd.show_payment(600.0)
    assert not cd.qr_box.isHidden()
    assert cd.spacer_widget.isHidden() is True

    # Test show_success clears discount
    cd.show_success(change=0.0)
    assert cd.disc_lbl.text() == "0.00 ฿"
    assert cd.total_lbl.text() == "0.00"

def test_sale_model_persists_discount(tmp_path):
    db_path = str(tmp_path / "sale_disc.db")
    session = init_db(f"sqlite:///{db_path}")

    sale = Sale(
        local_sale_id="test-sale-1",
        doc_number="003401000001",
        branch_id=34,
        total_amount=600.0,
        received_amount=600.0,
        discount_amount=50.0,
        payment_method="transfer",
        idempotency_key="offline-receipt-test-sale-1"
    )
    session.add(sale)
    session.commit()

    loaded = session.query(Sale).filter_by(local_sale_id="test-sale-1").first()
    assert loaded is not None
    assert loaded.total_amount == 600.0
    assert loaded.discount_amount == 50.0
    session.close()

def test_payment_dialog_discount_support(qtbot):
    from ui.payment_dialog import PaymentDialog
    dlg = PaymentDialog(total_amount=650.0, total_items=1, total_qty=1.0, discount_amount=0.0)
    qtbot.addWidget(dlg)

    assert dlg.total_amount == 650.0
    assert dlg.subtotal == 650.0
    assert dlg.btn_discount_dialog is not None

    # Apply 50 baht discount directly
    dlg.discount_amount = 50.0
    dlg.total_amount = 600.0
    dlg.update_summary_card()

    assert dlg.total_amount == 600.0
    assert "600.00" in dlg.total_lbl.text()

def test_customer_display_show_payment_updates_discount_and_total(qtbot):
    cd = CustomerDisplayWindow()
    qtbot.addWidget(cd)

    cd.show_payment("QR", override_amount=595.0, discount=55.0)
    assert cd.total_lbl.text() == "595.00"
    assert cd.disc_lbl.text() == "55.00 ฿"
    assert "556.07 ฿" in cd.subtotal_lbl.text()
    assert "38.93 ฿" in cd.vat_lbl.text()
    assert not cd.qr_box.isHidden()



def test_uat_e2e_70_minus_10_bill_sync_after_retry_matches_receipt_and_erp(qtbot, tmp_path, monkeypatch):
    """
    UAT End-to-End Test:
    - ขายสินค้า 70.00 บาท ลด 10.00 บาท ใบเสร็จออกสุทธิ 60.00 บาท (รับเงินสด 60.00 เงินทอน 0.00)
    - ซิงก์ครั้งแรกไม่สำเร็จ (Network Error)
    - ซิงก์ใหม่ครั้งที่สองสำเร็จ
    - ตรวจผลลัพธ์ฝั่ง ERP:
      * ยอดก่อนลด (gross_sales) = 70.00
      * ส่วนลด (discount_amount / manual_discount_amount) = 10.00
      * ผู้อนุมัติส่วนลด (discount_approved_by) = 77
      * ยอดสุทธิ (net_sales) = 60.00
      * ยอดรับเงินจริง (cash_received) = 60.00 ตรงกับใบเสร็จ
    """
    import json
    import requests
    from ui.main_window import MainWindow
    from sync_worker import SyncWorker
    import sync_worker as sync_worker_module

    db_path = str(tmp_path / "uat_70_10.db")
    session = init_db(f"sqlite:///{db_path}")
    session.add(Product(
        id=501,
        sku_code="UAT-70",
        barcode="8850000000701",
        name_th="สินค้า UAT 70 บาท",
        default_price=70.0,
        pos_price=70.0,
        is_active=True,
    ))
    session.commit()
    session.close()

    window = MainWindow(db_path=db_path)
    if hasattr(window, "sync_worker") and window.sync_worker:
        window.sync_worker.is_running = False
        window.sync_worker.wait(500)
    qtbot.addWidget(window)
    window.config.update({
        "api_url": "http://erp.uat.local",
        "pos_token": "uat-token",
        "branch_id": 1,
        "cashier_id": 11,
        "cashier_user_id": 77,
        "user_id": 77,
        "cashier_name": "UAT Cashier",
    })
    window.current_shift = {"id": 88, "local_id": 1, "branch_id": 1, "cashier_id": 11, "cashier_user_id": 77}

    # Add product 70 Baht to cart
    window.cart_table.setRowCount(1)
    name_item = QTableWidgetItem("สินค้า UAT 70 บาท")
    name_item.setData(Qt.UserRole, 501)
    window.cart_table.setItem(0, 0, name_item)
    window.cart_table.setItem(0, 1, QTableWidgetItem("1"))
    window.cart_table.setItem(0, 2, QTableWidgetItem("70.00"))
    window.cart_table.setItem(0, 3, QTableWidgetItem("70.00"))

    # Apply 10 Baht discount
    window.discount_amount = 10.0
    window.discount_label = "฿10.00"
    window.discount_approved_by = window._resolve_discount_approver_id()
    window.update_cart_total()

    captured_receipts = []

    class CaptureReceiptDialog:
        def __init__(self, parent, receipt_data, config=None):
            captured_receipts.append(dict(receipt_data))

        def exec(self):
            return 0

    class NoOpSyncWorker:
        def force_sync(self):
            pass

        def get_pending_count(self):
            return 1

    window.sync_worker = NoOpSyncWorker()
    monkeypatch.setattr("ui.receipt_dialog.ReceiptDialog", CaptureReceiptDialog)

    # Checkout: gross 70, discount 10, net 60, received 60, change 0
    window.process_payment("เงินสด", 60.0, 0.0, cash_amount=60.0)

    assert len(captured_receipts) == 1
    printed_receipt = captured_receipts[0]
    assert printed_receipt["subtotal"] == 70.0
    assert printed_receipt["discount_amount"] == 10.0
    assert printed_receipt["total"] == 60.0
    assert printed_receipt["cash_received"] == 60.0

    # Now run SyncWorker where 1st request fails and 2nd request is validated by simulated ERP
    erp_recorded_receipts = []
    call_counter = {"n": 0}

    class FakeShiftRes:
        status_code = 200

        def json(self):
            return {"shift": {"id": 88, "branch_id": 1, "cashier_id": 11, "cashier_user_id": 77}}

        def raise_for_status(self):
            pass

    class FakeErpCheckoutRes:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.text = json.dumps(body, ensure_ascii=False)

        def json(self):
            return self._body

        def raise_for_status(self):
            pass

    def fake_erp_post(url, json=None, headers=None, timeout=None):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            raise requests.Timeout("UAT simulated first request timeout")

        # Simulate ERP PosPricingGuard + PosPaymentValidator + PosController::recordPosReceipt
        gross = round(sum(float(i["qty"]) * float(i["unit_price"]) for i in json["items"]), 2)
        manual_disc = round(float(json.get("manual_discount_amount") or 0.0), 2)
        disc_amount = round(float(json.get("discount_amount") or 0.0), 2)
        approver = json.get("discount_approved_by")
        assert manual_disc == 10.0
        assert disc_amount == 10.0
        assert approver == 77
        net = round(gross - manual_disc, 2)
        cash_recv = round(float(json.get("cash_received") or 0.0), 2)
        change_amt = round(float(json.get("change_amount") or 0.0), 2)
        assert cash_recv >= net

        erp_record = {
            "receipt_no": "CSB00120261031999",
            "gross_sales": gross,
            "discount_amount": manual_disc,
            "net_sales": net,
            "cash_received": cash_recv,
            "change_amount": change_amt,
            "payment_amount": net,
            "discount_approved_by": approver,
        }
        erp_recorded_receipts.append(erp_record)
        return FakeErpCheckoutRes(200, {
            "success": True,
            "receipt_id": 999,
            "receipt_no": "CSB00120261031999",
            "total_amount": net,
        })

    monkeypatch.setattr(sync_worker_module.requests, "get", lambda *a, **kw: FakeShiftRes())
    monkeypatch.setattr(sync_worker_module.requests, "post", fake_erp_post)

    worker = SyncWorker(
        db_path,
        "http://erp.uat.local",
        "uat-token",
        config=window.config,
    )
    ok1, _ = worker._sync_outbox_sales()
    assert ok1 is False

    ok2, _ = worker._sync_outbox_sales()
    assert ok2 is True

    assert len(erp_recorded_receipts) == 1
    erp_bill = erp_recorded_receipts[0]
    assert erp_bill["gross_sales"] == 70.0
    assert erp_bill["discount_amount"] == 10.0
    assert erp_bill["net_sales"] == 60.0
    assert erp_bill["payment_amount"] == 60.0
    assert erp_bill["cash_received"] == printed_receipt["cash_received"] == 60.0
    assert erp_bill["change_amount"] == 0.0
    assert erp_bill["discount_approved_by"] == 77
