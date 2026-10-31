import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.customer_display import CustomerDisplayWindow

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_customer_display_fullscreen_toggle(qapp):
    win = CustomerDisplayWindow()
    assert hasattr(win, 'fullscreen_btn')
    assert "เต็มจอ" in win.fullscreen_btn.text()
    
    # Toggle to full screen
    win.toggle_fullscreen()
    assert win.isFullScreen() is True
    assert "ย่อจอ" in win.fullscreen_btn.text()
    
    # Toggle back to normal
    win.toggle_fullscreen()
    assert win.isFullScreen() is False
    assert "เต็มจอ" in win.fullscreen_btn.text()
    
    win.close()
