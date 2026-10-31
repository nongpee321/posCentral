import json
import base64
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import requests
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

import sync_worker as sync_worker_module
from database.models import Outbox, Sale, init_db
from services.offline_auth import verify_offline_login
from sync_worker import SyncWorker
from ui.main_window import MainWindow


def test_offline_login_requires_cached_pin_verifier():
    pin = "1234"
    salt = b"pos-test-salt"
    verifier = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 120000, 32)
    cached_auth = {
        "code": "CASHIER01",
        "credential": {
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(verifier).decode(),
            "iterations": 120000,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    }

    assert verify_offline_login(cached_auth, "cashier01", pin)
    assert not verify_offline_login(cached_auth, "cashier02", pin)
    assert not verify_offline_login(cached_auth, "cashier01", "wrong")
    cached_auth["credential"]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    assert not verify_offline_login(cached_auth, "cashier01", pin)


def test_existing_outbox_database_is_migrated(tmp_path):
    db_path = str(tmp_path / "existing.db")
    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE outbox (
            id INTEGER PRIMARY KEY,
            event_type VARCHAR(50) NOT NULL,
            aggregate_id VARCHAR(50) NOT NULL,
            payload_json TEXT NOT NULL,
            idempotency_key VARCHAR(100) NOT NULL UNIQUE,
            status VARCHAR(20)
        )
    """)
    connection.commit()
    connection.close()

    session = init_db(f"sqlite:///{db_path}")
    session.close()

    connection = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(outbox)")}
        assert "payload_prepared" in columns
    finally:
        connection.close()


def test_checkout_is_saved_before_any_network_request(qtbot, tmp_path, monkeypatch):
    db_path = str(tmp_path / "local_first.db")
    window = MainWindow(db_path=db_path)
    if hasattr(window, 'sync_worker') and window.sync_worker:
        window.sync_worker.is_running = False
        window.sync_worker.wait(500)
    qtbot.addWidget(window)
    window.config.update({
        "api_url": "http://erp.example",
        "pos_token": "test-token",
        "branch_id": 6,
        "cashier_id": 9,
        "cashier_name": "Cashier",
    })
    window.current_shift = {"id": 55, "local_id": 1}
    window.cart_table.setRowCount(1)
    name_item = QTableWidgetItem("Test item")
    name_item.setData(Qt.UserRole, 101)
    window.cart_table.setItem(0, 0, name_item)
    window.cart_table.setItem(0, 1, QTableWidgetItem("1"))
    window.cart_table.setItem(0, 2, QTableWidgetItem("100"))

    class FakeSyncWorker:
        force_sync_called = False

        def force_sync(self):
            self.force_sync_called = True

        def get_pending_count(self):
            return 1

    class FakeReceiptDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return 0

    worker = FakeSyncWorker()
    window.sync_worker = worker

    def reject_checkout_request(*args, **kwargs):
        pytest.fail("checkout must be queued locally before SyncWorker sends it")

    monkeypatch.setattr(sync_worker_module.requests, "post", reject_checkout_request)
    monkeypatch.setattr("ui.receipt_dialog.ReceiptDialog", FakeReceiptDialog)

    window.process_payment("เงินสด", 100, 0, cash_amount=100)

    session = init_db(f"sqlite:///{db_path}")
    try:
        sale = session.query(Sale).one()
        outbox = session.query(Outbox).one()
        payload = json.loads(outbox.payload_json)
        assert sale.status == "pending"
        assert outbox.status == "pending"
        assert outbox.idempotency_key == sale.idempotency_key
        assert outbox.idempotency_key.startswith("offline-receipt-")
        assert payload["items"] == [{"product_id": 101, "qty": 1.0, "unit_price": 100.0}]
    finally:
        session.close()

    assert worker.force_sync_called


def test_retry_reuses_legacy_idempotency_key_and_prepared_payload(tmp_path, monkeypatch):
    db_path = str(tmp_path / "retry.db")
    local_sale_id = "sale-uuid"
    legacy_key = f"pos-sale-{local_sale_id}"
    session = init_db(f"sqlite:///{db_path}")
    session.add(Sale(
        local_sale_id=local_sale_id,
        total_amount=100,
        received_amount=100,
        payment_method="cash",
        idempotency_key=legacy_key,
        status="pending",
    ))
    session.add(Outbox(
        event_type="sale_checkout",
        aggregate_id=local_sale_id,
        payload_json=json.dumps({
            "local_sale_id": local_sale_id,
            "branch_id": 6,
            "shift_id": None,
            "cashier_id": 9,
            "items": [],
        }),
        idempotency_key=legacy_key,
        status="pending",
    ))
    session.commit()
    session.close()

    shift_ids = iter([
        {"id": 55, "branch_id": 6, "cashier_id": 9},
        {"id": 56, "branch_id": 6, "cashier_id": 10},
    ])

    class FakeResponse:
        status_code = 200

        def __init__(self, shift):
            self.shift = shift

        def json(self):
            return {"shift": self.shift}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        sync_worker_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(next(shift_ids)),
    )
    posted_requests = []

    def timeout_post(url, json, headers, timeout):
        posted_requests.append((json.copy(), headers["Idempotency-Key"]))
        raise requests.Timeout("connection lost")

    monkeypatch.setattr(sync_worker_module.requests, "post", timeout_post)
    worker = SyncWorker(db_path, "http://erp.example", "test-token")

    worker._sync_outbox_sales()
    worker._sync_outbox_sales()

    assert posted_requests[0] == posted_requests[1]
    assert posted_requests[0][0]["shift_id"] == 55
    assert posted_requests[0][1] == f"pos-direct-{local_sale_id}"

    session = init_db(f"sqlite:///{db_path}")
    try:
        sale = session.query(Sale).one()
        outbox = session.query(Outbox).one()
        assert sale.idempotency_key == outbox.idempotency_key
        assert outbox.payload_prepared is True
    finally:
        session.close()
