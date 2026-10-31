import os
import pytest
from PySide6.QtWidgets import QApplication, QDialog
from ui.scale_weight_dialog import ScaleWeightDialog, is_scale_product
from database.models import init_db, Product

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_is_scale_product_detection():
    # 1. Scale product samples
    assert is_scale_product({"name_th": "คอต่อหมู (ชั่งน้ำหนัก)", "sku_code": "2990000000064"}) is True
    assert is_scale_product({"name_th": "เนื้อหมูสด (กก.)", "sku_code": "00123"}) is True
    assert is_scale_product({"name_th": "น่องไก่ติดสะโพก", "sku_code": "800101"}) is True
    assert is_scale_product({"name_th": "หมูบด", "is_scale_item": True}) is True
    assert is_scale_product({"name_th": "หมูบด", "unit": "กก."}) is True

    # 2. Non-scale product samples (piece-rate / retail)
    assert is_scale_product({"name_th": "ถุงใส PP-45 (50ใบ*18แพ็ค)", "sku_code": "100234"}) is False
    assert is_scale_product({"name_th": "น้ำดื่มสิงห์ 600ml", "sku_code": "8850999001"}) is False
    assert is_scale_product({"name_th": "กระดาษชำระ", "sku_code": "999999"}) is False
    assert is_scale_product(None) is False

def test_scale_weight_dialog_filters_only_scale_items(qapp, tmp_path):
    test_db = str(tmp_path / "test_scale.db")
    session = init_db(f"sqlite:///{test_db}")
    
    # Add 1 scale item and 2 non-scale items
    p_scale = Product(
        sku_code="SKU-SCALE-01",
        name_th="เนื้อหมูสันนอก (ชั่งน้ำหนัก)",
        default_price=150.0,
        is_active=True,
        is_scale_item=True
    )
    p_retail1 = Product(
        sku_code="SKU-RETAIL-01",
        name_th="ถุงหูหิ้วใส PP",
        default_price=25.0,
        is_active=True,
        is_scale_item=False
    )
    p_retail2 = Product(
        sku_code="SKU-RETAIL-02",
        name_th="น้ำอัดลม 1.5 ลิตร",
        default_price=30.0,
        is_active=True,
        is_scale_item=False
    )
    session.add_all([p_scale, p_retail1, p_retail2])
    session.commit()
    session.close()

    dlg = ScaleWeightDialog(db_path=test_db)
    
    # Check that ONLY the scale item was loaded into products_list and combo
    assert len(dlg.products_list) == 1
    assert dlg.products_list[0].sku_code == "SKU-SCALE-01"
    assert dlg.prod_combo.count() == 1
    assert "เนื้อหมูสันนอก" in dlg.prod_combo.itemText(0)
    
    # Test entering valid weight
    dlg.weight_input.setValue(1.500)
    dlg.on_submit()
    assert dlg.result() == QDialog.Accepted
    assert dlg.entered_weight == 1.500
