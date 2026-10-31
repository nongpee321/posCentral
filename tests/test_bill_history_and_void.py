import pytest
from datetime import datetime
from PySide6.QtWidgets import QApplication
from database.models import init_db, Sale, SaleItem, Outbox
from ui.bill_history_dialog import BillHistoryDialog

app = QApplication.instance() or QApplication([])

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_history.db")
    session = init_db(f"sqlite:///{db_file}")

    # Seed sales
    sale1 = Sale(
        local_sale_id="sale-001",
        doc_number="CSB00120261031001",
        total_amount=550.0,
        received_amount=600.0,
        discount_amount=100.0,
        payment_method="cash",
        status="synced",
        idempotency_key="key-001",
        created_at=datetime(2026, 10, 31, 15, 28, 0)
    )
    item1 = SaleItem(
        sale_id="sale-001",
        product_id=10,
        sku_code="SKU-CARDIGAN",
        name="BL(เบอร์#2) คาร์ดิแกน",
        qty=1.0,
        unit_price=650.0,
        total_price=650.0
    )

    sale2 = Sale(
        local_sale_id="sale-002",
        doc_number="CSB00120261031002",
        total_amount=300.0,
        received_amount=300.0,
        discount_amount=0.0,
        payment_method="transfer",
        status="pending",
        idempotency_key="key-002",
        created_at=datetime(2026, 10, 31, 16, 0, 0)
    )
    item2 = SaleItem(
        sale_id="sale-002",
        product_id=20,
        sku_code="SKU-SHIRT",
        name="เสื้อเชิ้ตขาว",
        qty=1.0,
        unit_price=300.0,
        total_price=300.0
    )

    outbox2 = Outbox(
        event_type="sale_checkout",
        aggregate_id="sale-002",
        payload_json='{"local_sale_id": "sale-002"}',
        idempotency_key="key-002",
        status="pending"
    )

    session.add_all([sale1, item1, sale2, item2, outbox2])
    session.commit()
    session.close()

    return db_file

def test_bill_history_dialog_listing_and_filtering(qtbot, test_db):
    dlg = BillHistoryDialog(db_path=test_db, config={})
    qtbot.addWidget(dlg)

    # Both sales should be loaded
    assert dlg.sales_table.rowCount() == 2
    assert dlg.sales_table.item(0, 0).text() == "CSB00120261031002"
    assert dlg.sales_table.item(1, 0).text() == "CSB00120261031001"

    # Discount check on row 1 (sale-001): -฿100.00
    assert dlg.sales_table.item(1, 4).text() == "-฿100.00"
    assert dlg.sales_table.item(1, 5).text() == "฿550.00"

    # Filter search
    dlg.search_input.setText("CSB00120261031001")
    assert dlg.sales_table.rowCount() == 1
    assert dlg.sales_table.item(0, 0).text() == "CSB00120261031001"

    dlg.search_input.setText("")
    assert dlg.sales_table.rowCount() == 2

def test_bill_selection_and_details(qtbot, test_db):
    dlg = BillHistoryDialog(db_path=test_db, config={})
    qtbot.addWidget(dlg)

    # Select sale-001 (row 1)
    dlg.sales_table.selectRow(1)
    assert dlg.selected_sale is not None
    assert dlg.selected_sale['doc_number'] == "CSB00120261031001"
    assert dlg.items_table.rowCount() == 1
    assert "คาร์ดิแกน" in dlg.items_table.item(0, 0).text()
    assert dlg.reprint_btn.isEnabled()
    assert dlg.edit_btn.isEnabled()
    assert dlg.void_btn.isEnabled()

def test_void_pending_sale_locally(qtbot, test_db):
    dlg = BillHistoryDialog(db_path=test_db, config={})
    qtbot.addWidget(dlg)

    sale_data = dlg.all_sales[0] # sale-002 (pending)
    success = dlg._execute_void(sale_data, "ลูกค้าคีย์ผิด")
    assert success is True

    session = init_db(f"sqlite:///{test_db}")
    s2 = session.query(Sale).filter_by(local_sale_id="sale-002").first()
    assert s2.status == "cancelled"

    ob2 = session.query(Outbox).filter_by(aggregate_id="sale-002").first()
    assert ob2.status == "cancelled"
    session.close()

def test_load_bill_into_cart_mock(qtbot, monkeypatch, test_db):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    class MockMainWindow:
        def __init__(self):
            from PySide6.QtWidgets import QTableWidget
            self.cart_table = QTableWidget(0, 5)
            self.discount_amount = 0.0
            self.discount_label = ""
            self.discount_approved_by = None
            self.config = {}

        def update_cart_total(self):
            pass

        def _resolve_discount_approver_id(self):
            return 1

        def delete_cart_row(self, r):
            pass

    from ui.main_window import MainWindow
    mock_window = MockMainWindow()

    sale_to_restore = {
        'doc_number': 'CSB00120261031001',
        'discount_amount': 100.0,
        'items': [
            {
                'product_id': 10,
                'name': 'BL(เบอร์#2) คาร์ดิแกน',
                'qty': 1.0,
                'unit_price': 650.0,
                'total_price': 650.0
            }
        ]
    }

    # Call MainWindow.load_bill_into_cart with mock
    MainWindow.load_bill_into_cart(mock_window, sale_to_restore)

    assert mock_window.cart_table.rowCount() == 1
    assert mock_window.cart_table.item(0, 0).text() == "BL(เบอร์#2) คาร์ดิแกน"
    assert mock_window.cart_table.item(0, 1).text() == "1"
    assert mock_window.cart_table.item(0, 2).text() == "650.00"
    assert mock_window.cart_table.item(0, 3).text() == "650.00"
    assert mock_window.discount_amount == 100.0
    assert mock_window.discount_label == "฿100.00"
