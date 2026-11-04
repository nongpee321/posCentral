import pytest
from PySide6.QtWidgets import QApplication
from ui.promotion_dialog import PromotionListDialog
from database.models import init_db, QtyPromotion, Product


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_promotion_dialog_initialization_and_filtering(qapp, tmp_path):
    db_file = tmp_path / "test_promo.db"
    session = init_db(f"sqlite:///{db_file}")

    # Add dummy product
    prod = Product(
        id=10,
        sku_code="P100",
        name_th="ไก่ทอดกรอบ (กล่อง)",
        barcode="885100",
        default_price=40.0,
        pos_price=40.0,
        is_active=True
    )
    session.add(prod)

    # Add dummy promotions (bundle: 3 packs 100)
    promo1 = QtyPromotion(
        id=1,
        code="PROMO-3-100",
        name="โปรสุดคุ้ม 3 กล่อง 100",
        promo_type="bundle_price",
        product_id=10,
        min_qty=3.0,
        bundle_price=100.0,
        is_active=True
    )
    promo2 = QtyPromotion(
        id=2,
        code="PROMO-DISC-10",
        name="ซื้อ 2 ชิ้นลด 10 บาท",
        promo_type="discount",
        product_id=10,
        min_qty=2.0,
        discount_type="baht",
        discount_value=10.0,
        is_active=True
    )
    session.add_all([promo1, promo2])
    session.commit()
    session.close()

    dlg = PromotionListDialog(
        parent=None,
        db_path=str(db_file),
        branch_name="สาขาอำนาจเจริญ"
    )

    assert "สาขาอำนาจเจริญ" in dlg.windowTitle()
    assert dlg.table.rowCount() == 2

    # Check condition text for bundle
    assert "100.00 บาท" in dlg.table.item(0, 4).text()

    # Filter by type: bundle_price
    idx_bundle = dlg.type_combo.findData("bundle_price")
    assert idx_bundle > 0
    dlg.type_combo.setCurrentIndex(idx_bundle)
    assert dlg.table.isRowHidden(0) is False
    assert dlg.table.isRowHidden(1) is True

    # Filter by type: discount
    idx_disc = dlg.type_combo.findData("discount")
    assert idx_disc > 0
    dlg.type_combo.setCurrentIndex(idx_disc)
    assert dlg.table.isRowHidden(0) is True
    assert dlg.table.isRowHidden(1) is False

    # Search filter
    dlg.type_combo.setCurrentIndex(0)
    dlg.search_input.setText("3 กล่อง")
    assert dlg.table.isRowHidden(0) is False
    assert dlg.table.isRowHidden(1) is True
