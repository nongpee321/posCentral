import pytest
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def test_mainwindow_initialization(qtbot):
    # This test verifies that the MainWindow can be initialized without fatal errors (like AttributeError)
    window = MainWindow()
    qtbot.addWidget(window)
    assert window is not None
    assert hasattr(window, "manual_open_drawer")
    assert hasattr(window, "cancel_current_bill")
    assert hasattr(window, "create_products_panel")
