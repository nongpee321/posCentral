# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtWidgets import QApplication, QSplitter
from PySide6.QtCore import Qt
from ui.main_window import MainWindow
from database.models import init_db, Product, Category


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_db(tmp_path):
    db_file = tmp_path / "test_pos.db"
    session = init_db(f"sqlite:///{db_file}")

    cat = Category(id=1, name_th="หมวดทดสอบ")
    session.add(cat)

    for i in range(1, 15):
        p = Product(
            id=i,
            category_id=1,
            sku_code=f"SKU-{i:03d}",
            barcode=f"885000000{i:03d}",
            name_th=f"สินค้าทดสอบ {i}",
            default_price=50.0 + i,
            is_active=True,
            stock_qty=100.0,
        )
        session.add(p)
    session.commit()
    session.close()
    return str(db_file)


def test_main_splitter_initialization_and_resizability(qapp, mock_db):
    win = MainWindow(db_path=mock_db, is_offline_login=True)
    try:
        # 1. Main splitter must exist and be QSplitter
        assert hasattr(win, 'main_splitter'), "MainWindow must have main_splitter attribute"
        assert isinstance(win.main_splitter, QSplitter)

        # 2. Both sides must be non-collapsible and have minimum widths
        assert not win.main_splitter.childrenCollapsible()
        assert win.main_splitter.count() == 2

        left_widget = win.main_splitter.widget(0)
        right_widget = win.main_splitter.widget(1)
        assert left_widget.minimumWidth() >= 300
        assert right_widget.minimumWidth() >= 340

        # 3. Cart panel must have a generous allocation by default
        sizes = win.main_splitter.sizes()
        assert len(sizes) == 2
        # Cart width is at least 40% of total
        total_w = sum(sizes)
        assert sizes[1] / total_w >= 0.40

        # 4. Dragging splitter updates config and triggers rearrange
        win._on_splitter_moved(450, 1)
        saved = win.config.get('splitter_sizes')
        assert isinstance(saved, list) and len(saved) == 2
        assert all(isinstance(x, int) and x > 0 for x in saved)
    finally:
        win.close()


def test_debounced_search_performance(qapp, mock_db):
    win = MainWindow(db_path=mock_db, is_offline_login=True)
    try:
        # Fast consecutive typing (e.g. typing "สินค้า")
        win.on_search_text_changed("ส")
        assert hasattr(win, '_search_debounce_timer')
        assert win._search_debounce_timer.isActive()

        win.on_search_text_changed("สิน")
        assert win._search_debounce_timer.isActive()

        win.on_search_text_changed("สินค้า")
        assert win._search_debounce_timer.isActive()

        # Fire debounce
        win._search_debounce_timer.stop()
        win._do_debounced_search()

        # Products grid should display matching items
        assert win.prod_grid.count() > 0

        # Emptying search immediately resets without waiting for timer
        win.on_search_text_changed("")
        assert not win._search_debounce_timer.isActive()
    finally:
        win.close()


def test_dynamic_grid_columns(qapp, mock_db):
    win = MainWindow(db_path=mock_db, is_offline_login=True)
    try:
        assert hasattr(win, '_calculate_grid_cols')
        cols = win._calculate_grid_cols()
        assert cols >= 2
        assert hasattr(win, '_rearrange_product_grid')
        win._rearrange_product_grid()
    finally:
        win.close()
