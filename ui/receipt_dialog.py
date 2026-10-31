# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QDialog, QHBoxLayout, QVBoxLayout, QFrame,

                               QFormLayout, QComboBox, QLineEdit, QTextEdit, QSpinBox,

                               QPushButton, QLabel, QScrollArea, QWidget, QMessageBox)

from PySide6.QtCore import Qt, QLocale, QUrl, QTimer, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from PySide6.QtGui import QFont

from PySide6.QtPrintSupport import QPrinterInfo

import os

import json
import html
import sys
from decimal import Decimal
from datetime import datetime

def _receipt_amount(value):
    return Decimal(str(value or 0))

def _payment_method_label(method):
    labels = {
        'cash': 'เงินสด',
        'transfer': 'โอนเงิน/QR',
        'mixed': 'เงินสด + โอนเงิน/QR',
        'split': 'เงินสด + โอนเงิน/QR',
        'เงินสด': 'เงินสด',
        'ผสม (Split)': 'เงินสด + โอนเงิน/QR',
    }
    return labels.get(method, str(method or 'ไม่ระบุ'))

def _receipt_date_label(value):
    date_text = str(value or '-')
    try:
        date = datetime.fromisoformat(date_text)
    except ValueError:
        return date_text
    thai_year = date.year + 543
    return date.strftime('%d/%m/') + f'{thai_year:04d} ' + date.strftime('%H:%M')

def _format_receipt_qty(qty_value):
    from decimal import ROUND_FLOOR
    qty_dec = _receipt_amount(qty_value)
    if qty_dec == int(qty_dec):
        return f"{int(qty_dec)}"
    first_dec = (qty_dec * Decimal('10')).to_integral_value(rounding=ROUND_FLOOR) / Decimal('10')
    return f"{first_dec:.1f} **"

def _format_total_qty(qty_value):
    qty_dec = _receipt_amount(qty_value).quantize(Decimal('0.001')).normalize()
    if qty_dec == int(qty_dec):
        return f"{int(qty_dec)}"
    text = f"{qty_dec:f}"
    return text.rstrip('0').rstrip('.') if '.' in text else text

def _truncate_thai_visual(text, max_visual_chars):
    import unicodedata
    out = []
    vis = 0
    for ch in str(text or ''):
        if unicodedata.category(ch) != 'Mn':
            if vis >= max_visual_chars:
                break
            vis += 1
        out.append(ch)
    return "".join(out)

def _logo_path():
    app_directory = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(__file__))
    return os.path.join(app_directory, 'assets', 'logo.png')

def _escpos_logo():
    path = _logo_path()
    if not os.path.isfile(path):
        return b''

    from PIL import Image

    image = Image.open(path).convert('L')
    content = image.point(lambda pixel: 255 if pixel < 245 else 0).getbbox()
    if content:
        image = image.crop(content)
    target_width = 128
    target_height = max(1, round(image.height * target_width / image.width))
    image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
    pixels = image.point(lambda pixel: 0 if pixel < 180 else 1, mode='1')
    row_bytes = (target_width + 7) // 8
    raster = bytearray()
    for y in range(target_height):
        for byte_index in range(row_bytes):
            value = 0
            for bit in range(8):
                x = byte_index * 8 + bit
                if x < target_width and pixels.getpixel((x, y)) == 0:
                    value |= 1 << (7 - bit)
            raster.append(value)

    width_low, width_high = row_bytes & 0xFF, row_bytes >> 8
    height_low, height_high = target_height & 0xFF, target_height >> 8
    return b'\x1dv0\x00' + bytes((width_low, width_high, height_low, height_high)) + bytes(raster) + b'\n'

def _receipt_raster_commands(document, paper_size='80mm'):
    doc_size = document.documentLayout().documentSize()
    source_width = max(document.textWidth(), doc_size.width())
    if source_width <= 0:
        raise ValueError("เอกสารใบเสร็จไม่มีความกว้างที่ถูกต้อง")
    paper_width = 384 if paper_size == '58mm' else 576
    target_width = 350 if paper_size == '58mm' else 525
    scale = target_width / source_width
    offset_x = max(0, (paper_width - int(source_width * scale)) // 2)
    source_height = doc_size.height()
    image_height = max(1, int(source_height * scale) + 16)
    image = QImage(paper_width, image_height, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
    painter.translate(offset_x, 8)
    painter.scale(scale, scale)
    document.drawContents(painter, QRectF(0, 0, source_width, source_height))
    painter.end()

    row_bytes = (paper_width + 7) // 8
    # ESC @ (init), ESC a 1 (center)
    commands = bytearray(b'\x1b@\x1ba\x01')
    for start_y in range(0, image_height, 128):
        band_height = min(128, image_height - start_y)
        commands.extend((
            0x1D, 0x76, 0x30, 0x00,
            row_bytes & 0xFF, row_bytes >> 8,
            band_height & 0xFF, band_height >> 8,
        ))
        for y in range(start_y, start_y + band_height):
            for byte_index in range(row_bytes):
                value = 0
                for bit in range(8):
                    x = byte_index * 8 + bit
                    # Threshold 225: any pixel darker than near-white turns solid black
                    if x < paper_width and image.pixelColor(x, y).value() < 225:
                        value |= 1 << (7 - bit)
                commands.append(value)

    commands.extend(b'\n\x1dVA\x03')
    return bytes(commands)

def _send_raw_to_printer(printer_name, commands):
    try:
        import win32print
    except ImportError:
        raise Exception("ไม่พบโมดูล win32print กรุณาติดตั้ง pypiwin32")

    try:
        printer = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(printer, 1, ("PopCentralPOS Receipt", None, "RAW"))
            win32print.StartPagePrinter(printer)
            win32print.WritePrinter(printer, commands)
            win32print.EndPagePrinter(printer)
            win32print.EndDocPrinter(printer)
        finally:
            win32print.ClosePrinter(printer)
    except Exception as error:
        raise Exception(f"ไม่สามารถส่งข้อมูลไปที่เครื่องพิมพ์ '{printer_name}' ได้: {str(error)}")

def _resolve_paper_size(config, printer_name=''):
    cfg = config or {}
    if cfg.get('receipt_paper_size_v110_user_set') and cfg.get('receipt_paper_size') in ('58mm', '80mm'):
        return cfg['receipt_paper_size']
    return '80mm'

def print_escpos_receipt(printer_name, receipt_data, config):
    if not printer_name:
        raise Exception("กรุณาเลือกเครื่องพิมพ์ก่อน")

    copies = int(config.get('receipt_copies', 1) or 1)
    if copies < 1:
        copies = 1

    document = config.get('_receipt_document')
    if document is not None:
        paper_size = _resolve_paper_size(config, printer_name)
        raster_cmds = _receipt_raster_commands(document, paper_size)
        for _ in range(copies):
            _send_raw_to_printer(printer_name, raster_cmds)
        return

    def enc(text):

        try:

            return text.encode('tis-620', errors='replace')

        except LookupError:

            return text.encode('cp874', errors='replace')

    

    header_text = config.get('receipt_header', '')

    if not header_text:

        header_text = "บริษัท ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง จำกัด\n480 ถนนวารินชำราบ-ศรีสะเกษ ม.1 ต.แสนสุข\nอ.วารินชำราบ จ.อุบลราชธานี 34190\nโทร. 061-935-4497 | Line: @popstarshop"

        

    footer_text = config.get('receipt_footer', '')

    if not footer_text:

        footer_text = "ขอบคุณที่ใช้บริการ\nโอกาสหน้าเชิญใหม่ครับ/ค่ะ"

    branch = receipt_data.get('branch', 'สำนักงานใหญ่')

    cashier = receipt_data.get('cashier', 'พนักงาน')

    receipt_no = receipt_data.get('doc_number', '-')

    date_str = _receipt_date_label(receipt_data.get('date', '-'))

    total_amount = receipt_data.get('total', 0.0)

    

    pm = receipt_data.get('payment_method', 'cash')
    method_str = _payment_method_label(pm)

    

    is_full_tax = receipt_data.get('is_full_tax', False)

    cust_name = receipt_data.get('customer_name', '') or ''

    cust_tax = receipt_data.get('customer_tax_id', '') or ''

    cust_addr = receipt_data.get('customer_address', '') or ''

    

    ESC = b'\x1b'

    GS  = b'\x1d'

    INIT          = ESC + b'@'
    ALIGN_LEFT    = ESC + b'a\x00'
    ALIGN_CENTER  = ESC + b'a\x01'
    ALIGN_RIGHT   = ESC + b'a\x02'
    FONT_SMALL    = ESC + b'M\x01'
    FONT_NORMAL   = ESC + b'M\x00'

    BOLD_ON       = ESC + b'E\x01'

    BOLD_OFF      = ESC + b'E\x00'

    DOUBLE_ON     = GS  + b'!\x11'

    DOUBLE_OFF    = GS  + b'!\x00'

    LINE_FEED     = b'\n'

    CUT_PAPER     = GS  + b'V\x41\x03'
    OPEN_DRAWER_1 = ESC + b'p\x00\x19\xfa'
    OPEN_DRAWER_2 = ESC + b'p\x01\x19\xfa'

    

    cmds = bytearray()

    cmds += INIT

    # Auto-kick cash drawer on printing receipt for cash or split payment
    pm_code = str(receipt_data.get('payment_method', '')).lower()
    if pm_code in ['cash', 'split', 'mixed', 'เงินสด', 'ผสม (split)', 'ผสม'] or config.get('open_drawer_on_print', True):
        cmds += get_drawer_kick_commands()

    cmds += FONT_SMALL
    
    cmds += ALIGN_CENTER

    cmds += _escpos_logo()
    
    cmds += BOLD_ON
    for line in header_text.split('\n'):

        cmds += enc(line) + LINE_FEED
    cmds += BOLD_OFF
    cmds += enc("ใบกำกับภาษีอย่างย่อ") + LINE_FEED

        

    

    cmds += ALIGN_LEFT
    if is_full_tax:
        cmds += enc(f"นามลูกค้า: {cust_name}") + LINE_FEED
        cmds += enc(f"เลขผู้เสียภาษี: {cust_tax}") + LINE_FEED
        cmds += enc(f"ที่อยู่: {cust_addr}") + LINE_FEED
        cmds += enc("-" * 48) + LINE_FEED
        
    cmds += enc(f"สาขา: {branch}    แคชเชียร์: {cashier}") + LINE_FEED
    cmds += enc(f"เลขที่: {receipt_no}") + LINE_FEED
    cmds += ALIGN_RIGHT
    cmds += enc(f"วันที่: {date_str}") + LINE_FEED
    cmds += ALIGN_LEFT
    cmds += enc("-" * 48) + LINE_FEED
    for item in receipt_data.get('items', []):
        name  = item.get('name', '')
        qty   = item.get('qty', 1)
        price = item.get('price', 0.0)
        total = item.get('total', 0.0)
        name_text = str(name)[:32]
        total_text = f"{total:,.2f}"
        padding = max(1, 48 - len(name_text) - len(total_text))
        cmds += enc(name_text + " " * padding + total_text) + LINE_FEED
        cmds += enc(f"  {qty} x {price:,.2f}") + LINE_FEED
    
    cmds += enc('-' * 48) + LINE_FEED
    
    subtotal = sum(float(it.get('total', 0.0)) for it in receipt_data.get('items', []))
    discount = float(receipt_data.get('discount_amount', 0.0))
    if discount > 0:
        cmds += enc(f"รวมเป็นเงิน: {subtotal:,.2f}") + LINE_FEED
        cmds += enc(f"ส่วนลด: -{discount:,.2f}") + LINE_FEED
        cmds += enc('-' * 48) + LINE_FEED
    
    vat_rate = _receipt_amount(receipt_data.get('vat_rate', 7))
    net_amount = _receipt_amount(total_amount)
    vat_amount = net_amount * vat_rate / (Decimal('100') + vat_rate) if vat_rate else Decimal('0')
    before_vat = net_amount - vat_amount
    cmds += enc(f"มูลค่าสินค้า (ก่อน VAT) {before_vat:,.2f}") + LINE_FEED
    cmds += enc(f"ภาษีมูลค่าเพิ่ม {vat_rate}% {vat_amount:,.2f}") + LINE_FEED
    cmds += ALIGN_CENTER
    cmds += BOLD_ON
    cmds += FONT_NORMAL
    cmds += enc(f'ยอดสุทธิ {net_amount:,.2f} บาท') + LINE_FEED
    cmds += FONT_SMALL
    cmds += BOLD_OFF
    cmds += ALIGN_CENTER
    cmds += enc('(รวมภาษีมูลค่าเพิ่มแล้ว)') + LINE_FEED
    cmds += enc(f'ชำระโดย: {method_str}') + LINE_FEED
    cmds += enc('-' * 48) + LINE_FEED

    

    cmds += BOLD_ON

    for line in footer_text.split('\n'):

        cmds += enc(line) + LINE_FEED

    cmds += BOLD_OFF

    cmds += LINE_FEED * 3

    cmds += CUT_PAPER

    

    try:

        import win32print

    except ImportError:

        raise Exception("ไม่พบโมดูล win32print กรุณาติดตั้ง pypiwin32")

    if not printer_name:

        raise Exception("กรุณาเลือกเครื่องพิมพ์ก่อน")

    try:

        hPrinter = win32print.OpenPrinter(printer_name)

        try:
            for _ in range(copies):
                win32print.StartDocPrinter(hPrinter, 1, ("PopCentralPOS Receipt", None, "RAW"))
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, bytes(cmds))
                win32print.EndPagePrinter(hPrinter)
                win32print.EndDocPrinter(hPrinter)

        finally:

            win32print.ClosePrinter(hPrinter)

    except Exception as e:

        raise Exception(f"ไม่สามารถส่งข้อมูลไปที่เครื่องพิมพ์ '{printer_name}' ได้: {str(e)}")

def get_drawer_kick_commands():
    ESC = b'\x1b'
    DLE = b'\x10'
    cmds = bytearray()
    cmds += ESC + b'@'                    # Initialize printer
    cmds += ESC + b'p\x00\x19\xfa'        # Pin 2 standard ESC/POS pulse (50ms on / 500ms off)
    cmds += ESC + b'p\x01\x19\xfa'        # Pin 5 standard ESC/POS pulse (50ms on / 500ms off)
    cmds += ESC + b'p\x00\x32\x32'        # Pin 2 pulse variant (50ms on / 50ms off)
    cmds += ESC + b'p\x01\x32\x32'        # Pin 5 pulse variant (50ms on / 50ms off)
    cmds += DLE + b'\x14\x01\x00\x05'    # DLE DC4 real-time pulse (Pin 2)
    cmds += DLE + b'\x14\x01\x01\x05'    # DLE DC4 real-time pulse (Pin 5)
    cmds += b'\x07'                       # BEL (Star / generic pulse)
    return bytes(cmds)

def open_cash_drawer(printer_name):
    try:
        import win32print
    except ImportError:
        raise Exception("Cannot import win32print")

    if not printer_name:
        raise Exception("No printer configured")

    cmds = get_drawer_kick_commands()

    try:
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("PopCentralPOS OpenDrawer", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, bytes(cmds))
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
        return True
    except Exception as e:
        raise Exception(f"Failed to open drawer: {str(e)}")

class ReceiptSettingsDialog(QDialog):
    def __init__(self, parent=None, config=None, receipt_data=None):
        super().__init__(parent)
        self.setWindowTitle("ตั้งค่าเครื่องพิมพ์ใบเสร็จ")
        self.setFixedSize(540, 370)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            }
            QLabel {
                color: #1e293b;
            }
            QComboBox {
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 14px;
                font-weight: 500;
                background-color: #f8fafc;
                color: #0f172a;
            }
            QComboBox:focus {
                border-color: #2563eb;
                background-color: #ffffff;
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
            }
            QSpinBox {
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 16px;
                font-weight: bold;
                background-color: #f8fafc;
                color: #0f172a;
            }
            QSpinBox:focus {
                border-color: #2563eb;
                background-color: #ffffff;
            }
        """)

        self.config = dict(config or {})
        self.receipt_data = receipt_data or {}
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(16)

        # Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_lbl = QLabel("ตั้งค่าเครื่องพิมพ์ใบเสร็จ")
        title_lbl.setStyleSheet("font-size: 19px; font-weight: bold; color: #0f172a;")
        sub_lbl = QLabel("เลือกเครื่องพิมพ์และจำนวนใบเสร็จที่ต้องการพิมพ์")
        sub_lbl.setStyleSheet("font-size: 13px; color: #64748b;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        main_layout.addLayout(title_box)

        # Divider line
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFrameShadow(QFrame.Sunken)
        div.setStyleSheet("color: #e2e8f0; background-color: #e2e8f0; max-height: 1px;")
        main_layout.addWidget(div)

        # 1. Printer selection
        printer_layout = QVBoxLayout()
        printer_layout.setSpacing(6)
        lbl_printer = QLabel("เลือกเครื่องพิมพ์:")
        lbl_printer.setStyleSheet("font-size: 14px; font-weight: bold; color: #1e293b;")
        self.printer_combo = QComboBox()
        self.printer_combo.setFixedHeight(42)
        self.printer_combo.addItem("--- กรุณาเลือกเครื่องพิมพ์ ---")
        for printer in QPrinterInfo.availablePrinters():
            self.printer_combo.addItem(printer.printerName())

        current_printer = self.config.get('receipt_printer', '')
        if current_printer:
            idx = self.printer_combo.findText(current_printer)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)

        printer_layout.addWidget(lbl_printer)
        printer_layout.addWidget(self.printer_combo)
        main_layout.addLayout(printer_layout)

        # 2. Number of copies
        copies_layout = QVBoxLayout()
        copies_layout.setSpacing(6)
        lbl_copies = QLabel("จำนวนให้พิมพ์ (ฉบับ/บิล):")
        lbl_copies.setStyleSheet("font-size: 14px; font-weight: bold; color: #1e293b;")

        copies_ctrl_layout = QHBoxLayout()
        copies_ctrl_layout.setSpacing(8)

        self.copies_spin = QSpinBox()
        self.copies_spin.setFixedHeight(42)
        self.copies_spin.setRange(1, 10)
        self.copies_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        current_copies = int(self.config.get('receipt_copies', 1) or 1)
        self.copies_spin.setValue(max(1, min(10, current_copies)))
        self.copies_spin.setSuffix(" ใบ")
        copies_ctrl_layout.addWidget(self.copies_spin, 2)

        for num in [1, 2, 3]:
            btn = QPushButton(f"{num} ใบ")
            btn.setFixedHeight(42)
            btn.setFixedWidth(56)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9; border: 1px solid #cbd5e1;
                    color: #334155; font-size: 13px; font-weight: bold; border-radius: 8px;
                }
                QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
            """)
            btn.clicked.connect(lambda checked=False, n=num: self.copies_spin.setValue(n))
            copies_ctrl_layout.addWidget(btn)

        copies_layout.addWidget(lbl_copies)
        copies_layout.addLayout(copies_ctrl_layout)
        main_layout.addLayout(copies_layout)

        main_layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setFixedHeight(42)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; border: 1px solid #cbd5e1; color: #475569;
                font-size: 13px; font-weight: bold; border-radius: 8px; padding: 0 14px;
            }
            QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }
        """)
        cancel_btn.clicked.connect(self.reject)

        test_btn = QPushButton("ทดสอบพิมพ์")
        test_btn.setFixedHeight(42)
        test_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0fdf4; border: 1px solid #86efac; color: #166534;
                font-size: 13px; font-weight: bold; border-radius: 8px; padding: 0 14px;
            }
            QPushButton:hover { background-color: #dcfce7; }
        """)
        test_btn.clicked.connect(lambda: self.save_settings(and_test=True))

        save_btn = QPushButton("บันทึกการตั้งค่า")
        save_btn.setFixedHeight(42)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb; border: none; color: white;
                font-size: 13px; font-weight: bold; border-radius: 8px; padding: 0 18px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:pressed { background-color: #1e40af; }
        """)
        save_btn.clicked.connect(lambda: self.save_settings(and_test=False))

        drawer_test_btn = QPushButton("ทดสอบเปิดลิ้นชัก")
        drawer_test_btn.setFixedHeight(42)
        drawer_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff7ed; border: 1px solid #fdba74; color: #c2410c;
                font-size: 13px; font-weight: bold; border-radius: 8px; padding: 0 14px;
            }
            QPushButton:hover { background-color: #ffedd5; }
        """)
        drawer_test_btn.clicked.connect(self.test_drawer)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(drawer_test_btn)
        btn_layout.addWidget(test_btn)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)

    def test_drawer(self):
        printer_name = self.printer_combo.currentText().strip()
        if printer_name == "--- กรุณาเลือกเครื่องพิมพ์ ---" or not printer_name:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกเครื่องพิมพ์ก่อนทดสอบเปิดลิ้นชัก")
            return
        try:
            open_cash_drawer(printer_name)
            QMessageBox.information(self, "สำเร็จ", f"ส่งคำสั่งเปิดลิ้นชักไปยังเครื่องพิมพ์ '{printer_name}' เรียบร้อยแล้ว")
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถเปิดลิ้นชักได้:\n{str(e)}")

    def save_and_test(self):
        self.save_settings(and_test=True)

    def save_settings(self, and_test=False):
        printer_name = self.printer_combo.currentText().strip()
        if printer_name == "--- กรุณาเลือกเครื่องพิมพ์ ---":
            printer_name = ""

        if not printer_name and and_test:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกเครื่องพิมพ์ก่อนทดสอบพิมพ์")
            return

        copies = int(self.copies_spin.value())
        self.config['receipt_printer'] = printer_name
        self.config['receipt_copies'] = copies

        if 'receipt_paper_size' not in self.config:
            self.config['receipt_paper_size'] = '80mm'
        if 'receipt_font_scale' not in self.config:
            self.config['receipt_font_scale'] = 'large'

        parent_window = self.parent()
        if parent_window:
            if hasattr(parent_window, 'config') and isinstance(parent_window.config, dict):
                parent_window.config.update(self.config)
            if hasattr(parent_window, 'save_config'):
                parent_window.save_config()
            if hasattr(parent_window, 'update_receipt_ui'):
                parent_window.update_receipt_ui(self.config)

        if and_test:
            try:
                printer_config = dict(self.config)
                test_data = self.receipt_data or {
                    'branch': self.config.get('branch_name', 'สำนักงานใหญ่'),
                    'cashier': self.config.get('cashier_name', 'ทดสอบระบบ'),
                    'doc_number': 'TEST-PRINT',
                    'date': '2026-10-30 11:45:00',
                    'total': 0.0,
                    'payment_method': 'cash',
                    'items': [{'name': 'ทดสอบพิมพ์ใบเสร็จ', 'qty': 1, 'price': 0.0, 'total': 0.0}]
                }
                test_cfg = dict(printer_config)
                test_cfg['receipt_copies'] = 1
                if parent_window and hasattr(parent_window, 'receipt_text'):
                    test_cfg['_receipt_document'] = parent_window.receipt_text.document()
                print_escpos_receipt(printer_name, test_data, test_cfg)
                QMessageBox.information(self, "สำเร็จ", f"บันทึกและส่งคำสั่งทดสอบไปยังเครื่องพิมพ์ '{printer_name}' เรียบร้อยแล้ว")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถสั่งพิมพ์ได้:\n{str(e)}")
        else:
            QMessageBox.information(self, "สำเร็จ", "บันทึกการตั้งค่าเครื่องพิมพ์เรียบร้อยแล้ว")
            self.accept()

class ReceiptDialog(QDialog):

    def __init__(self, parent=None, receipt_data=None):

        super().__init__(parent)

        self.setWindowTitle("พิมพ์ใบเสร็จรับเงิน")

        parent_config = getattr(parent, 'config', {}) if parent else {}
        self.config = dict(parent_config)
        self.receipt_paper_size = _resolve_paper_size(self.config)
        self.setFixedWidth(380 if self.receipt_paper_size == '58mm' else 400)
        self.setMinimumHeight(0)
        self.setMaximumHeight(1400)

        self.setStyleSheet("background-color: #f3f4f6; color: #111827; font-family: Tahoma, sans-serif;")

        

        self.receipt_data = receipt_data or {}

        self.init_ui()

        

    def init_ui(self):

        main_layout = QVBoxLayout(self)

        

        paper = QFrame()

        paper.setStyleSheet("background-color: white; border-radius: 8px; border: 1px solid #d1d5db;")

        self.paper_layout = QVBoxLayout(paper)
        self.paper_layout.setContentsMargins(18, 16, 18, 16)
        self.paper_layout.setSpacing(8)

        

        self.receipt_text = QTextEdit()

        self.receipt_text.setReadOnly(True)
        self.receipt_text.setFont(QFont("Tahoma", 14))
        self.receipt_text.setStyleSheet("border: none; background: transparent;")
        self.receipt_text.setFixedWidth(270 if self.receipt_paper_size == '58mm' else 280)
        self.receipt_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.receipt_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.paper_layout.setAlignment(self.receipt_text, Qt.AlignmentFlag.AlignHCenter)

        self.paper_layout.addWidget(self.receipt_text)

        

        self.update_receipt_ui(self.config)

        

        # Auto-open drawer if cash or split

        pm = self.receipt_data.get('payment_method', '')

        if pm in ['cash', 'split', 'เงินสด', 'ผสม (Split)']:

            printer_name = self.config.get('receipt_printer', '')

            if printer_name:

                try:

                    open_cash_drawer(printer_name)

                except:

                    pass

        

        top_btns = QHBoxLayout()

        print_btn = QPushButton("🖨️ พิมพ์")
        print_btn.setStyleSheet("QPushButton { background-color: #10b981; color: white; border: none; border-radius: 8px; padding: 10px; font-weight: bold; font-size: 14px; } QPushButton:hover { background-color: #059669; }")
        print_btn.clicked.connect(self.print_receipt)

        drawer_btn = QPushButton("💵 ลิ้นชัก")
        drawer_btn.setStyleSheet("QPushButton { background-color: #f8fafc; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; font-weight: bold; font-size: 14px; } QPushButton:hover { background-color: #e2e8f0; }")
        drawer_btn.clicked.connect(self.manual_open_drawer)

        settings_btn = QPushButton("⚙️ ตั้งค่า")
        settings_btn.setStyleSheet("QPushButton { background-color: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; font-weight: bold; } QPushButton:hover { background-color: #f3f4f6; }")
        settings_btn.clicked.connect(self.open_settings)

        top_btns.addWidget(print_btn)
        top_btns.addWidget(drawer_btn)
        top_btns.addWidget(settings_btn)

        self.paper_layout.addLayout(top_btns)

        new_bill_btn = QPushButton("📦 บิลใหม่")

        new_bill_btn.setStyleSheet("QPushButton { background-color: #111827; color: white; border: none; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 16px; } QPushButton:hover { background-color: #374151; }")

        new_bill_btn.clicked.connect(self.accept)

        self.paper_layout.addWidget(new_bill_btn)

        

        main_layout.addWidget(paper)
        self.adjustSize()
        QTimer.singleShot(0, self._fit_receipt_layout)

    def open_settings(self):

        parent_window = self.parent()

        config = getattr(parent_window, 'config', {}) if parent_window else {}

        dialog = ReceiptSettingsDialog(self, config, self.receipt_data)

        dialog.exec()

    def save_config(self):
        main_window = self.parent()
        if main_window and hasattr(main_window, 'save_config'):
            main_window.config.update(self.config)
            main_window.save_config()

    def update_receipt_ui(self, config):

        if not hasattr(self, 'receipt_text'): return

        from decimal import ROUND_FLOOR
        self.config = dict(config or {})
        self.receipt_paper_size = _resolve_paper_size(self.config)
        is_narrow = self.receipt_paper_size == '58mm'
        self.receipt_text.setFixedWidth(270 if is_narrow else 280)
        self.setFixedWidth(380 if is_narrow else 400)

        font_scale = self.config.get('receipt_font_scale', 'large')
        if font_scale == 'xlarge':
            font_body = "13px" if is_narrow else "13.5px"
            font_th = "12.5px" if is_narrow else "13px"
            font_shop = "19px" if is_narrow else "20px"
            font_doc = "13px" if is_narrow else "13.5px"
            font_total_lbl = "19px" if is_narrow else "20px"
            font_total_val = "21px" if is_narrow else "22px"
            font_meta = "11px" if is_narrow else "11.5px"
        elif font_scale == 'compact':
            font_body = "11px" if is_narrow else "11.5px"
            font_th = "10.5px" if is_narrow else "11px"
            font_shop = "16px" if is_narrow else "17px"
            font_doc = "11px" if is_narrow else "11.5px"
            font_total_lbl = "16px" if is_narrow else "17px"
            font_total_val = "18px" if is_narrow else "19px"
            font_meta = "9.5px" if is_narrow else "10px"
        else:  # 'large' (default - clear, bold, matching reference slip style)
            font_body = "12px" if is_narrow else "12px"
            font_th = "11.5px" if is_narrow else "11.5px"
            font_shop = "18px" if is_narrow else "18px"
            font_doc = "12px" if is_narrow else "12px"
            font_total_lbl = "18px" if is_narrow else "18px"
            font_total_val = "20px" if is_narrow else "20px"
            font_meta = "10.5px" if is_narrow else "10.5px"

        header_text = config.get('receipt_header', '')
        if not header_text:
            header_text = "บริษัท ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง จำกัด\n480 หมู่บ้านคำเจริญ ม.1 ต.แสนสุข\nอ.วารินชำราบ จ.อุบลราชธานี 34190\nโทร. 061-935-4497 | Line: @popstarshop"

        footer_text = config.get('receipt_footer', '')
        if not footer_text:
            footer_text = "ขอบคุณที่ใช้บริการ\nโอกาสหน้าเชิญใหม่ครับ/ค่ะ"

        branch = self.receipt_data.get('branch', 'สำนักงานใหญ่')
        cashier = self.receipt_data.get('cashier', '01')
        receipt_no = self.receipt_data.get('doc_number', '-')
        date_str = self.receipt_data.get('date', '-')

        items_list = self.receipt_data.get('items', [])
        items_sum = sum((_receipt_amount(it.get('total', 0)) for it in items_list), Decimal('0.00')).quantize(Decimal('0.01'))
        manual_discount = _receipt_amount(self.receipt_data.get('discount_amount', 0)).quantize(Decimal('0.01'))

        if items_sum > Decimal('0.00'):
            total_amount = max(Decimal('0.00'), items_sum - manual_discount).quantize(Decimal('0.01'))
        else:
            total_amount = _receipt_amount(self.receipt_data.get('total', 0)).quantize(Decimal('0.01'))
        satang_discount = Decimal('0.00')

        vat_rate = _receipt_amount(self.receipt_data.get('vat_rate', 7))
        vat_amount = total_amount * vat_rate / (Decimal('100') + vat_rate) if vat_rate else Decimal('0')
        before_vat = total_amount - vat_amount

        safe = lambda value: html.escape(str(value or ''))
        full_tax = bool(self.receipt_data.get('is_full_tax'))
        shop_name = config.get('receipt_shop_name', 'POP STAR SHOP')
        header_html = "<br>".join(safe(line) for line in header_text.splitlines()) if full_tax else safe(shop_name)
        footer_html = "<br>".join(safe(line) for line in footer_text.splitlines()[:1]) if full_tax else ""
        method = self.receipt_data.get('payment_method', 'cash')
        method_str = _payment_method_label(method)
        item_count = int(self.receipt_data.get('item_count', len(items_list)))
        total_qty = sum((_receipt_amount(item.get('qty', 0)) for item in items_list), Decimal('0')) if items_list else _receipt_amount(self.receipt_data.get('total_qty', 0))
        cash_received = _receipt_amount(self.receipt_data.get('cash_received', total_amount)).quantize(Decimal('0.01'))
        if cash_received <= Decimal('0.00'):
            cash_received = total_amount

        max_name_len = 15 if is_narrow else 18
        col_qty = "14%" if is_narrow else "14%"
        col_name = "44%" if is_narrow else "44%"
        col_unit = "21%" if is_narrow else "21%"
        col_price = "21%" if is_narrow else "21%"
        col_name_span = "58%" if is_narrow else "58%"
        col_unit_span = "21%" if is_narrow else "21%"
        col_price_span = "21%" if is_narrow else "21%"

        items_html = "".join(
            f"""
            <tr class="item-row">
                <td colspan="2" width="{col_name_span}" class="item-desc">{safe(_format_receipt_qty(item.get('qty', 1)))} {safe(_truncate_thai_visual(item.get('name', ''), max_name_len))}</td>
                <td width="{col_unit_span}" class="unit">{_receipt_amount(item.get('price', 0)):,.2f}&nbsp;&nbsp;</td>
                <td width="{col_price_span}" class="amount">{_receipt_amount(item.get('total', 0)):,.2f}#</td>
            </tr>
            """
            for item in items_list
        )

        logo_path = _logo_path()
        customer_html = ""
        if full_tax:
            customer_html = f"""
                <div class="customer">
                    ลูกค้า: {safe(self.receipt_data.get('customer_name'))}<br>
                    เลขประจำตัวผู้เสียภาษี: {safe(self.receipt_data.get('customer_tax_id'))}<br>
                    ที่อยู่: {safe(self.receipt_data.get('customer_address'))}
                </div>
            """

        satang_html = ""
        discount_html = (
            f'<tr class="item-row"><td colspan="2" class="item-desc">ส่วนลด</td><td class="unit"></td><td class="amount">-{manual_discount:,.2f}&nbsp;&nbsp;</td></tr>'
            if manual_discount > Decimal('0.00') else ''
        )
        vat_html = (
            f'<tr class="item-row"><td colspan="2" class="item-desc">มูลค่าสินค้าก่อน VAT</td><td class="unit"></td><td class="amount">{before_vat:,.2f}&nbsp;&nbsp;</td></tr>'
            f'<tr class="item-row"><td colspan="2" class="item-desc">VAT {vat_rate}%</td><td class="unit"></td><td class="amount">{vat_amount:,.2f}&nbsp;&nbsp;</td></tr>'
            if full_tax else ''
        )
        payment_label = 'เงินสด' if method == 'cash' else method_str
        paid_amount = cash_received if method == 'cash' else total_amount
        change_amount = max(Decimal('0.00'), paid_amount - total_amount)
        change_html = (
            f'<tr><td colspan="2">เงินทอน</td><td colspan="2" class="amount">{change_amount:,.2f}&nbsp;&nbsp;</td></tr>'
            if method == 'cash' and change_amount > Decimal('0.00') else ''
        )

        receipt_html = f"""
        <html><head><style>
            body {{ font-family: 'Leelawadee UI', 'Tahoma', 'Arial', sans-serif; font-size: {font_body}; font-weight: 700; color: #000; margin: 0; line-height: 1.22; }}
            .receipt {{ width: 100%; }}
            .center {{ text-align: center; }}
            .shop {{ font-size: {font_shop}; font-weight: 900; line-height: 1.2; letter-spacing: 0.5px; }}
            .document {{ font-size: {font_doc}; font-weight: 700; margin: 2px 0 3px; }}
            .customer {{ margin: 2px 0; padding-top: 2px; line-height: 1.22; font-size: {font_doc}; }}
            table.slip-table {{ width: 100%; border-collapse: collapse; color: #000; }}
            table.slip-table th {{ border-bottom: 1px solid #000; padding: 2px 0 3px 0; font-size: {font_th}; font-weight: 800; white-space: nowrap; }}
            table.slip-table td {{ padding: 1px 0; vertical-align: middle; font-size: {font_body}; font-weight: 700; }}
            .item-desc {{ text-align: left; white-space: nowrap; }}
            .unit {{ text-align: right; white-space: nowrap; padding-right: 6px; }}
            .amount {{ text-align: right; white-space: nowrap; }}
            .footer {{ margin-top: 6px; padding-top: 3px; line-height: 1.22; font-size: {font_doc}; }}
        </style></head><body>
            <div class="receipt">
                <div class="center shop">{header_html}</div>
                <div class="center document">{'ใบกำกับภาษีอย่างย่อ' if full_tax else 'ใบรับเงิน'}</div>
                {customer_html}
                <table class="slip-table" width="100%" cellspacing="0" cellpadding="0">
                    <thead>
                        <tr>
                            <th width="{col_qty}" align="left">Qty</th>
                            <th width="{col_name}" align="left">&nbsp;&nbsp;รายการ</th>
                            <th width="{col_unit}" align="right">ต่อหน่วย&nbsp;&nbsp;</th>
                            <th width="{col_price}" align="right">ราคา&nbsp;</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                        {discount_html}
                        {satang_html}
                        {vat_html}
                        <tr>
                            <td colspan="2" style="padding-top: 4px; padding-bottom: 4px; font-size: {font_total_lbl}; font-weight: 900; vertical-align: middle;">ยอดรวม</td>
                            <td colspan="2" align="right" style="border-top: 1px solid #000; border-bottom: 3.5px double #000; padding-top: 4px; padding-bottom: 4px; font-size: {font_total_val}; font-weight: 900; vertical-align: middle; white-space: nowrap;">{total_amount:,.2f}&nbsp;</td>
                        </tr>
                        <tr>
                            <td colspan="2" style="padding-top: 3px;">{safe(payment_label)}</td>
                            <td colspan="2" class="amount" style="padding-top: 3px;">{paid_amount:,.2f}&nbsp;&nbsp;</td>
                        </tr>
                        {change_html}
                        <tr>
                            <td colspan="2">รวมรายการ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {item_count}</td>
                            <td class="unit" style="white-space: nowrap;">รวมชิ้น &nbsp;&nbsp;&nbsp;&nbsp; {_format_total_qty(total_qty)}</td>
                            <td></td>
                        </tr>
                        <tr>
                            <td colspan="4">Cashier : &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {safe(cashier)}</td>
                        </tr>
                        <tr>
                            <td colspan="4" style="font-size: {font_meta}; padding-top: 2px; white-space: nowrap;">{safe(receipt_no)} &nbsp; {safe(_receipt_date_label(date_str))}</td>
                        </tr>
                    </tbody>
                </table>
                {f'<div class="center footer">{footer_html}</div>' if footer_html else ''}
            </div>
        </body></html>
        """
        document = self.receipt_text.document()
        document.setDocumentMargin(1)
        document.setBaseUrl(QUrl.fromLocalFile(os.path.dirname(logo_path) + os.sep))
        self.receipt_text.setHtml(receipt_html)
        document.setTextWidth(self.receipt_text.width())
        content_height = document.documentLayout().documentSize().height()
        self.receipt_text.setFixedHeight(min(max(int(content_height + 24), 240), 1200))

    def _fit_receipt_layout(self):
        document = self.receipt_text.document()
        document.setDocumentMargin(1)
        document.setTextWidth(self.receipt_text.width())
        content_height = document.documentLayout().documentSize().height()
        self.receipt_text.setFixedHeight(min(max(int(content_height + 24), 240), 1200))
        self.adjustSize()

    def manual_open_drawer(self):

        parent_window = self.parent()

        config = getattr(parent_window, 'config', {}) if parent_window else {}

        printer_name = config.get('receipt_printer', '')

        if not printer_name:

            QMessageBox.warning(self, "แจ้งเตือน", "ยังไม่ได้ตั้งค่าเครื่องพิมพ์ในหน้าตั้งค่า")

            return

        # Require PIN to open drawer
        from ui.drawer_pin_dialog import DrawerPinDialog
        pin_dialog = DrawerPinDialog(
            self,
            api_url=config.get('api_url', ''),
            pos_token=config.get('pos_token', ''),
            cashier_code=config.get('cashier_code') or config.get('cashier_username', ''),
            offline_auth=config.get('offline_auth'),
            active_pin=getattr(parent_window, '_active_cashier_pin', '') if parent_window else ''
        )
        if pin_dialog.exec() != QDialog.Accepted:
            return

        try:
            open_cash_drawer(printer_name)
            QMessageBox.information(self, "สำเร็จ", f"ส่งคำสั่งเปิดลิ้นชักไปยังเครื่องพิมพ์ '{printer_name}' เรียบร้อยแล้ว")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"ไม่สามารถเปิดลิ้นชักได้:\n{str(e)}")

    def print_receipt(self):
        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        merged_config = dict(config)
        merged_config.update(self.config)

        printer_name = merged_config.get('receipt_printer', '')
        if not printer_name:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาตั้งค่าเครื่องพิมพ์ใบเสร็จ (ปุ่มตั้งค่า) ก่อน!")
            return

        try:
            print_escpos_receipt(
                printer_name,
                self.receipt_data,
                {**merged_config, 'receipt_paper_size': self.receipt_paper_size, '_receipt_document': self.receipt_text.document()},
            )
            copies = int(merged_config.get('receipt_copies', 1) or 1)
            msg = f"สั่งพิมพ์ใบเสร็จเรียบร้อยแล้ว ({copies} ฉบับ)" if copies > 1 else "สั่งพิมพ์ใบเสร็จเรียบร้อยแล้ว"
            QMessageBox.information(self, "สำเร็จ", msg)
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการพิมพ์:\n{str(e)}")

class ShiftReportDialog(QDialog):
    """
    หน้าต่างแสดงตัวอย่างและสั่งพิมพ์ใบรายงานสรุปกะ (Z-Report)
    แสดงผลรูปแบบกระดาษความร้อน (Thermal Paper Slip) พร้อมปุ่มสั่งพิมพ์ลงเครื่องพิมพ์ใบเสร็จ
    """
    def __init__(self, parent=None, shift_data=None):
        super().__init__(parent)
        self.setWindowTitle("รายงานปิดกะการขาย (Z-Report)")
        self.setFixedWidth(460)
        self.setMinimumHeight(400)
        self.setMaximumHeight(780)
        self.setStyleSheet("background-color: #f1f5f9; color: #0f172a; font-family: 'Sarabun', Tahoma, sans-serif;")
        
        self.shift_data = shift_data or {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Header Title
        top_header = QHBoxLayout()
        title_lbl = QLabel("🧾 สรุปยอดขายประจำกะ (Z-Report)")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #0f172a;")
        top_header.addWidget(title_lbl)
        top_header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: bold; } QPushButton:hover { background: #fee2e2; color: #dc2626; }")
        close_btn.clicked.connect(self.accept)
        top_header.addWidget(close_btn)
        main_layout.addLayout(top_header)

        # Scroll Container for Paper (Prevents buttons being pushed off screen)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 8px; background: #e2e8f0; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8; border-radius: 4px; min-height: 24px;
            }
            QScrollBar::handle:vertical:hover { background: #64748b; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        # Paper Container Frame
        paper = QFrame()
        paper.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 35))
        shadow.setOffset(0, 4)
        paper.setGraphicsEffect(shadow)

        paper_layout = QVBoxLayout(paper)
        paper_layout.setContentsMargins(16, 18, 16, 18)
        paper_layout.setSpacing(8)

        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setFont(QFont("Tahoma", 13))
        self.report_text.setStyleSheet("border: none; background: transparent;")
        self.report_text.setFixedWidth(380)
        self.report_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.report_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        paper_layout.setAlignment(self.report_text, Qt.AlignmentFlag.AlignHCenter)

        paper_layout.addWidget(self.report_text)
        scroll.setWidget(paper)
        main_layout.addWidget(scroll)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.print_btn = QPushButton("🖨️ พิมพ์ใบกะ (Print)")
        self.print_btn.setFixedHeight(44)
        self.print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; border: none; border-radius: 8px;
                padding: 8px 18px; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background-color: #0369a1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        self.print_btn.clicked.connect(self.print_report)

        self.drawer_btn = QPushButton("💵 ลิ้นชัก")
        self.drawer_btn.setFixedHeight(44)
        self.drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drawer_btn.setStyleSheet("""
            QPushButton {
                background-color: white; border: 1px solid #cbd5e1; border-radius: 8px;
                padding: 8px 14px; font-weight: bold; font-size: 14px; color: #334155;
            }
            QPushButton:hover { background-color: #f8fafc; border-color: #94a3b8; }
        """)
        self.drawer_btn.clicked.connect(self.open_drawer)

        self.done_btn = QPushButton("ปิดหน้าต่าง")
        self.done_btn.setFixedHeight(44)
        self.done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155; color: white; border: none; border-radius: 8px;
                padding: 8px 16px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #1e293b; }
        """)
        self.done_btn.clicked.connect(self.accept)

        btn_layout.addWidget(self.drawer_btn)
        btn_layout.addWidget(self.print_btn, stretch=2)
        btn_layout.addWidget(self.done_btn)
        main_layout.addLayout(btn_layout)

        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        self.render_html_report(config)

        self.adjustSize()
        QTimer.singleShot(0, self._fit_report_layout)

    def render_html_report(self, config):
        shift = self.shift_data
        branch_name = shift.get('branch_name') or config.get('branch_name') or 'สำนักงานใหญ่'
        cashier_name = shift.get('cashier_name') or shift.get('cashier_user_name') or config.get('cashier_name') or 'พนักงาน'
        shift_no = shift.get('shift_no') or f"SHIFT-{shift.get('id', '-')}"
        status = shift.get('status', 'open')
        status_label = "เปิดอยู่ (ระหว่างกะ)" if status == 'open' else "ปิดกะแล้ว"

        opened_at = str(shift.get('opened_at') or '-')
        closed_at = str(shift.get('closed_at') or '-') if status != 'open' else 'ยังไม่ปิด'

        opening_cash = float(shift.get('opening_cash') or 0.0)
        cash_sales = float(shift.get('cash_sales') or 0.0)
        transfer_sales = float(shift.get('transfer_sales') or 0.0)
        card_sales = float(shift.get('card_sales') or 0.0)
        gross_sales = cash_sales + transfer_sales + card_sales
        total_sales = gross_sales
        expected_cash = float(shift.get('expected_cash') or (opening_cash + cash_sales))
        counted_cash = shift.get('counted_cash')
        cash_difference = shift.get('cash_difference')
        receipt_count = int(shift.get('receipt_count') or 0)

        # VAT calculation (approx 7% included)
        vat_amount = round(total_sales * 7 / 107, 2)
        before_vat = total_sales - vat_amount

        now_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        counted_html = ""
        if counted_cash is not None:
            c_val = float(counted_cash)
            counted_html += f'<tr><td style="padding: 2px 0;">เงินสดนับจริง</td><td align="right" style="font-weight: 800;">{c_val:,.2f}</td></tr>'
        if cash_difference is not None:
            d_val = float(cash_difference)
            diff_text = "เงินตรงกะ" if abs(d_val) < 0.01 else ("เงินเกิน (+)" if d_val > 0 else "เงินขาด (-)")
            counted_html += f'<tr><td style="padding: 2px 0; font-weight: 800;">{diff_text}</td><td align="right" style="font-weight: 900;">{abs(d_val):,.2f}</td></tr>'

        report_html = f"""<!doctype html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Tahoma', 'Arial', sans-serif; font-size: 13px; font-weight: 700; color: #000000; margin: 0; padding: 4px; line-height: 1.3; }}
            .center {{ text-align: center; }}
            .bold {{ font-weight: 800; }}
            .title {{ font-size: 17px; font-weight: 900; margin-bottom: 3px; color: #000; }}
            .subtitle {{ font-size: 14.5px; font-weight: 900; margin-bottom: 5px; color: #000; }}
            .rule {{ border-top: 2px dashed #000; margin: 6px 0; }}
            .rule-solid {{ border-top: 2px solid #000; margin: 6px 0; }}
            .rule-double {{ border-top: 3px double #000; margin: 6px 0; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; font-weight: 700; color: #000; }}
            td {{ vertical-align: top; color: #000; }}
            .num {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 800; }}
            .section {{ font-weight: 900; font-size: 14px; margin-top: 8px; margin-bottom: 4px; text-decoration: underline; color: #000; }}
        </style>
        </head>
        <body>
            <div class="center">
                <div class="title">ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง</div>
                <div class="subtitle">ใบสรุปการขายประจำกะ (Z-REPORT)</div>
                <div>สาขา: <strong>{branch_name}</strong></div>
                <div>รหัสกะ: <strong>{shift_no}</strong> ({status_label})</div>
            </div>
            <div class="rule"></div>
            <table>
                <tr><td>เปิดกะ:</td><td align="right"><strong>{opened_at}</strong></td></tr>
                <tr><td>ปิดกะ:</td><td align="right"><strong>{closed_at}</strong></td></tr>
                <tr><td>แคชเชียร์:</td><td align="right"><strong>{cashier_name}</strong></td></tr>
            </table>
            <div class="rule"></div>
            <div class="section">สรุปการขาย</div>
            <table>
                <tr><td style="padding: 2px 0;">จำนวนบิลขาย</td><td align="right" style="font-weight: 800;">{receipt_count} บิล</td></tr>
                <tr><td style="padding: 2px 0;">ยอดขายก่อน VAT</td><td align="right" style="font-weight: 800;">{before_vat:,.2f}</td></tr>
                <tr><td style="padding: 2px 0;">ภาษีมูลค่าเพิ่ม (7%)</td><td align="right" style="font-weight: 800;">{vat_amount:,.2f}</td></tr>
                <tr style="font-weight: 900; font-size: 15px;"><td style="padding: 5px 0;">ยอดขายรวมสุทธิ</td><td align="right" style="padding: 5px 0;">{total_sales:,.2f}</td></tr>
            </table>
            <div class="rule"></div>
            <div class="section">แยกตามช่องทางชำระ</div>
            <table>
                <tr><td style="padding: 2px 0;">เงินสด (Cash)</td><td align="right" style="font-weight: 800;">{cash_sales:,.2f}</td></tr>
                <tr><td style="padding: 2px 0;">โอนเงิน / PromptPay</td><td align="right" style="font-weight: 800;">{transfer_sales:,.2f}</td></tr>
                <tr><td style="padding: 2px 0;">บัตรเครดิต</td><td align="right" style="font-weight: 800;">{card_sales:,.2f}</td></tr>
                <tr style="font-weight: 900;"><td style="padding: 4px 0;">รวมยอดชำระ</td><td align="right" style="padding: 4px 0;">{total_sales:,.2f}</td></tr>
            </table>
            <div class="rule"></div>
            <div class="section">การตรวจสอบเงินสด (Cash Audit)</div>
            <table>
                <tr><td style="padding: 2px 0;">เงินทอนตั้งต้น (Opening)</td><td align="right" style="font-weight: 800;">{opening_cash:,.2f}</td></tr>
                <tr><td style="padding: 2px 0;">+ ยอดขายเงินสด</td><td align="right" style="font-weight: 800;">+{cash_sales:,.2f}</td></tr>
                <tr style="font-weight: 900; font-size: 14px;"><td style="padding: 5px 0;">เงินสดที่ควรมีในลิ้นชัก</td><td align="right" style="padding: 5px 0;">{expected_cash:,.2f}</td></tr>
                {counted_html}
            </table>
            <div class="rule-solid"></div>
            <div style="font-size: 11px; font-weight: 700; color: #000; margin-top: 6px;">
                <div>พิมพ์เมื่อ: {now_str}</div>
            </div>
            <div style="margin-top: 20px;">
                <table style="text-align: center; font-size: 11px; font-weight: 700;">
                    <tr>
                        <td width="50%" style="padding-top: 30px; border-top: 1.5px solid #000;">(ลงชื่อแคชเชียร์)</td>
                        <td width="50%" style="padding-top: 30px; border-top: 1.5px solid #000;">(ผู้ตรวจรับ/ผู้จัดการ)</td>
                    </tr>
                </table>
            </div>
            <div class="center" style="margin-top: 14px; font-size: 11px; font-weight: 700; color: #000;">
                - จบรายงานสรุปกะ -
            </div>
        </body>
        </html>
            </div>
        </body>
        </html>
        """
        self.report_text.setHtml(report_html)
        document = self.report_text.document()
        document.setTextWidth(self.report_text.width() - 20)
        content_height = document.documentLayout().documentSize().height()
        self.report_text.setFixedHeight(min(max(int(content_height + 36), 260), 1200))

    def _fit_report_layout(self):
        document = self.report_text.document()
        document.setTextWidth(self.report_text.viewport().width())
        content_height = document.documentLayout().documentSize().height()
        self.report_text.setFixedHeight(min(max(int(content_height + 36), 260), 1200))
        self.adjustSize()

    def open_drawer(self):
        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        printer_name = config.get('receipt_printer', '')
        if not printer_name:
            QMessageBox.warning(self, "แจ้งเตือน", "ยังไม่ได้ตั้งค่าเครื่องพิมพ์ในระบบ")
            return

        # Require PIN to open drawer
        from ui.drawer_pin_dialog import DrawerPinDialog
        pin_dialog = DrawerPinDialog(
            self,
            api_url=config.get('api_url', ''),
            pos_token=config.get('pos_token', ''),
            cashier_code=config.get('cashier_code') or config.get('cashier_username', ''),
            offline_auth=config.get('offline_auth'),
            active_pin=getattr(parent_window, '_active_cashier_pin', '') if parent_window else ''
        )
        if pin_dialog.exec() != QDialog.Accepted:
            return

        try:
            open_cash_drawer(printer_name)
            QMessageBox.information(self, "สำเร็จ", f"ส่งคำสั่งเปิดลิ้นชักไปยังเครื่องพิมพ์ '{printer_name}' เรียบร้อยแล้ว")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"ไม่สามารถเปิดลิ้นชักได้:\n{str(e)}")

    def print_report(self):
        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        printer_name = config.get('receipt_printer', '')
        if not printer_name:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาตั้งค่าเครื่องพิมพ์ใบเสร็จในหน้าตั้งค่าก่อนพิมพ์")
            return

        try:
            document = self.report_text.document()
            commands = _receipt_raster_commands(document)
            _send_raw_to_printer(printer_name, commands)
            QMessageBox.information(self, "สำเร็จ", "สั่งพิมพ์รายงานกะ (Z-Report) เรียบร้อยแล้ว!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"เกิดข้อผิดพลาดในการพิมพ์:\n{str(e)}")
