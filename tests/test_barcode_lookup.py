import os
import pytest
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from database.models import init_db, Product, ProductBarcode
from services.barcode_lookup import lookup_product, normalize_scan_text
from services.scale_service import ScaleBarcodeParser


def test_normalize_thai_keyboard_and_digits():
    # "0000001043747" typed while Windows keyboard layout is Thai Kedmanee:
    # 0->จ, 1->ๅ, 0->จ, 4->ภ, 3->-, 7->ึ, 4->ภ, 7->ึ
    thai_scan = "จจจจจจๅจภ-ึภึ"
    text, digits = normalize_scan_text(thai_scan)
    assert digits == "0000001043747"


def test_real_catalog_barcodes_and_scale_labels():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pos.db")
    session = init_db(db_path)
    try:
        # 1. Exact 13-digit barcode from product_barcodes (BL(เบอร์#2) คาร์กิลล์, SKU 104374, barcode 0000001043747)
        res = lookup_product(session, "0000001043747", scale_parser=ScaleBarcodeParser)
        assert res["status"] == "found"
        assert res["product"].sku_code == "104374"

        # 2. Scanner dropped leading zeros (1043747 -> 0000001043747)
        res_no_zeros = lookup_product(session, "1043747", scale_parser=ScaleBarcodeParser)
        assert res_no_zeros["status"] == "found"
        assert res_no_zeros["product"].sku_code == "104374"

        # 3. Thai keyboard layout scan of 0000001043747
        res_thai = lookup_product(session, "จจจจจจๅจภ-ึภึ", scale_parser=ScaleBarcodeParser)
        assert res_thai["status"] == "found"
        assert res_thai["product"].sku_code == "104374"

        # 4. 13-digit barcode starting with '20' (must NOT be hijacked by ScaleProfile prefix='20')
        res_20 = lookup_product(session, "2010740000008", scale_parser=ScaleBarcodeParser)
        assert res_20["status"] == "found"
        assert res_20["product"].sku_code == "201074"

        # 5. Trailing-zero 13-digit scan for a 6-digit SKU starting with '20' that only has 6-digit SKU in DB
        res_20_trail = lookup_product(session, "2080010000005", scale_parser=ScaleBarcodeParser)
        assert res_20_trail["status"] == "found"
        assert res_20_trail["product"].sku_code == "208001"

        # 6. POPSTAR 13-digit scale label: 801037 (เป็ดเชอรี่ 110/kg) + 014850 (148.50 Baht) + check digit 1
        res_scale = lookup_product(session, "8010370148501", scale_parser=ScaleBarcodeParser)
        assert res_scale["status"] == "scale"
        assert res_scale["product"].id == 35662
        assert abs(res_scale["scale"]["price"] - 148.50) < 1e-6
        assert abs(res_scale["scale"]["weight"] - 1.35) < 1e-3

        # 7. Internal 299xxxxxxxxxC barcode (299 + 9-digit product.id + check digit)
        res_299 = lookup_product(session, "2990000352029", scale_parser=ScaleBarcodeParser)
        assert res_299["status"] == "found"
        assert res_299["product"].id == 35202
    finally:
        session.close()


def test_scanner_redirect_preserves_first_digit(qapp, tmp_path):
    from ui.main_window import MainWindow

    db_file = tmp_path / "test_scan.db"
    s = init_db(str(db_file))
    s.add(Product(id=1, sku_code="104374", barcode="0000001043747", name_th="BL(#2)", default_price=650.0, pos_price=650.0, is_active=True))
    s.add(ProductBarcode(product_id=1, barcode="0000001043747", barcode_norm="1043747", unit_factor=1.0, price=650.0))
    s.commit()
    s.close()

    win = MainWindow(db_path=str(db_file), is_offline_login=True)
    win.show()
    QApplication.processEvents()
    try:
        win.cart_table.setFocus()
        win.search_input.clear()
        # Simulate first keystroke '8' sent while cart_table has focus
        ev = QKeyEvent(QEvent.KeyPress, Qt.Key_8, Qt.NoModifier, "8")
        win.eventFilter(win.cart_table, ev)
        assert win.search_input.text() == "8"
    finally:
        win.close()
