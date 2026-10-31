from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QRadioButton, QButtonGroup, QMessageBox, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QDoubleValidator


class DiscountDialog(QDialog):
    """
    หน้าต่างกำหนดส่วนลดบิล (Commercial POS Touch-Enabled Discount Dialog)
    รองรับ:
      1. ลดเป็นจำนวนเงิน (฿) พร้อมปุ่มลัด [10], [20], [50], [100], [200], [500]
      2. ลดเป็นเปอร์เซ็นต์ (%) พร้อมปุ่มลัด [5%], [10%], [15%], [20%], [50%]
      3. แป้นพิมพ์ตัวเลขสัมผัส (Touch Numpad) สำหรับจอ POS ทัชสกรีน
      4. ปุ่มล้างส่วนลด / ไม่ลด
    แสดงยอดส่วนลดและยอดสุทธิหลังลดแบบ Realtime ทันที
    """
    def __init__(self, parent=None, subtotal=0.0, current_discount=0.0, current_label=""):
        super().__init__(parent)
        self.subtotal = float(subtotal or 0.0)
        self.discount_amount = float(current_discount or 0.0)
        self.discount_label = str(current_label or "")
        self.input_str = ""
        
        self.setWindowTitle("กำหนดส่วนลดบิล")
        self.setFixedWidth(460)
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QLabel {
                color: #0f172a;
            }
            QRadioButton {
                color: #1e293b;
                font-size: 14px;
                font-weight: 600;
                spacing: 6px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            QLineEdit {
                background-color: #f8fafc;
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 20px;
                font-weight: bold;
                color: #0f172a;
            }
            QLineEdit:focus {
                border-color: #2563eb;
                background-color: #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Header Box: Subtotal
        subtotal_frame = QFrame()
        subtotal_frame.setStyleSheet("""
            QFrame {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
        """)
        sub_layout = QHBoxLayout(subtotal_frame)
        sub_layout.setContentsMargins(12, 8, 12, 8)
        
        lbl_title = QLabel("ยอดรวมบิลก่อนลด:")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #475569;")
        sub_layout.addWidget(lbl_title)
        
        self.subtotal_val_lbl = QLabel(f"฿{self.subtotal:,.2f}")
        self.subtotal_val_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #0f172a;")
        self.subtotal_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sub_layout.addWidget(self.subtotal_val_lbl)
        
        layout.addWidget(subtotal_frame)

        # Mode Selection
        mode_title = QLabel("เลือกประเภทส่วนลด:")
        mode_title.setStyleSheet("font-size: 13.5px; font-weight: 700; color: #0f172a;")
        layout.addWidget(mode_title)

        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(10)

        self.btn_group = QButtonGroup(self)
        self.radio_baht = QRadioButton("บาท (฿)")
        self.radio_pct = QRadioButton("เปอร์เซ็นต์ (%)")
        self.radio_clear = QRadioButton("ไม่ลด (ล้างส่วนลด)")

        self.btn_group.addButton(self.radio_baht, 1)
        self.btn_group.addButton(self.radio_pct, 2)
        self.btn_group.addButton(self.radio_clear, 3)

        mode_layout.addWidget(self.radio_baht)
        mode_layout.addWidget(self.radio_pct)
        mode_layout.addWidget(self.radio_clear)
        layout.addLayout(mode_layout)

        # Quick Preset Buttons Container
        self.preset_container = QWidget()
        preset_layout = QHBoxLayout(self.preset_container)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(6)

        self.preset_btns = []
        self.current_presets = []
        preset_layout.addWidget(QLabel("ปุ่มลัด:"))
        for idx in range(6):
            pbtn = QPushButton("")
            pbtn.setFixedHeight(32)
            pbtn.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9;
                    color: #1e293b;
                    font-size: 13px;
                    font-weight: bold;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    background-color: #e2e8f0;
                }
            """)
            pbtn.clicked.connect(lambda ch, i=idx: self.on_preset_clicked(i))
            preset_layout.addWidget(pbtn)
            self.preset_btns.append(pbtn)
        
        layout.addWidget(self.preset_container)

        # Input Row
        self.input_container = QWidget()
        input_layout = QVBoxLayout(self.input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        self.input_lbl = QLabel("ระบุจำนวนเงินส่วนลด (บาท):")
        self.input_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #334155;")
        input_layout.addWidget(self.input_lbl)

        in_row = QHBoxLayout()
        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("0.00")
        in_row.addWidget(self.val_input, 1)

        self.unit_lbl = QLabel("บาท")
        self.unit_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #475569; min-width: 35px;")
        in_row.addWidget(self.unit_lbl)
        input_layout.addLayout(in_row)

        layout.addWidget(self.input_container)

        # Touch Keypad for POS touchscreen
        self.keypad_container = QWidget()
        keypad_grid = QGridLayout(self.keypad_container)
        keypad_grid.setContentsMargins(0, 0, 0, 0)
        keypad_grid.setSpacing(6)

        keys = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2), ("⌫", 0, 3),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2), ("C", 1, 3),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2), (".", 2, 3),
            ("0", 3, 0), ("00", 3, 1),
        ]

        for k, r, c in keys:
            btn = QPushButton(k)
            btn.setFixedHeight(40)
            if k == "C":
                btn.setStyleSheet("background-color: #fee2e2; color: #dc2626; font-size: 16px; font-weight: bold; border-radius: 6px; border: 1px solid #fecaca;")
                btn.clicked.connect(self.clear_keypad)
            elif k == "⌫":
                btn.setStyleSheet("background-color: #fef3c7; color: #d97706; font-size: 16px; font-weight: bold; border-radius: 6px; border: 1px solid #fde68a;")
                btn.clicked.connect(self.backspace_keypad)
            else:
                btn.setStyleSheet("background-color: #ffffff; color: #0f172a; font-size: 16px; font-weight: bold; border-radius: 6px; border: 1px solid #cbd5e1;")
                btn.clicked.connect(lambda checked, val=k: self.append_keypad(val))
            
            if k == "0":
                keypad_grid.addWidget(btn, r, c)
            elif k == "00":
                keypad_grid.addWidget(btn, r, c, 1, 2)
            else:
                keypad_grid.addWidget(btn, r, c)

        layout.addWidget(self.keypad_container)

        # Summary Preview Box
        preview_frame = QFrame()
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1.5px dashed #93c5fd;
                border-radius: 8px;
            }
        """)
        prev_layout = QVBoxLayout(preview_frame)
        prev_layout.setContentsMargins(12, 6, 12, 6)
        prev_layout.setSpacing(4)

        row_disc = QHBoxLayout()
        lbl_d = QLabel("ส่วนลดที่ได้รับ:")
        lbl_d.setStyleSheet("font-size: 13px; color: #475569;")
        self.preview_disc_lbl = QLabel("-฿0.00")
        self.preview_disc_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #dc2626;")
        self.preview_disc_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_disc.addWidget(lbl_d)
        row_disc.addWidget(self.preview_disc_lbl)
        prev_layout.addLayout(row_disc)

        row_net = QHBoxLayout()
        lbl_n = QLabel("ยอดสุทธิต้องชำระ:")
        lbl_n.setStyleSheet("font-size: 13.5px; font-weight: 700; color: #0f172a;")
        self.preview_net_lbl = QLabel(f"฿{self.subtotal:,.2f}")
        self.preview_net_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #16a34a;")
        self.preview_net_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_net.addWidget(lbl_n)
        row_net.addWidget(self.preview_net_lbl)
        prev_layout.addLayout(row_net)

        layout.addWidget(preview_frame)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("ยกเลิก")
        self.btn_cancel.setFixedHeight(44)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #334155;
                font-size: 14px;
                font-weight: 700;
                border-radius: 6px;
                border: 1px solid #cbd5e1;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel, 1)

        self.btn_ok = QPushButton("ตกลง / บันทึกส่วนลด")
        self.btn_ok.setFixedHeight(44)
        self.btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
                border-radius: 6px;
                border: 1px solid #1d4ed8;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
        """)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.on_confirm)
        btn_row.addWidget(self.btn_ok, 2)

        layout.addLayout(btn_row)

        # Signal connections
        self.btn_group.idClicked.connect(self.on_mode_changed)
        self.val_input.textChanged.connect(self.on_text_changed)
        self.val_input.returnPressed.connect(self.on_confirm)

        # Set initial mode
        if self.discount_label.endswith("%"):
            self.radio_pct.setChecked(True)
            try:
                self.val_input.setText(self.discount_label.rstrip("%"))
            except Exception:
                self.val_input.setText("")
            self.on_mode_changed(2)
        elif self.discount_amount > 0:
            self.radio_baht.setChecked(True)
            self.val_input.setText(f"{self.discount_amount:g}")
            self.on_mode_changed(1)
        else:
            self.radio_baht.setChecked(True)
            self.on_mode_changed(1)

    def on_mode_changed(self, mode_id):
        if mode_id == 1:  # Baht
            self.input_container.show()
            self.keypad_container.show()
            self.preset_container.show()
            self.input_lbl.setText("ระบุจำนวนเงินส่วนลด (บาท):")
            self.unit_lbl.setText("บาท")
            presets = [("10", "10"), ("20", "20"), ("50", "50"), ("100", "100"), ("200", "200"), ("500", "500")]
            self.current_presets = [v for _, v in presets]
            for idx, (label, _) in enumerate(presets):
                if idx < len(self.preset_btns):
                    self.preset_btns[idx].setText(label)
                    self.preset_btns[idx].show()
            self.val_input.setFocus()
        elif mode_id == 2:  # Percentage
            self.input_container.show()
            self.keypad_container.show()
            self.preset_container.show()
            self.input_lbl.setText("ระบุเปอร์เซ็นต์ส่วนลด (%):")
            self.unit_lbl.setText("%")
            presets = [("5%", "5"), ("10%", "10"), ("15%", "15"), ("20%", "20"), ("50%", "50")]
            self.current_presets = [v for _, v in presets]
            for idx, (label, _) in enumerate(presets):
                if idx < len(self.preset_btns):
                    self.preset_btns[idx].setText(label)
                    self.preset_btns[idx].show()
            if len(self.preset_btns) > len(presets):
                self.preset_btns[-1].hide()
            self.val_input.setFocus()
        else:  # Clear
            self.input_container.hide()
            self.keypad_container.hide()
            self.preset_container.hide()

        self.recalc()

    def on_preset_clicked(self, idx):
        if idx < len(self.current_presets):
            self.val_input.setText(self.current_presets[idx])
            self.recalc()

    def apply_preset(self, val):
        self.val_input.setText(val)
        self.recalc()

    def append_keypad(self, val):
        cur = self.val_input.text()
        if val == "." and "." in cur:
            return
        if cur == "0" and val != ".":
            new_val = val
        else:
            new_val = cur + val
        self.val_input.setText(new_val)

    def clear_keypad(self):
        self.val_input.setText("")

    def backspace_keypad(self):
        cur = self.val_input.text()
        if cur:
            self.val_input.setText(cur[:-1])

    def on_text_changed(self):
        self.recalc()

    def recalc(self):
        mode_id = self.btn_group.checkedId()
        if mode_id == 3:  # Clear
            self.preview_disc_lbl.setText("-฿0.00")
            self.preview_net_lbl.setText(f"฿{self.subtotal:,.2f}")
            return

        txt = self.val_input.text().strip()
        try:
            val = float(txt) if txt else 0.0
        except ValueError:
            val = 0.0

        if mode_id == 1:  # Baht
            disc = max(0.0, min(val, self.subtotal))
            net = max(0.0, self.subtotal - disc)
            self.preview_disc_lbl.setText(f"-฿{disc:,.2f}")
            self.preview_net_lbl.setText(f"฿{net:,.2f}")
        elif mode_id == 2:  # Percent
            pct = max(0.0, min(val, 100.0))
            disc = round(self.subtotal * (pct / 100.0), 2)
            disc = max(0.0, min(disc, self.subtotal))
            net = max(0.0, self.subtotal - disc)
            self.preview_disc_lbl.setText(f"-฿{disc:,.2f} ({pct:g}%)")
            self.preview_net_lbl.setText(f"฿{net:,.2f}")

    def on_confirm(self):
        mode_id = self.btn_group.checkedId()
        if mode_id == 3:  # Clear
            self.discount_amount = 0.0
            self.discount_label = ""
            self.accept()
            return

        txt = self.val_input.text().strip()
        try:
            val = float(txt) if txt else 0.0
        except ValueError:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุตัวเลขส่วนลดที่ถูกต้อง")
            return

        if val < 0:
            QMessageBox.warning(self, "แจ้งเตือน", "ส่วนลดต้องไม่ติดลบ")
            return

        if mode_id == 1:  # Baht
            if val > self.subtotal:
                QMessageBox.warning(self, "แจ้งเตือน", f"ส่วนลดต้องไม่เกินยอดรวม ฿{self.subtotal:,.2f}")
                return
            self.discount_amount = round(val, 2)
            self.discount_label = f"฿{self.discount_amount:,.2f}" if self.discount_amount > 0 else ""
        elif mode_id == 2:  # Percent
            if val > 100:
                QMessageBox.warning(self, "แจ้งเตือน", "เปอร์เซ็นต์ส่วนลดต้องไม่เกิน 100%")
                return
            calc_val = round(self.subtotal * (val / 100.0), 2)
            self.discount_amount = min(calc_val, self.subtotal)
            self.discount_label = f"{val:g}%" if self.discount_amount > 0 else ""

        self.accept()
