import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtCore import Qt
from ui.drawer_pin_dialog import DrawerPinDialog

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_drawer_pin_dialog_ui(qapp):
    dlg = DrawerPinDialog(active_pin="1234")
    assert dlg.pin_input is not None
    assert dlg.confirm_btn is not None
    assert dlg.windowTitle() == "ยืนยันรหัส PIN เปิดลิ้นชัก"
    
    # Test entering digits via keypad
    dlg.append_digit("1")
    dlg.append_digit("2")
    assert dlg.pin_input.text() == "12"
    
    dlg.pin_input.clear()
    assert dlg.pin_input.text() == ""

def test_drawer_pin_verification_active_pin(qapp):
    dlg = DrawerPinDialog(active_pin="5566", cashier_code="EMP01")
    dlg.pin_input.setText("5566")
    dlg.verify_and_open()
    assert dlg.result() == QDialog.Accepted
    assert dlg.verified_cashier_name == "EMP01"

def test_drawer_pin_verification_wrong_pin(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    dlg = DrawerPinDialog(active_pin="5566")
    dlg.pin_input.setText("9999")
    dlg.verify_and_open()
    # Dialog should not accept wrong pin
    assert dlg.result() != QDialog.Accepted
