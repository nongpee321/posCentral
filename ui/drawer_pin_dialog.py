import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QLineEdit, QPushButton, QMessageBox, QFrame, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from services.offline_auth import verify_offline_login

class DrawerPinDialog(QDialog):
    """
    หน้าต่างยืนยันรหัส PIN เพื่อเปิดลิ้นชักเก็บเงิน
    - รองรับแป้นพิมพ์ตัวเลขบนหน้าจอ (Touch keypad)
    - รองรับการกดแป้นพิมพ์จริง (0-9, Backspace, Enter, Esc)
    - ตรวจสอบรหัส PIN กับเซิร์ฟเวอร์ ERP หรือฐานข้อมูลออฟไลน์
    """
    def __init__(self, parent=None, api_url="", pos_token="", cashier_code="", offline_auth=None, active_pin=""):
        super().__init__(parent)
        self.api_url = (api_url or "").rstrip("/")
        self.pos_token = pos_token or ""
        self.cashier_code = cashier_code or ""
        self.offline_auth = offline_auth if isinstance(offline_auth, dict) else None
        self.active_pin = str(active_pin or "").strip()
        self.verified_cashier_name = ""
        
        self.setWindowTitle("ยืนยันรหัส PIN เปิดลิ้นชัก")
        self.setFixedSize(380, 520)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            }
            QLabel {
                color: #1e293b;
            }
        """)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(12)

        # Header Box
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1e293b; border-radius: 10px; padding: 8px 12px;")
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(4)
        
        title_lbl = QLabel("เปิดลิ้นชักเก็บเงิน (Cash Drawer)")
        title_lbl.setStyleSheet("color: white; font-size: 17px; font-weight: bold; border: none; background: transparent;")
        title_lbl.setAlignment(Qt.AlignCenter)
        
        sub_lbl = QLabel("กรุณาระบุรหัส PIN แคชเชียร์เพื่อเปิดลิ้นชัก")
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; border: none; background: transparent;")
        sub_lbl.setAlignment(Qt.AlignCenter)
        
        h_layout.addWidget(title_lbl)
        h_layout.addWidget(sub_lbl)
        main_layout.addWidget(header_frame)

        # PIN Display / Input
        self.pin_input = QLineEdit()
        self.pin_input.setPlaceholderText("ใส่รหัส PIN 4-6 หลัก")
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setMaxLength(12)
        self.pin_input.setAlignment(Qt.AlignCenter)
        self.pin_input.setFixedHeight(54)
        self.pin_input.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                font-size: 26px;
                font-weight: bold;
                letter-spacing: 6px;
                border: 2px solid #cbd5e1;
                border-radius: 10px;
                padding: 4px;
            }
            QLineEdit:focus {
                border-color: #2563eb;
            }
        """)
        self.pin_input.returnPressed.connect(self.verify_and_open)
        main_layout.addWidget(self.pin_input)

        # Numeric Keypad
        keypad_layout = QGridLayout()
        keypad_layout.setSpacing(8)
        
        keys = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("ล้าง", 3, 0), ("0", 3, 1), ("ลบ", 3, 2),
        ]
        
        for key, r, c in keys:
            btn = QPushButton(key)
            btn.setFixedHeight(50)
            btn.setCursor(Qt.PointingHandCursor)
            if key == "ล้าง":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #fee2e2;
                        color: #dc2626;
                        font-size: 16px;
                        font-weight: bold;
                        border-radius: 8px;
                        border: 1px solid #fecaca;
                    }
                    QPushButton:hover { background-color: #fca5a5; }
                """)
                btn.clicked.connect(self.pin_input.clear)
            elif key == "ลบ":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f1f5f9;
                        color: #475569;
                        font-size: 16px;
                        font-weight: bold;
                        border-radius: 8px;
                        border: 1px solid #cbd5e1;
                    }
                    QPushButton:hover { background-color: #e2e8f0; }
                """)
                btn.clicked.connect(self.pin_input.backspace)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #0f172a;
                        font-size: 20px;
                        font-weight: bold;
                        border-radius: 8px;
                        border: 1px solid #e2e8f0;
                    }
                    QPushButton:hover { background-color: #f8fafc; border-color: #cbd5e1; }
                    QPushButton:pressed { background-color: #e2e8f0; }
                """)
                btn.clicked.connect(lambda checked=False, digit=key: self.append_digit(digit))
            keypad_layout.addWidget(btn, r, c)
            
        main_layout.addLayout(keypad_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setFixedHeight(44)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #475569;
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover { background-color: #cbd5e1; }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        self.confirm_btn = QPushButton("ยืนยันเปิดลิ้นชัก")
        self.confirm_btn.setFixedHeight(44)
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self.confirm_btn.clicked.connect(self.verify_and_open)
        
        btn_layout.addWidget(cancel_btn, 1)
        btn_layout.addWidget(self.confirm_btn, 2)
        main_layout.addLayout(btn_layout)

    def append_digit(self, digit):
        self.pin_input.insert(digit)
        self.pin_input.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        self.pin_input.setFocus()
        self.pin_input.selectAll()

    def verify_and_open(self):
        pin = self.pin_input.text().strip()
        if not pin:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุรหัส PIN เพื่อเปิดลิ้นชัก")
            self.pin_input.setFocus()
            return

        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setText("กำลังตรวจสอบ...")
        self.repaint()

        try:
            # 1. Fast match with current session active PIN in memory
            if self.active_pin and pin == self.active_pin:
                self.verified_cashier_name = self.cashier_code or "แคชเชียร์ปัจจุบัน"
                self.accept()
                return

            # 2. Online verification with ERP
            if self.api_url and self.pos_token:
                try:
                    payload = {'pin': pin}
                    if self.cashier_code:
                        payload['code'] = self.cashier_code

                    res = requests.post(
                        f"{self.api_url}/api/pos/cashier/login",
                        headers={'Authorization': f"Bearer {self.pos_token}", 'Accept': 'application/json'},
                        json=payload,
                        timeout=4
                    )
                    if res.status_code == 200:
                        data = res.json()
                        if data.get('success'):
                            cashier_data = data.get('cashier', {})
                            self.verified_cashier_name = cashier_data.get('name') or self.cashier_code or "แคชเชียร์"
                            self.accept()
                            return
                    elif res.status_code in (401, 403, 422):
                        QMessageBox.warning(self, "ไม่อนุญาต", "รหัส PIN ไม่ถูกต้อง ไม่ได้รับอนุญาตให้เปิดลิ้นชัก")
                        self.pin_input.clear()
                        self.pin_input.setFocus()
                        self.confirm_btn.setEnabled(True)
                        self.confirm_btn.setText("ยืนยันเปิดลิ้นชัก")
                        return
                except Exception:
                    # Network timeout or offline, proceed to offline check
                    pass

            # 3. Offline pbkdf2 verifier
            if self.offline_auth and verify_offline_login(self.offline_auth, self.cashier_code, pin):
                self.verified_cashier_name = self.cashier_code or "แคชเชียร์ออฟไลน์"
                self.accept()
                return

            # If none matched
            QMessageBox.warning(self, "ไม่อนุญาต", "รหัส PIN ไม่ถูกต้อง ไม่ได้รับอนุญาตให้เปิดลิ้นชัก")
            self.pin_input.clear()
            self.pin_input.setFocus()

        finally:
            self.confirm_btn.setEnabled(True)
            self.confirm_btn.setText("ยืนยันเปิดลิ้นชัก")
