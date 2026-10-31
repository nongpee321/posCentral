import json
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from database.models import init_db, Product, QtyPromotion, Sale, Outbox
from services.promotion_engine import evaluate_promotions, get_active_promotions_for_product
from ui.main_window import MainWindow
import sync_worker as sync_worker_module
from sync_worker import SyncWorker


@pytest.fixture(autouse=True)
def mock_msgbox(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)


def test_evaluate_bundle_price_3_packs_100(tmp_path):
    db_path = str(tmp_path / "promo_test.db")
    session = init_db(f"sqlite:///{db_path}")

    prod = Product(
        id=101,
        sku_code="PORK-PACK-01",
        barcode="8850001001",
        name_th="หมูบดแพ็คเกจ",
        default_price=35.0,
        is_active=True,
    )
    promo = QtyPromotion(
        id=1,
        code="PROMO-PORK3-100",
        name="หมูบด 3 แพ็ค 100",
        promo_type="bundle_price",
        product_id=101,
        min_qty=3.0,
        bundle_price=100.0,
        is_active=True,
    )
    session.add_all([prod, promo])
    session.commit()

    # 1 pack: no promo (35.00)
    disc1, details1 = evaluate_promotions(session, [{'product_id': 101, 'qty': 1, 'unit_price': 35.0}])
    assert disc1 == 0.0
    assert len(details1) == 0

    # 3 packs: 3 x 35 = 105 -> bundle 100 -> discount 5.00
    disc3, details3 = evaluate_promotions(session, [{'product_id': 101, 'qty': 3, 'unit_price': 35.0}])
    assert disc3 == 5.0
    assert len(details3) == 1
    assert details3[0]['sets'] == 1
    assert details3[0]['discount'] == 5.0

    # 6 packs: 2 sets x 100 = 200 (normal 210) -> discount 10.00
    disc6, details6 = evaluate_promotions(session, [{'product_id': 101, 'qty': 6, 'unit_price': 35.0}])
    assert disc6 == 10.0
    assert details6[0]['sets'] == 2

    # 7 packs: 2 sets x 100 + 1 x 35 = 235 (normal 245) -> discount 10.00
    disc7, details7 = evaluate_promotions(session, [{'product_id': 101, 'qty': 7, 'unit_price': 35.0}])
    assert disc7 == 10.0

    session.close()


def test_evaluate_buy_2_get_1_free(tmp_path):
    db_path = str(tmp_path / "bogo_test.db")
    session = init_db(f"sqlite:///{db_path}")

    prod = Product(
        id=202,
        sku_code="CHICKEN-PACK",
        barcode="8850002002",
        name_th="อกไก่แพ็ค",
        default_price=40.0,
        is_active=True,
    )
    promo = QtyPromotion(
        id=2,
        code="PROMO-CHICKEN-2FREE1",
        name="ซื้อ 2 แถม 1",
        promo_type="free_item",
        product_id=202,
        min_qty=2.0,
        free_product_id=202,
        free_qty=1.0,
        is_active=True,
    )
    session.add_all([prod, promo])
    session.commit()

    # Buy 3 in cart: 2 bought + 1 free -> free 1 x 40 = 40.00 discount
    disc, details = evaluate_promotions(session, [{'product_id': 202, 'qty': 3, 'unit_price': 40.0}])
    assert disc == 40.0
    assert details[0]['sets'] == 1

    session.close()


def test_main_window_auto_promotion_flow(qtbot, tmp_path):
    db_path = str(tmp_path / "pos_gui_promo.db")
    session = init_db(f"sqlite:///{db_path}")

    pork = Product(
        id=50,
        sku_code="PORK-50",
        barcode="8850005001",
        name_th="หมูสามชั้นแพ็ค",
        default_price=35.0,
        pos_price=35.0,
        is_active=True,
        stock_qty=100.0,
    )
    promo = QtyPromotion(
        id=10,
        code="PORK-3-100",
        name="3 แพ็ค 100 บาท",
        promo_type="bundle_price",
        product_id=50,
        min_qty=3.0,
        bundle_price=100.0,
        is_active=True,
    )
    session.add_all([pork, promo])
    session.commit()
    session.close()

    win = MainWindow(db_path=db_path)
    qtbot.addWidget(win)
    win.config = {
        'api_url': 'http://erp.example',
        'pos_token': 'dummy',
        'branch_id': 1,
        'cashier_id': 1,
    }
    win.current_shift = {'id': 999, 'local_id': 1, 'branch_id': 1}
    win.cart_table.setRowCount(0)

    # 1. Add 2 packs (subtotal 70, no promo)
    p_data = {
        'id': 50,
        'sku_code': 'PORK-50',
        'name_th': 'หมูสามชั้นแพ็ค',
        'default_price': 35.0,
        'pos_price': 35.0,
        'stock_qty': 100.0,
        'is_scale_item': False,
    }
    win.handle_product_click(p_data)
    win.handle_product_click(p_data)

    assert win.promo_discount_amount == 0.0
    assert win.promo_container.isHidden()
    assert win.total_val.text() == "฿70.00"

    # 2. Add 3rd pack (subtotal 105, triggers 3 for 100 promo -> -5.00 discount)
    win.handle_product_click(p_data)

    assert win.promo_discount_amount == 5.0
    assert not win.promo_container.isHidden()
    assert "โปรโมชั่น" in win.promo_title_lbl.text()
    assert win.promo_val.text() == "-฿5.00"
    assert win.subtotal_val.text() == "฿105.00"
    assert win.total_val.text() == "฿100.00"

    # 3. Verify totals computation
    totals = win._compute_rounded_totals(105.0, win.promo_discount_amount)
    assert totals['subtotal'] == 105.0
    assert totals['promo_discount'] == 5.0
    assert totals['manual_discount'] == 0.0
    assert totals['total_discount'] == 5.0
    assert totals['grand_total'] == 100.0

    win.close()


def test_sync_worker_promotions_sync(tmp_path, monkeypatch):
    db_path = str(tmp_path / "sync_promo.db")
    session = init_db(f"sqlite:///{db_path}")
    session.close()

    class FakePromoResp:
        status_code = 200

        def json(self):
            return [
                {
                    "id": 88,
                    "code": "PROMO-B3P100",
                    "name": "หมู 3 แพ็ค 100",
                    "promo_type": "bundle_price",
                    "product_id": 999,
                    "min_qty": 3.0,
                    "bundle_price": 100.0,
                    "free_product_id": None,
                    "free_qty": 0.0,
                    "discount_type": None,
                    "discount_value": 0.0,
                    "branch_id": None,
                }
            ]

    monkeypatch.setattr(
        sync_worker_module.requests,
        "get",
        lambda *args, **kwargs: FakePromoResp(),
    )

    worker = SyncWorker(db_path, "http://erp.example", "test-token")
    session = init_db(f"sqlite:///{db_path}")
    worker._sync_promotions(session, headers={'Authorization': 'Bearer test'})
    session.close()

    # Verify promo was saved to SQLite
    session = init_db(f"sqlite:///{db_path}")
    promos = session.query(QtyPromotion).all()
    assert len(promos) == 1
    assert promos[0].code == "PROMO-B3P100"
    assert promos[0].bundle_price == 100.0
    assert promos[0].min_qty == 3.0
    session.close()


def test_auto_promotion_checkout_outbox_payload(qtbot, tmp_path, monkeypatch):
    db_path = str(tmp_path / "checkout_promo.db")
    session = init_db(f"sqlite:///{db_path}")

    pork = Product(
        id=77,
        sku_code="PORK-77",
        barcode="8850007700",
        name_th="หมูสไลซ์แพ็ค",
        default_price=35.0,
        pos_price=35.0,
        is_active=True,
        stock_qty=100.0,
    )
    promo = QtyPromotion(
        id=15,
        code="PORK-3-100",
        name="หมูสไลซ์ 3 แพ็ค 100",
        promo_type="bundle_price",
        product_id=77,
        min_qty=3.0,
        bundle_price=100.0,
        is_active=True,
    )
    session.add_all([pork, promo])
    session.commit()
    session.close()

    win = MainWindow(db_path=db_path)
    qtbot.addWidget(win)
    win.config = {
        'api_url': 'http://erp.example',
        'pos_token': 'dummy',
        'branch_id': 1,
        'cashier_id': 1,
        'device_id': 'DEV-TEST',
    }
    win.current_shift = {'id': 101, 'local_id': 1, 'branch_id': 1, 'cashier_id': 1}
    win.cart_table.setRowCount(0)

    p_data = {
        'id': 77,
        'sku_code': 'PORK-77',
        'name_th': 'หมูสไลซ์แพ็ค',
        'default_price': 35.0,
        'pos_price': 35.0,
        'stock_qty': 100.0,
        'is_scale_item': False,
    }
    # Add 3 packs
    win.handle_product_click(p_data)
    win.handle_product_click(p_data)
    win.handle_product_click(p_data)

    assert win.promo_discount_amount == 5.0
    assert win.total_val.text() == "฿100.00"

    # Mock receipt dialog so it doesn't block
    from ui.receipt_dialog import ReceiptDialog
    monkeypatch.setattr(ReceiptDialog, "exec", lambda self: None)

    # Process cash payment 100.00
    win.process_payment('cash', 100.0, 100.0, 0.0)

    session = init_db(f"sqlite:///{db_path}")
    sale = session.query(Sale).one()
    assert sale.total_amount == 100.0
    assert sale.discount_amount == 5.0

    outbox = session.query(Outbox).filter(Outbox.event_type == 'sale_checkout').one()
    payload = json.loads(outbox.payload_json)
    assert payload['discount_amount'] == 5.0
    assert payload['manual_discount_amount'] == 0.0
    assert payload['promo_discount_amount'] == 5.0
    assert payload['discount_approved_by'] is None
    assert payload['cash_received'] == 100.0
    assert len(payload['items']) == 1
    assert payload['items'][0]['qty'] == 3.0
    assert payload['items'][0]['unit_price'] == 35.0
    session.close()
    win.close()
