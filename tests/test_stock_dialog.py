import pytest
from PySide6.QtWidgets import QApplication
from ui.stock_dialog import StockCheckDialog
from database.models import init_db, Product, Category


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_stock_dialog_initialization_and_category_filter(qapp, tmp_path):
    db_file = tmp_path / "test_stock.db"
    session = init_db(f"sqlite:///{db_file}")

    # Add dummy categories
    c1 = Category(id=1, name_th="เนื้อหมู", is_active=True)
    c2 = Category(id=2, name_th="เนื้อวัว", is_active=True)
    session.add_all([c1, c2])

    # Add dummy products
    p1 = Product(
        sku_code="101001",
        name_th="เนื้อหมูสันนอก",
        category_id=1,
        barcode="885001",
        default_price=150.0,
        pos_price=150.0,
        stock_qty=12.5,
        is_active=True,
        is_scale_item=True
    )
    p2 = Product(
        sku_code="101002",
        name_th="เนื้อวัวบด",
        category_id=2,
        barcode="885002",
        default_price=220.0,
        pos_price=220.0,
        stock_qty=0.0,
        is_active=True,
        is_scale_item=False
    )
    session.add_all([p1, p2])
    session.commit()
    session.close()

    dlg = StockCheckDialog(
        parent=None,
        db_path=str(db_file),
        branch_name="สาขาอำนาจเจริญ"
    )

    assert "สาขาอำนาจเจริญ" in dlg.windowTitle()
    assert dlg.table.rowCount() == 2
    assert dlg.category_combo.count() == 3  # "ทุกหมวดหมู่", categories...

    # Find combo index for Category 1 (เนื้อหมู)
    idx_cat1 = dlg.category_combo.findData(1)
    assert idx_cat1 > 0
    dlg.category_combo.setCurrentIndex(idx_cat1)
    assert dlg.table.isRowHidden(0) is False
    assert dlg.table.isRowHidden(1) is True

    # Find combo index for Category 2 (เนื้อวัว)
    idx_cat2 = dlg.category_combo.findData(2)
    assert idx_cat2 > 0
    dlg.category_combo.setCurrentIndex(idx_cat2)
    assert dlg.table.isRowHidden(0) is True
    assert dlg.table.isRowHidden(1) is False

    # Reset to all categories (index 0)
    dlg.category_combo.setCurrentIndex(0)
    assert dlg.table.isRowHidden(0) is False
    assert dlg.table.isRowHidden(1) is False

    # Check search filter
    dlg.search_input.setText("เนื้อวัว")
    assert dlg.table.isRowHidden(0) is True
    assert dlg.table.isRowHidden(1) is False

    # Clear search filter
    dlg.search_input.setText("")
    assert dlg.table.isRowHidden(0) is False
    assert dlg.table.isRowHidden(1) is False
