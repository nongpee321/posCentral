import sys
import os
import io
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QFrame)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QFont, QColor, QImage
import qrcode

def crc16(data: str) -> str:
    crc = 0xFFFF
    for char in data:
        crc ^= (ord(char) << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"

def generate_promptpay(promptpay_id: str, amount: float = 0) -> str:
    promptpay_id = ''.join(filter(str.isdigit, promptpay_id))
    target = f"0213{promptpay_id}" if len(promptpay_id) == 13 else f"01130066{promptpay_id[1:]}"
    merchant_info = f"0016A000000677010111{target}"
    payload = ["000201", "010212", f"29{len(merchant_info):02d}{merchant_info}", "5802TH", "5303764"]
    if amount > 0:
        amt_str = f"{amount:.2f}"
        payload.append(f"54{len(amt_str):02d}{amt_str}")
    payload.append("6304")
    data_to_crc = "".join(payload)
    return data_to_crc + crc16(data_to_crc)

class CustomerDisplayWindow(QMainWindow):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        self.setWindowTitle("Customer Display")
        self.setMinimumSize(1024, 768)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #f0f2f5; }
            QLabel { font-family: 'Tahoma', sans-serif; }
            
            QTableWidget { 
                background-color: white; 
                color: #1f2937;
                border: 1px solid #d1d5db; 
                border-radius: 8px;
                font-size: 20px;
                selection-background-color: transparent;
            }
            QTableWidget::item { padding: 15px; border-bottom: 1px solid #f3f4f6; }
            QHeaderView::section {
                background-color: #007934;
                color: white;
                font-size: 22px;
                font-weight: bold;
                border: none;
                padding: 12px;
            }
            
            #totalBox {
                background-color: white;
                border-radius: 12px;
                border: 2px solid #007934;
            }
            #totalLabelTitle {
                font-size: 28px;
                font-weight: bold;
                color: #374151;
                padding: 10px;
            }
            #totalLabelAmount {
                font-size: 80px;
                font-weight: 900;
                color: #E21B22;
                padding: 10px;
            }
            
            #statusLabel {
                font-size: 32px;
                font-weight: bold;
                color: #007934;
                padding: 10px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(30)
        
        left_panel = QVBoxLayout()
        welcome_lbl = QLabel("ยินดีต้อนรับ (Welcome)")
        welcome_lbl.setFont(QFont("Tahoma", 32, QFont.Bold))
        welcome_lbl.setStyleSheet("color: #007934; margin-bottom: 10px;")
        left_panel.addWidget(welcome_lbl)
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["รายการสินค้า", "จำนวน", "ราคา", "รวม"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        left_panel.addWidget(self.table)
        
        right_panel = QVBoxLayout()
        right_panel.setAlignment(Qt.AlignTop)
        
        total_box = QFrame()
        total_box.setObjectName("totalBox")
        total_box_layout = QVBoxLayout(total_box)
        total_box_layout.setAlignment(Qt.AlignCenter)
        
        self.status_lbl = QLabel("ยอดชำระสุทธิ (Total)")
        self.status_lbl.setObjectName("totalLabelTitle")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        total_box_layout.addWidget(self.status_lbl)
        
        self.total_lbl = QLabel("120.00")
        self.total_lbl.setObjectName("totalLabelAmount")
        self.total_lbl.setAlignment(Qt.AlignCenter)
        total_box_layout.addWidget(self.total_lbl)
        
        right_panel.addWidget(total_box)
        right_panel.addSpacing(30)
        
        self.qr_container = QWidget()
        qr_layout = QVBoxLayout(self.qr_container)
        qr_layout.setAlignment(Qt.AlignCenter)
        
        self.qr_title = QLabel("กรุณาสแกนจ่ายเงิน")
        self.qr_title.setObjectName("statusLabel")
        self.qr_title.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(self.qr_title)
        
        self.qr_image = QLabel()
        self.qr_image.setFixedSize(380, 380)
        self.qr_image.setScaledContents(True)
        self.qr_image.setStyleSheet("background-color: white; padding: 15px; border-radius: 12px; border: 3px solid #007934;")
        qr_layout.addWidget(self.qr_image)
        
        right_panel.addWidget(self.qr_container)
        
        self.thank_lbl = QLabel("ขอบคุณที่ใช้บริการ\\nโอกาสหน้าเชิญใหม่ครับ/ค่ะ")
        self.thank_lbl.setFont(QFont("Tahoma", 36, QFont.Bold))
        self.thank_lbl.setStyleSheet("color: #007934; margin-top: 50px;")
        self.thank_lbl.setAlignment(Qt.AlignCenter)
        self.thank_lbl.hide()
        right_panel.addWidget(self.thank_lbl)
        
        main_layout.addLayout(left_panel, 6)
        main_layout.addLayout(right_panel, 4)

        # Gen QR
        payload = generate_promptpay('0999999999', 120.00)
        qr_img = qrcode.make(payload)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue())
        self.qr_image.setPixmap(pix)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = CustomerDisplayWindow()
    w.show()
    sys.exit(app.exec())
