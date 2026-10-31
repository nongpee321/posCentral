import pytest
from sync_worker import SyncWorker
from database.models import init_db

def test_sync_worker_offline_detection(tmp_path):
    db_path = str(tmp_path / "sync_test.db")
    init_db(f"sqlite:///{db_path}")
    
    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    
    # We want to test that if _check_internet returns False, it raises the exception
    # Instead of running the thread, we can call run() and let it hit the exception 
    # Or just test _check_internet directly.
    # To avoid infinite loop in run(), we will mock is_running to turn false after one loop.
    
    # Let's mock _check_internet to return False
    worker._check_internet = lambda: False
    
    error_caught = []
    
    def on_sync_finished(success, msg):
        worker.is_running = False # stop loop
        error_caught.append((success, msg))
        
    worker.sync_finished.connect(on_sync_finished)
    
    # Call run directly (synchronously) for testing
    worker.run()
    
    assert len(error_caught) > 0
    success, msg = error_caught[0]
    assert success is False
    assert "No Internet Connection" in msg


def test_auto_heal_invalid_branch(tmp_path):
    import json
    from database.models import Sale, Outbox
    db_path = str(tmp_path / "heal_test.db")
    session = init_db(f"sqlite:///{db_path}")

    # Create a pending sale and outbox entry with old branch 6
    sale = Sale(
        local_sale_id="000601254763",
        doc_number="000601254763",
        branch_id=6,
        status="failed",
        idempotency_key="test-sale-000601254763",
        sync_error='{"message": "The selected branch id is invalid."}'
    )
    payload = {"branch_id": 6, "shift_id": 1, "items": []}
    outbox = Outbox(
        aggregate_id="000601254763",
        event_type="sale_checkout",
        idempotency_key="test-key-000601254763",
        payload_json=json.dumps(payload),
        status="failed",
        last_error="The selected branch id is invalid.",
        payload_prepared=True
    )
    session.add(sale)
    session.add(outbox)
    session.commit()
    session.close()

    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    # Simulate resolving branch 34 and shift 99
    worker._resolve_branch_and_cashier = lambda sess: (34, 173)

    # Mock requests.get for active shift
    class MockShiftResponse:
        status_code = 200
        def json(self):
            return {"shift": {"id": 99, "branch_id": 34, "cashier_id": 173}}
        def raise_for_status(self):
            pass

    # Mock requests.post for checkout
    class MockCheckoutResponse:
        status_code = 200
        def json(self):
            return {"status": "success", "receipt_id": 500, "receipt_no": "REC-001"}
        def raise_for_status(self):
            pass

    import unittest.mock as mock
    with mock.patch("requests.get", return_value=MockShiftResponse()), \
         mock.patch("requests.post", return_value=MockCheckoutResponse()):
        ok, msg = worker._sync_outbox_sales()
        assert ok is True

    # Verify that payload and sale were healed to branch 34, shift 99
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


def test_auto_heal_discount_fields(tmp_path):
    import json
    from database.models import Sale, Outbox, Product
    db_path = str(tmp_path / "discount_heal.db")
    session = init_db(f"sqlite:///{db_path}")

    prod = Product(
        id=35801,
        sku_code="104150",
        barcode="104150",
        name_th="Test Chicken",
        default_price=110.0,
        pos_price=110.0,
        is_active=True
    )
    sale = Sale(
        local_sale_id="sale-disc-1",
        doc_number="003401254878",
        branch_id=34,
        total_amount=100.0,
        received_amount=100.0,
        payment_method="cash",
        idempotency_key="offline-receipt-sale-disc-1",
        status="failed",
        sync_error="ราคาหรือส่วนลดเปลี่ยนจากข้อมูลบนเซิร์ฟเวอร์"
    )
    payload = {
        "local_sale_id": "sale-disc-1",
        "branch_id": 34,
        "shift_id": 13,
        "cashier_id": 173,
        "method": "cash",
        "cash_received": 100.0,
        "change_amount": 0.0,
        "discount_amount": 0.0,
        "manual_discount_amount": 0.0,
        "items": [{"product_id": 35801, "qty": 1.0, "unit_price": 100.0}]
    }
    outbox = Outbox(
        aggregate_id="sale-disc-1",
        event_type="sale_checkout",
        idempotency_key="offline-receipt-sale-disc-1",
        payload_json=json.dumps(payload),
        status="failed",
        last_error="ราคาหรือส่วนลดเปลี่ยนจากข้อมูลบนเซิร์ฟเวอร์",
        payload_prepared=True
    )
    session.add(prod)
    session.add(sale)
    session.add(outbox)
    session.commit()
    session.close()

    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    worker._resolve_branch_and_cashier = lambda sess: (34, 173)

    posted_payloads = []
    class MockCheckoutResponse:
        status_code = 200
        def json(self):
            return {"status": "success", "receipt_id": 501, "receipt_no": "REC-002"}
        def raise_for_status(self):
            pass

    def mock_post(url, json=None, headers=None, timeout=None):
        posted_payloads.append(json)
        return MockCheckoutResponse()

    class MockShiftResponse:
        status_code = 200
        def json(self):
            return {"shift": {"id": 13, "branch_id": 34, "cashier_id": 173}}
        def raise_for_status(self):
            pass

    import unittest.mock as mock
    with mock.patch("requests.get", return_value=MockShiftResponse()), \
         mock.patch("requests.post", side_effect=mock_post):
        ok, msg = worker._sync_outbox_sales()
        assert ok is True

    assert len(posted_payloads) == 1
    sent = posted_payloads[0]
    # Unit price restored to catalog 110.0
    assert sent["items"][0]["unit_price"] == 110.0
    # manual_discount_amount must be 0.0 so manager approval is never required
    assert sent["manual_discount_amount"] == 0.0
    # discount_amount equals discount (110 - 100 = 10)
    assert sent["discount_amount"] == 10.0
    # cash_received equals gross total 110.0
    assert sent["cash_received"] == 110.0
    # change_amount equals 10.0
    assert sent["change_amount"] == 10.0

def test_offline_shift_close_sync(tmp_path):
    import json
    from database.models import PosShift, Outbox
    import unittest.mock as mock

    db_path = str(tmp_path / 'shift_close_test.db')
    session = init_db(f'sqlite:///{db_path}')

    # Create an offline closed shift
    shift = PosShift(
        server_id=6,
        branch_id=6,
        cashier_id=21,
        opening_cash=500.0,
        expected_cash=595.0,
        counted_cash=595.0,
        status='closed',
        sync_status='pending'
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
            'closing_note': 'ปิดกะออฟไลน์ (Auto-sync)'
        }),
        status='pending'
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
        ok, msg = worker._sync_outbox_sales()
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
