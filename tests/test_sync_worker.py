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

