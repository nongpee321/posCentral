import pytest
from PySide6.QtWidgets import QApplication, QListWidget, QTableWidget
from PySide6.QtCore import Qt
from database.models import init_db, Product, ProductBarcode
from services.barcode_lookup import lookup_product, find_by_name

app = QApplication.instance() or QApplication([])

@pytest.fixture
def mock_db(tmp_path):
    db_path = str(tmp_path / "test_search.db")
    session = init_db(f"sqlite:///{db_path}")

    # Seed products with pork (หมู) items
    p1 = Product(
        id=101,
        sku_code="PORK01",
        barcode="8850001001",
        name_th="หมูบดสด (กก.)",
        default_price=130.0,
        pos_price=130.0,
        is_active=True
    )
    p2 = Product(
        id=102,
        sku_code="PORK02",
        barcode="8850001002",
        name_th="สันนอกหมู สไลซ์",
        default_price=160.0,
        pos_price=150.0,
        is_promotion=True,
        is_active=True
    )
    p3 = Product(
        id=103,
        sku_code="PORK03",
        barcode="8850001003",
        name_th="หมูสามชั้น หั่นชิ้น",
        default_price=180.0,
        pos_price=180.0,
        is_active=True
    )
    p4 = Product(
        id=104,
        sku_code="CHICK01",
        barcode="8850002001",
        name_th="อกไก่ไร้หนัง",
        default_price=95.0,
        pos_price=95.0,
        is_active=True
    )

    session.add_all([p1, p2, p3, p4])
    session.commit()
    session.close()
    return db_path

def test_find_by_name_pork_query(mock_db):
    session = init_db(f"sqlite:///{mock_db}")
    try:
        # 1. Search "หมู" -> should find all 3 pork items
        pork_items = find_by_name(session, "หมู")
        assert len(pork_items) == 3
        names = [p.name_th for p in pork_items]
        assert "หมูบดสด (กก.)" in names
        assert "สันนอกหมู สไลซ์" in names
        assert "หมูสามชั้น หั่นชิ้น" in names

        # 2. Search specific "สันนอก" -> 1 item
        sirloin = find_by_name(session, "สันนอก")
        assert len(sirloin) == 1
        assert sirloin[0].sku_code == "PORK02"

        # 3. Lookup product by name "หมู" -> ambiguous (multiple items)
        res_ambiguous = lookup_product(session, "หมู")
        assert res_ambiguous["status"] == "ambiguous"
        assert len(res_ambiguous["products"]) == 3

        # 4. Lookup product by unique name "อกไก่" -> found
        res_found = lookup_product(session, "อกไก่")
        assert res_found["status"] == "found"
        assert res_found["product"].id == 104
    finally:
        session.close()

def test_suggestions_list_and_selection(qtbot, mock_db):
    from ui.main_window import MainWindow

    class MockWindow:
        def __init__(self, db_p):
            from PySide6.QtWidgets import QLineEdit, QListWidget, QTableWidget
            self.db_path = db_p
            self.search_input = QLineEdit()
            self.suggestions_list = QListWidget()
            self.cart_table = QTableWidget(0, 5)
            self.added_products = []

        def handle_product_click(self, p_dict):
            self.added_products.append(p_dict)

        def render_products_grid(self, *args, **kwargs):
            pass

    win = MockWindow(mock_db)

    # 1. Type "หมู"
    MainWindow._update_search_suggestions(win, "หมู")
    assert win.suggestions_list.count() == 3
    assert win.suggestions_list.isVisible()

    first_item = win.suggestions_list.item(0)
    assert "หมู" in first_item.text()

    # 2. Click suggestion item
    MainWindow.on_suggestion_clicked(win, first_item)
    assert len(win.added_products) == 1
    assert "หมู" in win.added_products[0]["name_th"]
    assert win.suggestions_list.count() == 0
    assert not win.suggestions_list.isVisible()
