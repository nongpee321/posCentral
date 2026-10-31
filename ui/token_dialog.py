import os
import sys
import requests
from services.offline_auth import verify_offline_login
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QMessageBox, QWidget, QFrame,
    QInputDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from urllib.parse import urlsplit

VERSION_STRING = "1.2.21"

class PosTokenLoginDialog(QDialog):
    """
    หน้าต่างเข้าสู่ระบบจุดขาย (POS Terminal Authentication)
    ธีมสีแดง-ขาว (Signature Pop Star Red & White) คมชัด สวยงาม ทรงพลัง ระดับ Commercial POS
    """
    def __init__(self, parent=None, api_url="http://localhost:8000", default_token="", default_username="", cached_offline_auth=None):
        super().__init__(parent)
        self.api_url = (api_url or "http://localhost:8000").rstrip("/")
        self.token = default_token.strip()
        self.username = default_username.strip()
        self.verified_device = None
        self.branch_name = ""
        self.device_name = ""
        self.selected_cashier = None
        self.entered_pin = ""
        self.is_offline_login = False
        self.offline_auth = cached_offline_auth if isinstance(cached_offline_auth, dict) else None

        self.setWindowTitle(f"PopCentral POS — เข้าสู่ระบบ (v{VERSION_STRING})")
        self.setFixedSize(440, 540)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            }
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: #0f172a;
                font-size: 14px;
                font-weight: 500;
            }
            QMessageBox QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-size: 13.5px;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 20px;
                min-width: 80px;
                min-height: 30px;
                border: 1px solid #1d4ed8;
            }
            QMessageBox QPushButton:hover {
                background-color: #1d4ed8;
            }
            QMessageBox QPushButton:pressed {
                background-color: #1e40af;
            }
            QInputDialog {
                background-color: #ffffff;
            }
            QInputDialog QLabel {
                color: #0f172a;
                font-size: 14px;
                font-weight: 600;
            }
            QInputDialog QLineEdit {
                background-color: #f8fafc;
                color: #0f172a;
                border: 1.5px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
            }
            QInputDialog QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-size: 13.5px;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 18px;
                min-width: 75px;
                min-height: 28px;
                border: 1px solid #1d4ed8;
            }
            QInputDialog QComboBox, QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 1.5px solid #3b82f6;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 14px;
                font-weight: 600;
                min-height: 32px;
            }
            QInputDialog QComboBox:hover, QComboBox:hover {
                border-color: #2563eb;
            }
            QInputDialog QComboBox::drop-down, QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left: 1px solid #cbd5e1;
                background-color: #f1f5f9;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QInputDialog QComboBox QAbstractItemView, QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #0f172a;
                border: 1.5px solid #cbd5e1;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                font-size: 14px;
                padding: 4px;
            }

        """)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Top Red Header Bar
        top_header = QWidget()
        top_header.setStyleSheet("background-color: #dc2626; border-top-left-radius: 0px; border-top-right-radius: 0px;")
        top_layout = QVBoxLayout(top_header)
        top_layout.setContentsMargins(30, 24, 30, 22)
        top_layout.setSpacing(4)
        top_layout.setAlignment(Qt.AlignCenter)

        # Brand / Logo
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(__file__))
        logo_path = os.path.join(base_dir, 'assets', 'logo.png')
        
        if os.path.exists(logo_path):
            logo_lbl = QLabel()
            logo_lbl.setAlignment(Qt.AlignCenter)
            pix = QPixmap(logo_path).scaled(190, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            top_layout.addWidget(logo_lbl)
        else:
            brand_title = QLabel("POP STAR FOOD")
            brand_title.setAlignment(Qt.AlignCenter)
            brand_title.setStyleSheet("font-size: 20px; font-weight: 900; color: #ffffff; letter-spacing: 2px;")
            top_layout.addWidget(brand_title)

        title = QLabel(f"POS SYSTEM (v{VERSION_STRING})")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #fee2e2; letter-spacing: 1.5px; margin-top: 2px;")
        top_layout.addWidget(title)

        layout.addWidget(top_header)

        # 2. Form Content Area (Clean White)
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #ffffff;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(36, 24, 36, 24)
        content_layout.setSpacing(14)

        # Field 1: Device Token
        f1_box = QVBoxLayout()
        f1_box.setSpacing(4)
        lbl1 = QLabel("รหัสเครื่องจุดขาย (Device Token)")
        lbl1.setStyleSheet("font-size: 12px; font-weight: 700; color: #374151;")
        f1_box.addWidget(lbl1)

        self.token_input = QLineEdit()
        self.token_input.setText(self.token)
        self.token_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 14px;
                border: 1.5px solid #d1d5db;
                border-radius: 6px;
                font-size: 13px;
                color: #111827;
                background-color: #f9fafb;
            }
            QLineEdit:focus {
                border-color: #dc2626;
                background-color: #ffffff;
            }
        """)
        f1_box.addWidget(self.token_input)
        content_layout.addLayout(f1_box)

        # Field 2: Username
        f2_box = QVBoxLayout()
        f2_box.setSpacing(4)
        lbl2 = QLabel("ชื่อผู้ใช้งาน (Username)")
        lbl2.setStyleSheet("font-size: 12px; font-weight: 700; color: #374151;")
        f2_box.addWidget(lbl2)

        self.user_input = QLineEdit()
        self.user_input.setText(self.username)
        self.user_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 14px;
                border: 1.5px solid #d1d5db;
                border-radius: 6px;
                font-size: 13px;
                color: #111827;
                background-color: #f9fafb;
            }
            QLineEdit:focus {
                border-color: #dc2626;
                background-color: #ffffff;
            }
        """)
        f2_box.addWidget(self.user_input)
        content_layout.addLayout(f2_box)

        # Field 3: Cashier PIN (Digits)
        f3_box = QVBoxLayout()
        f3_box.setSpacing(4)
        lbl3 = QLabel("รหัส PIN แคชเชียร์ (ตัวเลข 4-6 หลัก)")
        lbl3.setStyleSheet("font-size: 12px; font-weight: 700; color: #374151;")
        f3_box.addWidget(lbl3)

        self.pin_input = QLineEdit()
        self.pin_input.setPlaceholderText("ใส่รหัส PIN เช่น 1234 หรือ 0000")
        self.pin_input.setToolTip("รหัส PIN ประจำตัวพนักงานแคชเชียร์ (ตัวเลข 4-6 หลักที่ตั้งไว้ในระบบ ERP)")
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 14px;
                border: 1.5px solid #d1d5db;
                border-radius: 6px;
                font-size: 13px;
                color: #111827;
                background-color: #f9fafb;
            }
            QLineEdit:focus {
                border-color: #dc2626;
                background-color: #ffffff;
            }
        """)
        self.pin_input.returnPressed.connect(self.do_verify_and_login)
        self.user_input.returnPressed.connect(self.pin_input.setFocus)
        self.token_input.returnPressed.connect(self.user_input.setFocus)
        f3_box.addWidget(self.pin_input)
        content_layout.addLayout(f3_box)

        # Status Label
        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626; min-height: 18px;")
        content_layout.addWidget(self.status_lbl)
        try:
            if urlsplit(self.api_url).hostname.casefold() in ("localhost", "127.0.0.1", "::1"):
                self.status_lbl.setText(
                    "ERP URL ชี้ไป localhost (เครื่องนี้) — หาก ERP อยู่เครื่องอื่น กด “ตั้งค่า ERP”"
                )
                self.status_lbl.setStyleSheet(
                    "font-size: 12px; font-weight: 700; color: #b45309; min-height: 18px;"
                )
        except (AttributeError, ValueError):
            self.status_lbl.setText("ERP URL ไม่ถูกต้อง — กด “ตั้งค่า ERP” เพื่อแก้ไข")

        content_layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        exit_btn = QPushButton("ปิด")
        exit_btn.setFixedSize(70, 44)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6;
                color: #4b5563;
                font-weight: 700;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e5e7eb;
                color: #111827;
            }
        """)
        exit_btn.clicked.connect(self.reject)

        server_btn = QPushButton("ตั้งค่า ERP")
        server_btn.setFixedSize(80, 44)
        server_btn.setToolTip("ตั้งค่า URL ของ ERP Server ที่เครื่อง POS ต้องเชื่อมต่อ")
        server_btn.setStyleSheet("""
            QPushButton {
                background-color: #eff6ff;
                color: #1d4ed8;
                font-weight: 700;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #dbeafe;
            }
        """)
        server_btn.clicked.connect(self.configure_server)

        self.login_btn = QPushButton("เข้าสู่ระบบ")
        self.login_btn.setFixedHeight(44)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                font-size: 15px;
                font-weight: 800;
                border: none;
                border-radius: 6px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
            QPushButton:pressed {
                background-color: #991b1b;
            }
            QPushButton:disabled {
                background-color: #fca5a5;
                color: #ffffff;
            }
        """)
        self.login_btn.clicked.connect(self.do_verify_and_login)

        guide_btn = QPushButton("คู่มือ")
        guide_btn.setFixedSize(80, 44)
        guide_btn.setStyleSheet("""
            QPushButton {
                background-color: #fef2f2;
                color: #dc2626;
                font-weight: 700;
                border: 1px solid #fecaca;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #fee2e2;
                color: #b91c1c;
            }
        """)
        guide_btn.clicked.connect(self.show_quick_guide)

        btn_layout.addWidget(guide_btn)
        btn_layout.addWidget(server_btn)
        btn_layout.addWidget(exit_btn)
        btn_layout.addWidget(self.login_btn)
        content_layout.addLayout(btn_layout)

        layout.addWidget(content_widget)

        # Auto Focus
        if not self.token:
            self.token_input.setFocus()
        elif not self.username:
            self.user_input.setFocus()
        else:
            self.pin_input.setFocus()

    def configure_server(self):
        url, accepted = QInputDialog.getText(
            self,
            "ตั้งค่า ERP Server",
            "ใส่ API URL ของ ERP (เช่น https://erp.example.com):",
            text=self.api_url,
        )
        if not accepted:
            return

        url = url.strip().rstrip("/")
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            has_credentials = parsed.username is not None or parsed.password is not None
        except ValueError:
            hostname = None
            has_credentials = False
            parsed = None
        if not parsed or parsed.scheme not in ("http", "https") or not hostname or has_credentials:
            QMessageBox.warning(
                self,
                "URL ไม่ถูกต้อง",
                "กรุณาระบุ URL ที่ขึ้นต้นด้วย http:// หรือ https:// และไม่มีชื่อผู้ใช้หรือรหัสผ่านใน URL",
            )
            return
        is_local_or_lan = (
            hostname.casefold() in ("localhost", "127.0.0.1", "::1")
            or hostname.startswith("192.168.")
            or hostname.startswith("10.")
            or hostname.startswith("172.")
        )
        if parsed.scheme != "https" and not is_local_or_lan:
            QMessageBox.warning(
                self,
                "ต้องใช้ HTTPS",
                "การเชื่อมต่อ ERP นอกเครื่องนี้ต้องใช้ https:// เพื่อปกป้องข้อมูลการเข้าสู่ระบบ",
            )
            return
        if parsed.query or parsed.fragment:
            QMessageBox.warning(self, "URL ไม่ถูกต้อง", "API URL ต้องไม่มี query string หรือ fragment")
            return

        self.api_url = url
        self.status_lbl.setText(f"ERP Server: {self.api_url}")
        QMessageBox.information(
            self,
            "เปลี่ยน ERP Server แล้ว",
            "เปลี่ยน URL ในหน้าต่างนี้แล้ว กดเข้าสู่ระบบเพื่อทดสอบการเชื่อมต่อ",
        )

    def play_intro_sound(self):
        """เสียงแจ้งเตือนสั้นๆ นุ่มนวลเมื่อเข้าใช้งานสำเร็จ"""
        try:
            import winsound
            winsound.PlaySound('SystemAsterisk', winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass

    def do_verify_and_login(self):
        token = self.token_input.text().strip()
        username = self.user_input.text().strip()
        pin = self.pin_input.text().strip()

        if not token:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุรหัสเครื่องจุดขาย (Token)")
            self.token_input.setFocus()
            return

        if not username:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุชื่อผู้ใช้งาน")
            self.user_input.setFocus()
            return

        if not pin:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุรหัสผ่าน")
            self.pin_input.setFocus()
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("กำลังตรวจสอบ...")
        self.status_lbl.setText("กำลังเชื่อมต่อเซิร์ฟเวอร์...")
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
        self.repaint()

        try:
            # 1. ตรวจสอบ Token
            ping_res = requests.get(
                f"{self.api_url}/api/pos/ping",
                headers={'Authorization': f"Bearer {token}", 'Accept': 'application/json'},
                timeout=(5, 20)
            )
            if ping_res.status_code != 200:
                self.status_lbl.setText("Token ไม่ถูกต้อง หรือถูกเพิกถอน")
                self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
                QMessageBox.warning(self, "ข้อผิดพลาด", "รหัสเครื่อง (Token) ไม่ถูกต้อง หรือถูกระงับการใช้งาน")
                self.login_btn.setEnabled(True)
                self.login_btn.setText("เข้าสู่ระบบ")
                return

            ping_data = ping_res.json()
            self.branch_id = ping_data.get('branch_id')
            self.branch_name = ping_data.get('branch_name', 'สำนักงานใหญ่')
            device_info = ping_data.get('device', {}) if isinstance(ping_data.get('device'), dict) else {}
            self.device_id = device_info.get('terminal_code') or str(device_info.get('id', 'POS-01'))
            self.device_name = device_info.get('name', 'POS Terminal')
            self.token = token

            # 2. ตรวจสอบ Cashier Credentials
            login_res = requests.post(
                f"{self.api_url}/api/pos/cashier/login",
                headers={'Authorization': f"Bearer {token}", 'Accept': 'application/json'},
                json={'code': username, 'pin': pin},
                timeout=(5, 20)
            )
            login_res.encoding = 'utf-8'

            if login_res.status_code == 200:
                login_data = login_res.json()
                if login_data.get('success'):
                    self.selected_cashier = login_data.get('cashier', {})
                    if 'code' not in self.selected_cashier:
                        self.selected_cashier['code'] = username
                    offline_credential = login_data.get('offline_credential')
                    self.offline_auth = {
                        'code': username,
                        'cashier': self.selected_cashier,
                        'credential': offline_credential,
                    } if isinstance(offline_credential, dict) else None
                    self.entered_pin = pin
                    self.username = username

                    cashier_name = self.selected_cashier.get('name') or username
                    self.status_lbl.setText(f"เข้าสู่ระบบสำเร็จ: {cashier_name}")
                    self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #16a34a;")
                    self.repaint()

                    self.play_intro_sound()
                    QTimer.singleShot(350, self.accept)
                    return
                else:
                    msg = login_data.get('message', 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
                    self.status_lbl.setText(msg)
                    self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
                    QMessageBox.warning(self, "เข้าสู่ระบบไม่สำเร็จ", msg)
            elif login_res.status_code == 403:
                self.status_lbl.setText("บัญชีนี้ไม่มีสิทธิ์การขาย POS")
                self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
                QMessageBox.warning(self, "ไม่มีสิทธิ์", "บัญชีผู้ใช้นี้ยังไม่ได้รับสิทธิ์การขายประจำเครื่อง POS")
            else:
                try:
                    err = login_res.json().get('message', 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
                except Exception:
                    err = f"เกิดข้อผิดพลาดในการเชื่อมต่อ ({login_res.status_code})"
                if "The pin field format is invalid" in str(err) or ("pin" in str(err).lower() and "format" in str(err).lower()):
                    err = "รหัส PIN ไม่ถูกต้อง: กรุณากรอกรหัส PIN แคชเชียร์ที่เป็นตัวเลข (เช่น 1234) ไม่ใช่รหัสผ่านตัวหนังสือของระบบเว็บ ERP\n\n(หากยังไม่ได้ตั้งรหัส PIN สามารถเข้าไปตรวจสอบหรือตั้งค่าได้ที่เมนูพนักงานใน ERP)"
                self.status_lbl.setText(err)
                self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
                QMessageBox.warning(self, "ข้อผิดพลาด", err)

        except requests.exceptions.RequestException as exc:
            self.status_lbl.setText(f"ติดต่อ ERP ไม่สำเร็จ ({type(exc).__name__})")
            self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
            if verify_offline_login(self.offline_auth, username, pin):
                self.token = token
                self.username = username
                self.entered_pin = pin
                self.selected_cashier = self.offline_auth.get('cashier') or {
                    'code': username,
                    'name': f"พนักงาน ({username})",
                }
                self.is_offline_login = True
                cashier_display_name = self.selected_cashier.get('name') or username
                self.play_intro_sound()
                QMessageBox.information(
                    self,
                    "โหมดออฟไลน์ (Offline Mode)",
                    f"ติดต่อ ERP ไม่สำเร็จ ({type(exc).__name__})\n"
                    f"เข้าสู่ระบบแบบออฟไลน์สำเร็จ: {cashier_display_name}\n\n"
                    "• ตรวจสอบข้อมูลผู้ใช้จากฐานข้อมูลภายในเครื่องเรียบร้อย\n"
                    "• สามารถขายสินค้าและพิมพ์ใบเสร็จได้ตามปกติ\n"
                    "• เมื่ออินเทอร์เน็ตเชื่อมต่อติด ระบบจะสลับเป็นโหมดออนไลน์และซิงค์บิลให้อัตโนมัติ"
                )
                self.accept()
                return
            QMessageBox.warning(
                self,
                "เข้าสู่ระบบออฟไลน์ไม่ได้",
                f"POS ติดต่อ ERP ไม่สำเร็จ ({type(exc).__name__}) และไม่พบข้อมูลยืนยันออฟไลน์ที่ยังใช้งานได้สำหรับบัญชีนี้ หรือ PIN ไม่ถูกต้อง",
            )
        except Exception as exc:
            self.status_lbl.setText(f"ตรวจสอบข้อมูลตอบกลับจาก ERP ไม่สำเร็จ ({type(exc).__name__})")
            self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #dc2626;")
            QMessageBox.critical(
                self,
                "ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ",
                f"เกิดข้อผิดพลาดระหว่างตรวจสอบการเข้าสู่ระบบ ({type(exc).__name__})\n"
                "ระบบไม่ได้เปลี่ยนเป็นโหมดออฟไลน์ กรุณาลองอีกครั้งหรือติดต่อผู้ดูแลระบบ",
            )

        finally:
            self.login_btn.setEnabled(True)
            self.login_btn.setText("เข้าสู่ระบบ")

    def show_quick_guide(self):
        from ui.manual_dialog import ManualDialog
        dialog = ManualDialog(self, initial_step=0)
        dialog.exec()
