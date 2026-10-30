from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QFrame, QMessageBox, QWidget
)
from PySide6.QtCore import Qt

class ShiftOpenDialog(QDialog):
    def __init__(self, parent=None, cashier_name="Unknown", api_url="", pos_token="", branch_name="สำนักงานใหญ่"):
        self.api_url = api_url
        self.pos_token = pos_token
        self.selected_branch_id = None
        self.branch_name = branch_name
        super().__init__(parent)
        self.setWindowTitle("เปิดกะขาย")
        self.setFixedSize(500, 400)
        self.setStyleSheet("background-color: white; color: #111827; font-family: 'Segoe UI', sans-serif;")
        # Remove default title bar (optional, we use our own close button)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        
        self.opening_cash = 0.0
        self.opening_note = ""
        self.cashier_name = cashier_name
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header Area
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_lbl = QLabel("เปิดกะขาย")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #00643c;")
        
        close_btn = QPushButton("X")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("QPushButton { background-color: white; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 14px; } QPushButton:hover { background-color: #f3f4f6; }")
        close_btn.clicked.connect(self.reject)
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        main_layout.addWidget(header_widget)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #e5e7eb;")
        main_layout.addWidget(line)
        
        # Content Area
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Info Row
        info_layout = QHBoxLayout()
        left_info = QVBoxLayout()
        left_info.addWidget(QLabel("สาขา"))
        left_info.addWidget(QLabel("แคชเชียร์"))
        left_info.setSpacing(5)
        
        right_info = QVBoxLayout()
        r1 = QLabel(self.branch_name)
        r1.setAlignment(Qt.AlignRight)
        r1.setStyleSheet("font-weight: bold;")
        r2 = QLabel(self.cashier_name)
        r2.setAlignment(Qt.AlignRight)
        r2.setStyleSheet("font-weight: bold;")
        right_info.addWidget(r1)
        right_info.addWidget(r2)
        right_info.setSpacing(5)
        
        info_layout.addLayout(left_info)
        info_layout.addStretch()
        info_layout.addLayout(right_info)
        layout.addLayout(info_layout)
        
        # Opening Cash
        lbl1 = QLabel("เงินทอนตั้งต้น")
        lbl1.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl1)
        
        self.amount_input = QLineEdit()
        self.amount_input.setText("0")
        self.amount_input.setStyleSheet("font-size: 16px; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px;")
        layout.addWidget(self.amount_input)
        
        # Note
        lbl2 = QLabel("หมายเหตุเปิดกะ")
        lbl2.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(lbl2)
        
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("ไม่บังคับ")
        self.note_input.setStyleSheet("font-size: 16px; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px;")
        layout.addWidget(self.note_input)
        
        main_layout.addWidget(content)
        
        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(20, 10, 20, 20)
        
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setFixedSize(100, 48)
        cancel_btn.setStyleSheet("QPushButton { background-color: white; border: 1px solid #e5e7eb; border-radius: 8px; font-weight: bold; color: #4b5563; } QPushButton:hover { background-color: #f3f4f6; }")
        cancel_btn.clicked.connect(self.reject)
        
        confirm_btn = QPushButton("เปิดกะ")
        confirm_btn.setFixedHeight(48)
        confirm_btn.setStyleSheet("QPushButton { background-color: #10b981; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; } QPushButton:hover { background-color: #059669; }")
        confirm_btn.clicked.connect(self.on_confirm)
        
        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(confirm_btn)
        main_layout.addLayout(footer_layout)
        
    def on_confirm(self):
        try:
            val = self.amount_input.text().strip()
            self.opening_cash = float(val) if val else 0.0
            if self.opening_cash < 0:
                raise ValueError
            self.opening_note = self.note_input.text().strip()
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาใส่จำนวนเงินให้ถูกต้อง")

class ShiftCloseDialog(QDialog):
    def __init__(self, parent=None, expected_cash=0.0):
        super().__init__(parent)
        self.setWindowTitle("ปิดกะ (Close Shift)")
        self.setFixedSize(400, 300)
        self.setStyleSheet("background-color: white; color: #111827;")
        
        self.expected_cash = expected_cash
        self.counted_cash = 0.0
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("ปิดกะทำงาน")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #111827;")
        layout.addWidget(title, alignment=Qt.AlignCenter)
        
        info = QLabel(f"ยอดเงินในระบบ: ฿ {self.expected_cash:,.2f}")
        info.setStyleSheet("font-size: 16px; color: #4b5563; font-weight: bold;")
        layout.addWidget(info, alignment=Qt.AlignCenter)
        
        input_layout = QHBoxLayout()
        lbl = QLabel("ยอดเงินนับจริง:")
        lbl.setStyleSheet("font-size: 16px; color: #374151;")
        
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.amount_input.setStyleSheet("font-size: 20px; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px;")
        
        input_layout.addWidget(lbl)
        input_layout.addWidget(self.amount_input)
        layout.addLayout(input_layout)
        
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setStyleSheet("background-color: white; border: 1px solid #d1d5db; padding: 10px; border-radius: 8px; font-size: 16px; font-weight: bold;")
        cancel_btn.clicked.connect(self.reject)
        
        confirm_btn = QPushButton("ยืนยันปิดกะ")
        confirm_btn.setStyleSheet("background-color: #ef4444; color: white; border: none; padding: 10px; border-radius: 8px; font-size: 16px; font-weight: bold;")
        confirm_btn.clicked.connect(self.on_confirm)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)
        
    def on_confirm(self):
        try:
            val = self.amount_input.text().strip()
            if not val:
                raise ValueError
            self.counted_cash = float(val)
            if self.counted_cash < 0:
                raise ValueError
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาใส่ยอดเงินที่นับได้จริง")

