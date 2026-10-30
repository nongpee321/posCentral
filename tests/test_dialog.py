import sys
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QCheckBox, QLineEdit
from PySide6.QtCore import Qt
from ui.customer_display import CustomerDisplayWindow
import traceback

app = QApplication.instance() or QApplication([])

class DummyMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = {'promptpay_id': '0812345678'}
        self.customer_display = CustomerDisplayWindow(self)
        self.customer_display.show()

class DummyDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.show_split_qr_checkbox = QCheckBox()
        self.show_split_qr_checkbox.setChecked(True)
        self.selected_method = "ผสม (Split)"
        self.inp_split_transfer = QLineEdit("10.50")
        
        from PySide6.QtWidgets import QLabel
        self.qr_label = QLabel()

    def toggle_split_qr(self, state):
        is_checked = self.show_split_qr_checkbox.isChecked()
        if is_checked and self.selected_method == "ผสม (Split)":
            try:
                amt = float(self.inp_split_transfer.text() or 0)
                print(f"Amt is {amt}")
                if amt > 0:
                    if hasattr(self.parent(), 'customer_display') and self.parent().customer_display:
                        print("Updating customer display...")
                        self.parent().customer_display.show_payment("QR", override_amount=amt)
                        
                    parent_window = self.parent()
                    promptpay_id = parent_window.config.get('promptpay_id', '0999999999') if parent_window else '0999999999'
                    
                    from ui.customer_display import generate_promptpay
                    import io, qrcode
                    from PySide6.QtGui import QPixmap
                    from PySide6.QtCore import Qt
                    
                    print("Generating cashier QR...")
                    payload = generate_promptpay(promptpay_id, amt)
                    qr_img = qrcode.make(payload)
                    buf = io.BytesIO()
                    qr_img.save(buf, format="PNG")
                    pix = QPixmap()
                    pix.loadFromData(buf.getvalue())
                    pix = pix.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.qr_label.setPixmap(pix)
                    self.qr_label.show()
                    print("Success!")
                else:
                    print("Amt is 0")
            except Exception as e:
                print("Exception:", e)
                traceback.print_exc()
        else:
            print("Not checked or wrong method")

m = DummyMainWindow()
d = DummyDialog(m)
d.toggle_split_qr(2)
