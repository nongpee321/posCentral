import pytest
from PySide6.QtWidgets import QApplication
from ui.customer_display import CustomerDisplayWindow

def test_move_to_secondary_screen_method(qtbot):
    win = CustomerDisplayWindow()
    qtbot.addWidget(win)
    assert hasattr(win, 'move_to_secondary_screen')
    # When tested on single screen machine, returns False and displays window normally
    res = win.move_to_secondary_screen(fullscreen=False)
    assert res in (True, False)
    assert win.isVisible() is True
    win.close()
