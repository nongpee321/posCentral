import sys
import os
import io
import time
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QAbstractItemView, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QDateTime
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
    if len(promptpay_id) >= 15:
        target = f"0315{promptpay_id}"
    elif len(promptpay_id) == 13:
        target = f"0213{promptpay_id}"
    elif len(promptpay_id) == 10:
        target = f"01130066{promptpay_id[1:]}"
    else:
        target = "01130066000000000"
    
    amount_str = f"{amount:.2f}"
    
    def tlv(tag, val):
        return f"{tag}{len(val):02d}{val}"
        
    merchant_acct = tlv('00', 'A000000677010111') + target
    
    payload = (
        tlv('00', '01') +
        tlv('01', '12') +
        tlv('29', merchant_acct) +
        tlv('53', '764') +
        tlv('54', amount_str) +
        tlv('58', 'TH') +
        tlv('59', 'PopCentral') +
        tlv('60', 'BANGKOK') +
        "6304"
    )
    return payload + crc16(payload)

class CustomerDisplayWindow(QMainWindow):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.config = main_window.config if main_window else {}
        self.setWindowTitle("Customer Display - PopCentral POS")
        self.resize(1024, 768)
        self.setStyleSheet("QMainWindow { background-color: #f1f5f9; }")

        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 8, 12, 6)
        main_layout.setSpacing(6)

        # ---------------- HEADER ----------------
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignTop)
        
        welcome_lbl = QLabel("ยินดีต้อนรับ (Welcome)")
        welcome_lbl.setStyleSheet("font-size: 24px; font-weight: 900; color: #059669; margin: 0px; padding: 0px;")
        header_layout.addWidget(welcome_lbl, 0, Qt.AlignVCenter)
        
        header_layout.addStretch()
        
        self.fullscreen_btn = QPushButton("เต็มจอ (Fullscreen)")
        self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self.fullscreen_btn.setFixedHeight(34)
        self.fullscreen_btn.setStyleSheet("""
            QPushButton {
                background-color: #047857;
                color: white;
                border: none;
                border-radius: 17px;
                padding: 6px 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        header_layout.addWidget(self.fullscreen_btn, 0, Qt.AlignVCenter)
        header_layout.addSpacing(10)
        
        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet("background-color: white; border: 1px solid #e2e8f0; border-radius: 15px; padding: 5px 15px; font-size: 14px; font-weight: bold; color: #334155;")
        header_layout.addWidget(self.clock_lbl, 0, Qt.AlignVCenter)
        
        main_layout.addLayout(header_layout)

        # ---------------- CONTENT AREA ----------------
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # LEFT PANEL (Cart)
        left_panel = QFrame()
        left_panel.setStyleSheet("QFrame { background-color: white; border-radius: 10px; border: 1px solid #e2e8f0; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        tbl_header_frame = QFrame()
        tbl_header_frame.setStyleSheet("QFrame { background-color: #059669; border-top-left-radius: 10px; border-top-right-radius: 10px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; }")
        tbl_header_layout = QHBoxLayout(tbl_header_frame)
        tbl_header_layout.setContentsMargins(15, 10, 15, 10)
        
        lbl_h1 = QLabel("รายการสินค้า")
        lbl_h2 = QLabel("จำนวน")
        lbl_h3 = QLabel("ราคา")
        lbl_h4 = QLabel("รวม")
        for lbl in [lbl_h1, lbl_h2, lbl_h3, lbl_h4]:
            lbl.setStyleSheet("color: white; font-weight: bold; font-size: 15px; border: none; background: transparent;")
        
        lbl_h2.setFixedWidth(60)
        lbl_h3.setFixedWidth(80)
        lbl_h4.setFixedWidth(90)
        lbl_h2.setAlignment(Qt.AlignCenter)
        lbl_h3.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_h4.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        tbl_header_layout.addWidget(lbl_h1)
        tbl_header_layout.addWidget(lbl_h2)
        tbl_header_layout.addWidget(lbl_h3)
        tbl_header_layout.addWidget(lbl_h4)
        left_layout.addWidget(tbl_header_frame)

        self.table = QTableWidget(0, 4)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        # Rounded bottom corners for table area since footer is removed
        self.table.setStyleSheet("QTableWidget { border: none; background-color: white; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; } QTableWidget::item { border-bottom: 1px solid #f1f5f9; padding: 5px; }")
        
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.Fixed)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 90)
        
        left_layout.addWidget(self.table)
        content_layout.addWidget(left_panel, 6)

        # RIGHT PANEL
        right_panel = QVBoxLayout()
        right_panel.setSpacing(6)
        # REMOVED right_panel.setAlignment(Qt.AlignTop)

        total_box = QFrame()
        total_box.setStyleSheet("QFrame { background-color: white; border-radius: 10px; border: 2px solid #10b981; }")
        total_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        total_layout = QVBoxLayout(total_box)
        total_layout.setContentsMargins(10, 8, 10, 8)
        total_layout.setSpacing(3)
        
        total_title = QLabel("ยอดชำระสุทธิ (Total)")
        total_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1e293b; border: none;")
        total_title.setAlignment(Qt.AlignCenter)
        total_layout.addWidget(total_title)
        
        self.total_lbl = QLabel("0.00")
        self.total_lbl.setStyleSheet("font-size: 42px; font-weight: 900; color: #dc2626; border: none; font-family: Arial;")
        self.total_lbl.setAlignment(Qt.AlignCenter)
        total_layout.addWidget(self.total_lbl)
        
        total_currency = QLabel("● สกุลเงิน: บาท (THB)")
        total_currency.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; border: none;")
        total_currency.setAlignment(Qt.AlignCenter)
        total_layout.addWidget(total_currency)
        
        subtotal_frame = QFrame()
        subtotal_frame.setStyleSheet("QFrame { background-color: #f0fdf4; border-radius: 8px; border: none; margin-top: 4px; }")
        subtotal_layout = QHBoxLayout(subtotal_frame)
        subtotal_layout.setContentsMargins(8, 4, 8, 4)
        
        sub1 = QVBoxLayout()
        lbl_s1 = QLabel("ราคาก่อนภาษี")
        lbl_s1.setStyleSheet("color: #475569; font-size: 11px; font-weight: bold;")
        self.subtotal_lbl = QLabel("0.00 ฿")
        self.subtotal_lbl.setStyleSheet("color: #1e293b; font-size: 13px; font-weight: bold;")
        sub1.addWidget(lbl_s1)
        sub1.addWidget(self.subtotal_lbl)
        
        sub2 = QVBoxLayout()
        lbl_s2 = QLabel("VAT 7%")
        lbl_s2.setStyleSheet("color: #475569; font-size: 11px; font-weight: bold;")
        self.vat_lbl = QLabel("0.00 ฿")
        self.vat_lbl.setStyleSheet("color: #1e293b; font-size: 13px; font-weight: bold;")
        sub2.addWidget(lbl_s2)
        sub2.addWidget(self.vat_lbl)
        
        sub3 = QVBoxLayout()
        lbl_s3 = QLabel("ส่วนลด")
        lbl_s3.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        self.disc_lbl = QLabel("0.00 ฿")
        self.disc_lbl.setStyleSheet("color: #10b981; font-size: 13px; font-weight: bold;")
        sub3.addWidget(lbl_s3)
        sub3.addWidget(self.disc_lbl)
        
        subtotal_layout.addLayout(sub1)
        subtotal_layout.addLayout(sub2)
        subtotal_layout.addLayout(sub3)
        
        total_layout.addWidget(subtotal_frame)
        right_panel.addWidget(total_box)

        # QR BOX
        self.qr_box = QFrame()
        self.qr_box.setStyleSheet("QFrame { background-color: white; border-radius: 10px; border: 1px solid #cbd5e1; }")
        self.qr_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        qr_layout = QVBoxLayout(self.qr_box)
        qr_layout.setContentsMargins(10, 6, 10, 6)
        qr_layout.setSpacing(3)
        
        qr_h = QHBoxLayout()
        qr_badge = QLabel("THAI QR")
        qr_badge.setStyleSheet("background-color: #1e3a8a; color: white; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 11px;")
        qr_title = QLabel("พร้อมเพย์ (PromptPay)")
        qr_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #1e293b; border: none;")
        qr_status = QLabel("รอสแกน")
        qr_status.setStyleSheet("background-color: #d1fae5; color: #059669; border-radius: 6px; padding: 2px 8px; font-weight: bold; font-size: 11px;")
        
        qr_h.addWidget(qr_badge)
        qr_h.addWidget(qr_title)
        qr_h.addStretch()
        qr_h.addWidget(qr_status)
        qr_layout.addLayout(qr_h, 0)
        
        qr_body = QVBoxLayout()
        qr_body.setSpacing(4)
        qr_body.setAlignment(Qt.AlignCenter)
        
        self.qr_image = QLabel()
        self.qr_image.setFixedSize(210, 210)
        self.qr_image.setStyleSheet("border: 1.5px solid #e2e8f0; border-radius: 6px; padding: 3px; background: white;")
        self.qr_image.setScaledContents(True)
        
        self.qr_timer_lbl = QLabel("")
        self.qr_timer_lbl.setStyleSheet("""
            background-color: #fee2e2;
            color: #dc2626;
            font-size: 15px;
            font-weight: bold;
            border: 1px solid #fecaca;
            border-radius: 6px;
            padding: 3px 14px;
            margin-top: 2px;
        """)
        self.qr_timer_lbl.setAlignment(Qt.AlignCenter)
        
        qr_body.addWidget(self.qr_image, 0, Qt.AlignCenter)
        qr_body.addWidget(self.qr_timer_lbl, 0, Qt.AlignCenter)
        
        qr_layout.addLayout(qr_body, 0)
        
        right_panel.addWidget(self.qr_box, 0)
        
        self.spacer_widget = QWidget()
        self.spacer_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        right_panel.addWidget(self.spacer_widget, 1)
        right_panel.addStretch(1)
        content_layout.addLayout(right_panel, 5)

        main_layout.addLayout(content_layout)
        
        footer_frame = QFrame()
        footer_frame.setFixedHeight(22)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_online = QLabel("● Online Connected")
        lbl_online.setStyleSheet("color: #059669; font-weight: bold; font-size: 12px;")
        
        self.cashier_lbl = QLabel("แคชเชียร์: STAFF")
        self.cashier_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        
        lbl_version = QLabel("PopCentral POS • PySide6 GUI Runtime")
        lbl_version.setStyleSheet("color: #94a3b8; font-size: 12px;")
        
        footer_layout.addWidget(lbl_online)
        footer_layout.addSpacing(10)
        footer_layout.addWidget(self.cashier_lbl)
        footer_layout.addStretch()
        footer_layout.addWidget(lbl_version)
        
        main_layout.addWidget(footer_frame)

        self.current_total = 0.0
        self.qr_box.hide()
        self.spacer_widget.show()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

    def update_time(self):
        dt = QDateTime.currentDateTime()
        self.clock_lbl.setText(f"●  {dt.toString('dd/MM/yyyy • HH:mm:ss')}")

    def update_timer(self, seconds):
        if seconds > 0:
            self.qr_timer_lbl.setText(f"หมดเวลาใน: {seconds} วินาที")
        else:
            self.qr_timer_lbl.setText("หมดเวลาชำระเงิน")

    def update_cart(self, table_widget, total_amount, subtotal=0.0, discount=0.0):
        total_val = float(total_amount or 0.0)
        disc_val = float(discount or 0.0)
        self.current_total = total_val
        self.qr_box.hide()
        self.spacer_widget.show()
        
        self.total_lbl.setText(f"{total_val:,.2f}")
        self.total_lbl.setStyleSheet("font-size: 42px; font-weight: 900; color: #dc2626; border: none; font-family: Arial;")
        self.disc_lbl.setText(f"{disc_val:,.2f} ฿")
        
        if total_val > 0:
            sub = total_val / 1.07
            vat = total_val - sub
            self.subtotal_lbl.setText(f"{sub:,.2f} ฿")
            self.vat_lbl.setText(f"{vat:,.2f} ฿")
        else:
            self.subtotal_lbl.setText("0.00 ฿")
            self.vat_lbl.setText("0.00 ฿")
        
        self.table.setRowCount(0)
        rows = table_widget.rowCount()
        for i in range(rows):
            self.table.insertRow(i)
            self.table.setRowHeight(i, 40)
            
            name = table_widget.item(i, 0).text() if table_widget.item(i, 0) else ""
            qty_str = table_widget.item(i, 1).text() if table_widget.item(i, 1) else "0"
            price = table_widget.item(i, 2).text() if table_widget.item(i, 2) else ""
            total = table_widget.item(i, 3).text() if table_widget.item(i, 3) else ""
            
            ni = QTableWidgetItem(name)
            ni.setFont(QFont("Arial", 12, QFont.Bold))
            ni.setForeground(QColor("#1e293b"))
            self.table.setItem(i, 0, ni)
            
            qi = QTableWidgetItem(qty_str)
            qi.setFont(QFont("Arial", 12, QFont.Bold))
            qi.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, qi)
            
            pi = QTableWidgetItem(price)
            pi.setFont(QFont("Arial", 11))
            pi.setForeground(QColor("#64748b"))
            pi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, pi)
            
            ti = QTableWidgetItem(total)
            ti.setFont(QFont("Arial", 12, QFont.Bold))
            ti.setForeground(QColor("#1e293b"))
            ti.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, ti)

    def generate_qr_image(self, amount):
        promptpay_id = self.config.get('promptpay_id', '0999999999')
        payload = generate_promptpay(promptpay_id, amount)
        qr_img = qrcode.make(payload)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

    def show_payment(self, method="QR", override_amount=None, discount=None):
        if isinstance(method, (int, float)):
            override_amount = float(method)
            method = "QR"
        amt = float(override_amount if override_amount is not None else self.current_total)
        self.current_total = amt
        self.total_lbl.setText(f"{amt:,.2f}")

        if discount is not None:
            self.disc_lbl.setText(f"{float(discount):,.2f} ฿")

        if amt > 0:
            sub = amt / 1.07
            vat = amt - sub
            self.subtotal_lbl.setText(f"{sub:,.2f} ฿")
            self.vat_lbl.setText(f"{vat:,.2f} ฿")
        else:
            self.subtotal_lbl.setText("0.00 ฿")
            self.vat_lbl.setText("0.00 ฿")

        if method == "QR":
            try:
                pixmap = self.generate_qr_image(amt)
                self.qr_image.setPixmap(pixmap)
                self.qr_timer_lbl.setText("พร้อมเพย์ (PromptPay)")
            except Exception as e:
                print(e)
            self.spacer_widget.hide()
            self.qr_box.show()
        else:
            self.qr_box.hide()
            self.spacer_widget.show()

    def show_success(self, change=0):
        self.table.setRowCount(0)
        self.qr_box.hide()
        self.spacer_widget.show()
        self.total_lbl.setStyleSheet("font-size: 42px; font-weight: 900; color: #10b981; border: none; font-family: Arial;")
        self.total_lbl.setText(f"{change:,.2f}")
        self.disc_lbl.setText("0.00 ฿")
        self.subtotal_lbl.setText("0.00 ฿")
        self.vat_lbl.setText("0.00 ฿")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_btn.setText("เต็มจอ (Fullscreen)")
            self.fullscreen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #047857;
                    color: white;
                    border: none;
                    border-radius: 17px;
                    padding: 6px 18px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #059669;
                }
            """)
        else:
            self.showFullScreen()
            self.fullscreen_btn.setText("ย่อจอ (Exit Fullscreen)")
            self.fullscreen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #475569;
                    color: white;
                    border: none;
                    border-radius: 17px;
                    padding: 6px 18px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #334155;
                }
            """)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            return
        elif event.key() == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            return
        super().keyPressEvent(event)
