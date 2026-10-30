import sys
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
try:
    from ui.customer_display import CustomerDisplayWindow
    win = CustomerDisplayWindow()
    print("Success!")
except Exception as e:
    import traceback
    print("Error:")
    traceback.print_exc()
