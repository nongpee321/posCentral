import json
import unittest.mock as mock
import pytest
import requests
from sync_worker import SyncWorker
from database.models import init_db, Sale, SaleItem, Payment, Outbox, Product, PosShift


def test_sync_worker_offline_detection(tmp_path):
    db_path = str(tmp_path / "sync_test.db")
    init_db(f"sqlite:///{db_path}")

    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    worker._check_internet = lambda: False

    error_caught = []

    def on_sync_finished(success, msg):
        worker.is_running = False
        error_caught.append((success, msg))

    worker.sync_finished.connect(on_sync_finished)
    worker.run()

    assert len(error_caught) > 0
    success, msg = error_caught[0]
    assert success is False
    assert "No Internet Connection" in msg


def test_auto_heal_invalid_branch(tmp_path):
    db_path = str(tmp_path / "heal_test.db")
    session = init_db(f"sqlite:///{db_path}")

    sale = Sale(
        local_sale_id="000601254763",
        doc_number="000601254763",
        branch_id=6,
        status="failed",
        idempotency_key="test-sale-000601254763",
        sync_error='{"message": "The selected branch id is invalid."}',
    )
    payload = {"branch_id": 6, "shift_id": 1, "items": []}
    outbox = Outbox(
        aggregate_id="000601254763",
        event_type="sale_checkout",
        idempotency_key="test-key-000601254763",
        payload_json=json.dumps(payload),
        status="failed",
        last_error="The selected branch id is invalid.",
        payload_prepared=True,
    )
    session.add(sale)
    session.add(outbox)
    session.commit()
    session.close()

    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    worker._resolve_branch_and_cashier = lambda sess: (34, 173)

    class MockShiftResponse:
        status_code = 200

        def json(self):
            return {"shift": {"id": 99, "branch_id": 34, "cashier_id": 173}}

        def raise_for_status(self):
            pass

    class MockCheckoutResponse:
        status_code = 200

        def json(self):
            return {"status": "success", "receipt_id": 500, "receipt_no": "REC-001"}

        def raise_for_status(self):
            pass

    with mock.patch("requests.get", return_value=MockShiftResponse()), \
         mock.patch("requests.post", return_value=MockCheckoutResponse()):
        ok, _ = worker._sync_outbox_sales()
        assert ok is True

    session = init_db(f"sqlite:///{db_path}")
    healed_outbox = session.query(Outbox).filter_by(aggregate_id="000601254763").first()
    healed_sale = session.query(Sale).filter_by(local_sale_id="000601254763").first()
    assert healed_outbox.status == "synced"
    assert healed_sale.status == "synced"
    assert healed_sale.branch_id == 34
    assert healed_sale.shift_id == 99
    healed_payload = json.loads(healed_outbox.payload_json)
    assert healed_payload["branch_id"] == 34
    assert healed_payload["shift_id"] == 99
    session.close()


def test_discount_70_minus_10_retry_after_first_request_fails_preserves_discount_and_receipt_payment(tmp_path):
    """
    เทสต์กรณีขาย 70 ลด 10 (ใบเสร็จสุทธิ 60 รับเงินสดจริง 60)
    ซิงก์ครั้งแรกไม่สำเร็จ (เน็ตหลุด/timeout) แล้วซิงก์ใหม่ในรอบถัดไป:
    - ต้องส่ง manual_discount_amount = 10.0 พร้อม discount_approved_by ไป ERP ให้ครบ
    - ตอน retry ห้ามเปลี่ยนราคาสินค้ากลับเป็นราคาเต็มอื่น และห้ามล้างส่วนลดเป็น 0
    - ยอดก่อนลด 70 ส่วนลด 10 สุทธิ 60 และยอดรับเงินจริง (60) ตรงกับใบเสร็จ
    """
    db_path = str(tmp_path / "discount_retry_70_10.db")
    session = init_db(f"sqlite:///{db_path}")

    prod = Product(
        id=35801,
        sku_code="104150",
        barcode="104150",
        name_th="สินค้าทดสอบ 70 บาท",
        default_price=70.0,
        pos_price=70.0,
        is_active=True,
    )
    sale = Sale(
        local_sale_id="sale-70-disc-10",
        doc_number="003401254878",
        branch_id=34,
        shift_id=13,
        cashier_salesman_id=173,
        total_amount=60.0,
        received_amount=60.0,
        discount_amount=10.0,
        cash_amount=60.0,
        transfer_amount=0.0,
        payment_method="cash",
        idempotency_key="offline-receipt-sale-70-disc-10",
        status="pending",
    )
    sale_item = SaleItem(
        sale_id="sale-70-disc-10",
        product_id=35801,
        sku_code="104150",
        name="สินค้าทดสอบ 70 บาท",
        qty=1.0,
        unit_price=70.0,
        total_price=70.0,
    )
    payment = Payment(
        sale_id="sale-70-disc-10",
        method="cash",
        amount=60.0,
        received_amount=60.0,
        change_amount=0.0,
    )
    payload = {
        "local_sale_id": "sale-70-disc-10",
        "branch_id": 34,
        "shift_id": 13,
        "cashier_id": 173,
        "method": "cash",
        "payment_confirmed": True,
        "cash_received": 60.0,
        "cash_amount": 60.0,
        "transfer_amount": 0.0,
        "change_amount": 0.0,
        "discount_amount": 10.0,
        "manual_discount_amount": 10.0,
        "discount_approved_by": 99,
        "is_offline_sync": True,
        "items": [{"product_id": 35801, "qty": 1.0, "unit_price": 70.0}],
    }
    outbox = Outbox(
        aggregate_id="sale-70-disc-10",
        event_type="sale_checkout",
        idempotency_key="offline-receipt-sale-70-disc-10",
        payload_json=json.dumps(payload),
        status="pending",
        payload_prepared=False,
    )
    session.add_all([prod, sale, sale_item, payment, outbox])
    session.commit()
    session.close()

    worker = SyncWorker(
        db_path,
        "http://localhost:8000",
        "test_token",
        config={"branch_id": 34, "cashier_id": 173, "user_id": 99},
    )
    worker._resolve_branch_and_cashier = lambda sess: (34, 173)

    class MockShiftResponse:
        status_code = 200

        def json(self):
            return {"shift": {"id": 13, "branch_id": 34, "cashier_id": 173, "cashier_user_id": 99}}

        def raise_for_status(self):
            pass

    class MockCheckoutSuccessResponse:
        status_code = 200
        text = '{"success": true, "receipt_id": 501, "receipt_no": "CSB00120261031099", "total_amount": 60.0}'

        def json(self):
            return {
                "success": True,
                "receipt_id": 501,
                "receipt_no": "CSB00120261031099",
                "total_amount": 60.0,
            }

        def raise_for_status(self):
            pass

    posted_payloads = []
    attempt = {"count": 0}

    def mock_post_first_fails_second_succeeds(url, json=None, headers=None, timeout=None):
        attempt["count"] += 1
        posted_payloads.append(json)
        if attempt["count"] == 1:
            raise requests.ConnectionError("Simulated network failure on first checkout request")
        return MockCheckoutSuccessResponse()

    with mock.patch("requests.get", return_value=MockShiftResponse()), \
         mock.patch("requests.post", side_effect=mock_post_first_fails_second_succeeds):
        ok1, _ = worker._sync_outbox_sales()
        assert ok1 is False

        ok2, _ = worker._sync_outbox_sales()
        assert ok2 is True

    assert len(posted_payloads) == 2
    for sent in posted_payloads:
        gross = sum(float(i["qty"]) * float(i["unit_price"]) for i in sent["items"])
        discount = float(sent["manual_discount_amount"])
        net = gross - discount
        assert gross == 70.0
        assert sent["manual_discount_amount"] == 10.0
        assert sent["discount_amount"] == 10.0
        assert sent["discount_approved_by"] == 99
        assert net == 60.0
        assert sent["cash_received"] == 60.0
        assert sent["cash_amount"] == 60.0
        assert sent["change_amount"] == 0.0

    session = init_db(f"sqlite:///{db_path}")
    synced_sale = session.query(Sale).filter_by(local_sale_id="sale-70-disc-10").first()
    synced_outbox = session.query(Outbox).filter_by(aggregate_id="sale-70-disc-10").first()
    assert synced_sale.status == "synced"
    assert synced_sale.total_amount == 60.0
    assert synced_sale.discount_amount == 10.0
    assert synced_sale.received_amount == 60.0
    assert synced_outbox.status == "synced"
    session.close()


def test_discount_or_approval_failure_holds_bill_for_inspection_and_never_sends_full_price(tmp_path):
    """
    ถ้าส่งส่วนลดหรือสิทธิ์อนุมัติไม่ผ่าน ให้พักบิลไว้ตรวจสอบ ห้ามส่งบิลราคาเต็มแทน
    """
    db_path = str(tmp_path / "discount_hold.db")
    session = init_db(f"sqlite:///{db_path}")

    prod = Product(
        id=35801,
        sku_code="104150",
        barcode="104150",
        name_th="สินค้าทดสอบ 70 บาท",
        default_price=70.0,
        pos_price=70.0,
        is_active=True,
    )
    sale = Sale(
        local_sale_id="sale-hold-1",
        doc_number="003401254879",
        branch_id=34,
        total_amount=60.0,
        received_amount=60.0,
        discount_amount=10.0,
        payment_method="cash",
        idempotency_key="offline-receipt-sale-hold-1",
        status="pending",
    )
    payload = {
        "local_sale_id": "sale-hold-1",
        "branch_id": 34,
        "shift_id": 13,
        "cashier_id": 173,
        "method": "cash",
        "cash_received": 60.0,
        "cash_amount": 60.0,
        "change_amount": 0.0,
        "discount_amount": 10.0,
        "manual_discount_amount": 10.0,
        "discount_approved_by": 999999,
        "items": [{"product_id": 35801, "qty": 1.0, "unit_price": 70.0}],
    }
    outbox = Outbox(
        aggregate_id="sale-hold-1",
        event_type="sale_checkout",
        idempotency_key="offline-receipt-sale-hold-1",
        payload_json=json.dumps(payload),
        status="pending",
        payload_prepared=True,
    )
    session.add_all([prod, sale, outbox])
    session.commit()
    session.close()

    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    worker._resolve_branch_and_cashier = lambda sess: (34, 173)

    class MockShiftResponse:
        status_code = 200

        def json(self):
            return {"shift": {"id": 13, "branch_id": 34, "cashier_id": 173}}

        def raise_for_status(self):
            pass

    class MockRejectedResponse:
        status_code = 422
        text = '{"success": false, "message": "ส่วนลดพิเศษต้องให้ผู้จัดการที่มีสิทธิ์อนุมัติ"}'

        def json(self):
            return {"success": False, "message": "ส่วนลดพิเศษต้องให้ผู้จัดการที่มีสิทธิ์อนุมัติ"}

    posted_payloads = []

    def mock_post(url, json=None, headers=None, timeout=None):
        posted_payloads.append(json)
        return MockRejectedResponse()

    with mock.patch("requests.get", return_value=MockShiftResponse()), \
         mock.patch("requests.post", side_effect=mock_post):
        ok1, _ = worker._sync_outbox_sales()
        assert ok1 is False

        ok2, _ = worker._sync_outbox_sales()
        assert ok2 is False

    assert len(posted_payloads) == 1
    assert posted_payloads[0]["manual_discount_amount"] == 10.0
    assert posted_payloads[0]["discount_amount"] == 10.0
    assert posted_payloads[0]["cash_received"] == 60.0

    session = init_db(f"sqlite:///{db_path}")
    held_outbox = session.query(Outbox).filter_by(aggregate_id="sale-hold-1").first()
    held_sale = session.query(Sale).filter_by(local_sale_id="sale-hold-1").first()
    held_payload = json.loads(held_outbox.payload_json)
    assert held_outbox.status == "failed"
    assert held_sale.status == "failed"
    assert held_payload.get("held_for_discount_review") is True
    assert held_payload["manual_discount_amount"] == 10.0
    assert held_payload["discount_amount"] == 10.0
    assert held_payload["cash_received"] == 60.0
    assert held_payload["items"][0]["unit_price"] == 70.0
    session.close()


def test_offline_shift_close_sync(tmp_path):
    db_path = str(tmp_path / 'shift_close_test.db')
    session = init_db(f'sqlite:///{db_path}')

    shift = PosShift(
        server_id=6,
        branch_id=6,
        cashier_id=21,
        opening_cash=500.0,
        expected_cash=595.0,
        counted_cash=595.0,
        status='closed',
        sync_status='pending',
    )
    session.add(shift)
    session.flush()
    shift_local_id = shift.id

    outbox = Outbox(
        event_type='shift_close',
        aggregate_id='6',
        idempotency_key='shift-close-6-12345',
        payload_json=json.dumps({
            'shift_id': 6,
            'local_shift_id': shift_local_id,
            'counted_cash': 595.0,
            'closing_note': 'ปิดกะออฟไลน์ (Auto-sync)',
        }),
        status='pending',
    )
    session.add(outbox)
    session.commit()
    outbox_id = outbox.id
    session.close()

    worker = SyncWorker(db_path, 'http://localhost:8000', 'test_token')
    assert worker.get_pending_count() == 1

    posted_urls = []
    posted_bodies = []

    class MockCloseResponse:
        status_code = 200
        text = '{"success": true}'

        def json(self):
            return {'success': True, 'shift': {'id': 6, 'status': 'closed'}}

    def mock_post(url, json=None, headers=None, timeout=None):
        posted_urls.append(url)
        posted_bodies.append(json)
        return MockCloseResponse()

    with mock.patch('requests.post', side_effect=mock_post):
        ok, _ = worker._sync_outbox_sales()
        assert ok is True

    assert any('/api/pos/shift/close' in url for url in posted_urls)
    close_req = next(body for body in posted_bodies if body.get('shift_id') == 6)
    assert close_req['counted_cash'] == 595.0

    session = init_db(f'sqlite:///{db_path}')
    updated_shift = session.query(PosShift).filter_by(id=shift_local_id).first()
    updated_outbox = session.query(Outbox).filter_by(id=outbox_id).first()
    assert updated_shift.sync_status == 'synced'
    assert updated_outbox.status == 'synced'
    assert worker.get_pending_count() == 0
    session.close()
