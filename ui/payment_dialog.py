import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QPushButton, QLabel, QFrame, QWidget, QLineEdit, QCheckBox, QMessageBox, QFormLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage
import qrcode
from ui.customer_display import generate_promptpay
from PySide6.QtGui import QFont, QIcon, QDoubleValidator


class IdleTimeoutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("แจ้งเตือนหมดเวลา")
        self.setFixedSize(400, 200)
        self.setStyleSheet("background-color: white; font-family: Tahoma, sans-serif;")
        
        layout = QVBoxLayout(self)
        
        self.lbl_msg = QLabel("หมดเวลาชำระเงิน ต้องการทำรายการต่อหรือไม่?\nระบบจะยกเลิกบิลอัตโนมัติใน 60 วินาที")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        self.lbl_msg.setStyleSheet("font-size: 16px; font-weight: bold; color: #111827;")
        layout.addWidget(self.lbl_msg)
        
        btn_layout = QHBoxLayout()
        self.btn_continue = QPushButton("ยังทำรายการอยู่")
        self.btn_continue.setStyleSheet("background-color: #10b981; color: white; padding: 10px; border-radius: 8px; font-weight: bold; font-size: 16px;")
        self.btn_continue.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("ขึ้นบิลใหม่")
        self.btn_cancel.setStyleSheet("background-color: #ef4444; color: white; padding: 10px; border-radius: 8px; font-weight: bold; font-size: 16px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_continue)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.countdown = 60
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)
        
    def update_timer(self):
        self.countdown -= 1
        self.lbl_msg.setText(f"หมดเวลาชำระเงิน ต้องการทำรายการต่อหรือไม่?\nระบบจะยกเลิกบิลอัตโนมัติใน {self.countdown} วินาที")
        if self.countdown <= 0:
            self.timer.stop()
            self.reject()

class PaymentDialog(QDialog):
    def __init__(self, parent=None, total_amount=0.0, total_items=0, total_qty=0.0, discount_amount=0.0):
        super().__init__(parent)
        self.setWindowTitle("รับชำระเงิน")
        self.setFixedSize(850, 620)
        self.setStyleSheet("background-color: white; color: #111827;")
        
        self.discount_amount = float(discount_amount or 0.0)
        self.total_amount = float(total_amount or 0.0)
        self.subtotal = float(total_amount or 0.0) + self.discount_amount
        self.total_items = total_items
        self.total_qty = total_qty
        
        self.selected_method = "เงินสด"
        self.received_amount = 0.0
        self.change_amount = 0.0
        self.transfer_amount = 0.0
        
        # Tax Invoice Data
        self.is_full_tax = False
        self.customer_name = ""
        self.customer_tax_id = ""
        self.customer_address = ""

        self.clear_cart_requested = False
        self.timer_seconds = 60
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.prompt_idle)
        self.idle_timer.start(1000)
        
        self.init_ui()
        self.update_summary_card()
        self.update_displays()
        
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left Panel (Gray)
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #f3f4f6;")
        left_panel.setFixedWidth(350)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(20)
        
        # Payment Methods
        methods_layout = QGridLayout()
        self.method_btns = {}
        row, col = 0, 0
        for m in ["เงินสด", "QR"]:
            btn = QPushButton(m)
            btn.setCheckable(True)
            btn.setFixedHeight(60)
            btn.setStyleSheet("""
                QPushButton { background-color: white; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 14px; font-weight: bold; color: #4b5563; }
                QPushButton:checked { border: 2px solid #10b981; color: #10b981; background-color: #ecfdf5; }
            """)
            btn.clicked.connect(lambda checked, method=m: self.set_method(method))
            self.method_btns[m] = btn
            methods_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        self.method_btns["เงินสด"].setChecked(True)
        left_layout.addLayout(methods_layout)
        

        
        # Summary Card
        self.summary_card = QFrame()
        self.summary_card.setStyleSheet("background-color: white; border-radius: 12px; border: 1px solid #e5e7eb;")
        self.summary_layout = QVBoxLayout(self.summary_card)
        self.summary_layout.setSpacing(8)

        # Action button to add / edit discount inside payment dialog
        self.btn_discount_dialog = QPushButton("ใส่ / แก้ไขส่วนลดบิล")
        self.btn_discount_dialog.setFixedHeight(38)
        self.btn_discount_dialog.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                border-radius: 6px;
                font-size: 13.5px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        self.btn_discount_dialog.clicked.connect(self.prompt_discount)

        left_layout.addWidget(self.summary_card)
        left_layout.addWidget(self.btn_discount_dialog)
        left_layout.addStretch()
        main_layout.addWidget(left_panel)
        
        # Right Panel
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(30, 30, 30, 30)
        right_layout.setSpacing(15)
        
        self.title_lbl = QLabel("รับเงินสด")
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #1f2937;")
        right_layout.addWidget(self.title_lbl)
        
        # Normal Input
        self.input_field = QLineEdit()
        self.input_field.setReadOnly(True)
        self.input_field.setAlignment(Qt.AlignRight)
        self.input_field.setStyleSheet("""
            QLineEdit { border: 2px solid #e5e7eb; border-radius: 12px; font-size: 36px; padding: 15px; color: #111827; }
        """)
        right_layout.addWidget(self.input_field)
        
        self.change_lbl = QLabel("เงินทอน: ฿ 0.00")
        self.change_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #f59e0b;")
        self.change_lbl.setAlignment(Qt.AlignRight)
        right_layout.addWidget(self.change_lbl)
        
        # Keypad
        keypad_layout = QGridLayout()
        keypad_layout.setSpacing(10)
        
        keys = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2), ("1,000", 0, 3),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2), ("500", 1, 3),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2), ("100", 2, 3),
            ("0", 3, 0), ("00", 3, 1), (".", 3, 2), ("C", 3, 3)
        ]
        
        for key, r, c in keys:
            btn = QPushButton(key)
            btn.setFixedHeight(65)
            if key == "C":
                btn.setStyleSheet("background-color: #fee2e2; color: #ef4444; font-size: 24px; font-weight: bold; border-radius: 8px; border: none;")
                btn.clicked.connect(self.clear_input)
            elif key in ["1,000", "500", "100"]:
                btn.setStyleSheet("background-color: #f3f4f6; color: #374151; font-size: 20px; font-weight: bold; border-radius: 8px; border: none;")
                btn.clicked.connect(lambda checked, k=key: self.quick_cash(k))
            else:
                btn.setStyleSheet("background-color: white; color: #111827; font-size: 24px; font-weight: bold; border-radius: 8px; border: 1px solid #e5e7eb;")
                btn.clicked.connect(lambda checked, k=key: self.append_input(k))
            keypad_layout.addWidget(btn, r, c)
            
        self.keypad_widget = QWidget()
        self.keypad_widget.setLayout(keypad_layout)
        right_layout.addWidget(self.keypad_widget)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.hide()
        right_layout.addWidget(self.qr_label)
        
        
        
        # Action Buttons
        action_layout = QHBoxLayout()
        
        self.cancel_bill_btn = QPushButton("ยกเลิกบิล")
        self.cancel_bill_btn.setFixedHeight(60)
        self.cancel_bill_btn.setStyleSheet("background-color: #ef4444; color: white; font-size: 22px; font-weight: bold; border-radius: 8px; border: none;")
        self.cancel_bill_btn.clicked.connect(self.request_cancel_bill)
        
        self.submit_btn = QPushButton("ยืนยันชำระเงิน (Enter)")
        self.submit_btn.setFixedHeight(60)
        self.submit_btn.setStyleSheet("background-color: #3b82f6; color: white; font-size: 22px; font-weight: bold; border-radius: 8px; border: none;")
        self.submit_btn.clicked.connect(self.accept_payment)
        
        action_layout.addWidget(self.cancel_bill_btn, 1)
        action_layout.addWidget(self.submit_btn, 2)
        right_layout.addLayout(action_layout)
        
        main_layout.addWidget(right_panel)
        
        self.received_str = ""
        self.set_method(self.selected_method)
        
    def accept(self):
        if hasattr(self, 'idle_timer'):
            self.idle_timer.stop()
        super().accept()

    def reject(self):
        if hasattr(self, 'idle_timer'):
            self.idle_timer.stop()
        super().reject()

    def prompt_idle(self):
        self.timer_seconds -= 1
        parent_window = self.parent()
        if parent_window and getattr(parent_window, "customer_display", None) and not parent_window.customer_display.isHidden():
            parent_window.customer_display.update_timer(self.timer_seconds)
            
        if self.timer_seconds <= 0:
            self.idle_timer.stop()
            dialog = IdleTimeoutDialog(self)
            if dialog.exec() == QDialog.Accepted:
                self.timer_seconds = 60
                self.idle_timer.start(1000)
            else:
                self.clear_cart_requested = True
                self.reject()

    def update_summary_card(self):
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                sub_l = item.layout()
                while sub_l.count():
                    sub_item = sub_l.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        def add_summary_row(label, value, is_discount=False):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 14px; color: {'#059669' if is_discount else '#374151'}; font-weight: bold; border: none;")
            val = QLabel(str(value))
            val.setStyleSheet(f"font-size: 14px; color: {'#10b981' if is_discount else '#111827'}; font-weight: bold; border: none;")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            self.summary_layout.addLayout(row)

        add_summary_row("จำนวนรายการ", f"{self.total_items}")
        add_summary_row("จำนวนชิ้น", f"{self.total_qty:g}")
        if self.subtotal > self.total_amount or self.discount_amount > 0:
            add_summary_row("ยอดรวมเดิม", f"฿{self.subtotal:,.2f}")
            add_summary_row("ส่วนลด", f"-฿{self.discount_amount:,.2f}", is_discount=True)

        self.total_lbl = QLabel(f"฿ {self.total_amount:,.2f}")
        self.total_lbl.setStyleSheet("font-size: 32px; font-weight: bold; color: #10b981; margin-top: 6px; border: none;")
        self.total_lbl.setAlignment(Qt.AlignCenter)
        self.summary_layout.addWidget(self.total_lbl)

    def prompt_discount(self):
        from ui.discount_dialog import DiscountDialog
        cur_label = getattr(self.parent(), 'discount_label', '') if self.parent() else ''
        dlg = DiscountDialog(self, subtotal=self.subtotal, current_discount=self.discount_amount, current_label=cur_label)
        if dlg.exec() == QDialog.Accepted:
            self.discount_amount = dlg.discount_amount
            self.total_amount = max(0.0, round(self.subtotal - self.discount_amount, 2))
            if self.parent():
                self.parent().discount_amount = self.discount_amount
                self.parent().discount_label = dlg.discount_label
                if hasattr(self.parent(), 'update_cart_total'):
                    self.parent().update_cart_total()
            self.update_summary_card()
            self.set_method(self.selected_method)

    def set_method(self, method):
        for m, btn in self.method_btns.items():
            btn.setChecked(m == method)
        self.selected_method = method
        if hasattr(self, 'qr_label'):
            self.qr_label.hide()
        self.title_lbl.setText(f"ยอดรับชำระ: {method}")
        parent_window = self.parent()
        if parent_window and getattr(parent_window, "customer_display", None) and not parent_window.customer_display.isHidden():
            parent_window.customer_display.show_payment(method, override_amount=self.total_amount, discount=self.discount_amount)
        
        if method == "QR":
            self.keypad_widget.hide()
            self.input_field.hide()
            self.change_lbl.hide()
            
            
            # Show QR
            self.qr_label.show()
            try:
                parent_window = self.parent()
                ppid = parent_window.config.get('promptpay_id', '0999999999') if parent_window else '0999999999'
                self.title_lbl.setText(f"PromptPay: {ppid}")
                promptpay_id = parent_window.config.get('promptpay_id', '0999999999') if parent_window else '0999999999'
                payload = generate_promptpay(promptpay_id, self.total_amount)
                import io
                qr_img = qrcode.make(payload)
                buf = io.BytesIO()
                qr_img.save(buf, format="PNG")
                pix = QPixmap()
                pix.loadFromData(buf.getvalue())
                pix = pix.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.qr_label.setPixmap(pix)
            except Exception as e:
                print("QR Error:", e)
                
            self.received_str = f"{self.total_amount:.2f}"
            self.update_displays()
        else:
            self.keypad_widget.show()
            self.input_field.show()
            self.change_lbl.show()
            
            self.received_str = ""
            self.update_displays()
            
    def append_input(self, val):
        if val == "." and "." in self.received_str:
            return
        if self.received_str == "0" and val != ".":
            self.received_str = val
        else:
            self.received_str += val
        self.update_displays()
        
    def quick_cash(self, val):
        amount = float(val.replace(",", ""))
        current = float(self.received_str or 0)
        self.received_str = str(current + amount)
        self.update_displays()
        
    def clear_input(self):
        self.received_str = ""
        self.update_displays()
        
    def update_displays(self):
        try:
            self.received_amount = float(self.received_str or 0)
        except ValueError:
            self.received_amount = 0.0
            
        self.input_field.setText(f"{self.received_amount:,.2f}")
        
        if self.received_amount >= self.total_amount:
            self.change_amount = self.received_amount - self.total_amount
            self.change_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #10b981;")
        else:
            self.change_amount = 0.0
            self.change_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #ef4444;")
            
        self.change_lbl.setText(f"เงินทอน: ฿ {self.change_amount:,.2f}")
        
        self.cash_amount = self.received_amount if self.selected_method == "เงินสด" else 0.0
        self.transfer_amount = self.total_amount if self.selected_method == "QR" else 0.0

    def request_cancel_bill(self):
        self.explicit_cancel_bill = True
        self.reject()

    def accept_payment(self):
        if self.received_amount < self.total_amount:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "แจ้งเตือน", "ยอดเงินรับยังไม่ครบ!")
            return
            
        self.accept()

