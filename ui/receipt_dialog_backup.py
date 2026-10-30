import os
import tempfile
import subprocess
import traceback
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QTextEdit, QMessageBox, QComboBox, 
                               QLineEdit, QFormLayout, QFrame)
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QFont
from PySide6.QtPrintSupport import QPrinterInfo

def print_escpos_receipt(printer_name, receipt_data, config):
    def enc(text):
        try:
            return text.encode('tis-620', errors='replace')
        except LookupError:
            return text.encode('cp874', errors='replace')
    
    header_text = config.get('receipt_header', '')
    if not header_text:
        header_text = "บริษัท ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง จำกัด\n480 หมู่บ้านคำเจริญ ม.1 ต.แสนสุข\nอ.วารินชำราบ จ.อุบลราชธานี 34190\nโทร. 061-935-4497 | Line: @popstarshop"
        
    footer_text = config.get('receipt_footer', '')
    if not footer_text:
        footer_text = "ขอบคุณที่ใช้บริการ\nโอกาสหน้าเชิญใหม่ครับ/ค่ะ"

    branch = receipt_data.get('branch', 'สำนักงานใหญ่')
    cashier = receipt_data.get('cashier', 'พนักงาน')
    receipt_no = receipt_data.get('doc_number', '-')
    date_str = receipt_data.get('date', '-')
    total_amount = receipt_data.get('total', 0.0)
    method_str = "เงินสด" if receipt_data.get('payment_method') == 'cash' else "โอนเงิน/QR"
    
    ESC = b'\x1b'
    GS  = b'\x1d'
    INIT          = ESC + b'@'
    ALIGN_LEFT    = ESC + b'a\x00'
    ALIGN_CENTER  = ESC + b'a\x01'
    ALIGN_RIGHT   = ESC + b'a\x02'
    BOLD_ON       = ESC + b'E\x01'
    BOLD_OFF      = ESC + b'E\x00'
    DOUBLE_ON     = GS  + b'!\x11'
    DOUBLE_OFF    = GS  + b'!\x00'
    LINE_FEED     = b'\n'
    CUT_PAPER     = GS  + b'V\x41\x03'
    
    cmds = bytearray()
    cmds += INIT
    
    cmds += ALIGN_CENTER
    cmds += BOLD_ON
    for line in header_text.split('\n'):
        cmds += enc(line) + LINE_FEED
    cmds += BOLD_OFF
    cmds += enc('-' * 32) + LINE_FEED
    cmds += enc('ใบเสร็จรับเงิน/ใบกำกับภาษีอย่างย่อ') + LINE_FEED
    cmds += enc('-' * 32) + LINE_FEED
    
    cmds += ALIGN_LEFT
    cmds += enc(f'สาขา: {branch}') + LINE_FEED
    cmds += enc(f'พนักงาน: {cashier}') + LINE_FEED
    cmds += enc(f'เลขที่: {receipt_no}') + LINE_FEED
    cmds += enc(f'วันที่: {date_str}') + LINE_FEED
    cmds += enc('-' * 32) + LINE_FEED
    
    for item in receipt_data.get('items', []):
        name  = item.get('name', '')
        qty   = item.get('qty', 1)
        price = item.get('price', 0.0)
        total = item.get('total', 0.0)
        cmds += enc(name[:32]) + LINE_FEED
        detail = f'  {qty} x {price:.2f}'
        total_str = f'{total:.2f}'
        pad = 32 - len(detail) - len(total_str)
        cmds += enc(detail + ' ' * max(pad, 1) + total_str) + LINE_FEED
    
    cmds += enc('-' * 32) + LINE_FEED
    
    cmds += ALIGN_CENTER
    cmds += enc('ยอดรวมสุทธิ') + LINE_FEED
    cmds += DOUBLE_ON
    cmds += BOLD_ON
    cmds += enc(f'{total_amount:,.2f} บาท') + LINE_FEED
    cmds += BOLD_OFF
    cmds += DOUBLE_OFF
    cmds += enc('(รวมภาษีมูลค่าเพิ่มแล้ว)') + LINE_FEED
    cmds += LINE_FEED
    cmds += enc(f'ชำระโดย: {method_str}') + LINE_FEED
    cmds += enc('-' * 32) + LINE_FEED
    
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
            win32print.StartDocPrinter(hPrinter, 1, ("PopCentralPOS Receipt", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, bytes(cmds))
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        raise Exception(f"ไม่สามารถส่งข้อมูลไปที่เครื่องพิมพ์ '{printer_name}' ได้: {str(e)}")


class ReceiptSettingsDialog(QDialog):
    def __init__(self, parent=None, config=None, receipt_data=None):
        super().__init__(parent)
        self.setWindowTitle("ตั้งค่าใบเสร็จ")
        self.setFixedSize(950, 620)
        self.setStyleSheet("background-color: #f3f4f6; color: #111827; font-family: Tahoma, sans-serif;")
        self.config = config or {}
        self.receipt_data = receipt_data or {}
        
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        main_layout = QHBoxLayout(self)
        
        settings_frame = QFrame()
        settings_frame.setStyleSheet("background-color: white; border-radius: 8px;")
        settings_layout = QVBoxLayout(settings_frame)
        form = QFormLayout()
        
        self.printer_combo = QComboBox()
        self.printer_combo.addItem("")
        for printer in QPrinterInfo.availablePrinters():
            self.printer_combo.addItem(printer.printerName())
        
        current_printer = self.config.get('receipt_printer', '')
        if current_printer:
            idx = self.printer_combo.findText(current_printer)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)
                
        form.addRow("เครื่องพิมพ์ใบเสร็จ (80mm):", self.printer_combo)
        
        self.header_edit = QTextEdit()
        self.header_edit.setPlaceholderText("ชื่อร้าน\nที่อยู่\nเบอร์โทร")
        default_header = "บริษัท ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง จำกัด\n480 หมู่บ้านคำเจริญ ม.1 ต.แสนสุข\nอ.วารินชำราบ จ.อุบลราชธานี 34190\nโทร. 061-935-4497 | Line: @popstarshop"
        self.header_edit.setPlainText(self.config.get('receipt_header', default_header))
        form.addRow("หัวใบเสร็จ:", self.header_edit)
        
        self.footer_edit = QTextEdit()
        self.footer_edit.setPlaceholderText("ข้อความขอบคุณ")
        default_footer = "ขอบคุณที่ใช้บริการ\nโอกาสหน้าเชิญใหม่ครับ/ค่ะ"
        self.footer_edit.setPlainText(self.config.get('receipt_footer', default_footer))
        form.addRow("ท้ายใบเสร็จ:", self.footer_edit)
        
        settings_layout.addLayout(form)
        
        save_btn = QPushButton("บันทึกและทดสอบพิมพ์")
        save_btn.setStyleSheet("background-color: #3b82f6; color: white; padding: 12px; font-size: 16px; border-radius: 6px; font-weight: bold;")
        save_btn.clicked.connect(self.save_and_test)
        settings_layout.addWidget(save_btn)
        
        main_layout.addWidget(settings_frame, stretch=1)

    def save_and_test(self):
        self.config['receipt_printer'] = self.printer_combo.currentText()
        self.config['receipt_header'] = self.header_edit.toPlainText()
        self.config['receipt_footer'] = self.footer_edit.toPlainText()
        
        parent_window = self.parent()
        if parent_window:
            parent_window.config = self.config
            parent_window.save_config()
            
            if hasattr(parent_window, 'update_receipt_ui'):
                parent_window.update_receipt_ui(self.config)
        
        printer_name = self.printer_combo.currentText()
        if not printer_name:
            QMessageBox.warning(self, "Warning", "กรุณาเลือกเครื่องพิมพ์")
            return
            
        try:
            print_escpos_receipt(printer_name, self.receipt_data, self.config)
            QMessageBox.information(self, "สำเร็จ", "บันทึกและสั่งพิมพ์เรียบร้อยแล้ว!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"เกิดข้อผิดพลาด:\n{str(e)}")


class ReceiptDialog(QDialog):
    def __init__(self, parent=None, receipt_data=None):
        super().__init__(parent)
        self.setWindowTitle("พิมพ์ใบเสร็จรับเงิน")
        self.setFixedSize(450, 680)
        self.setStyleSheet("background-color: #f3f4f6; color: #111827; font-family: Tahoma, sans-serif;")
        
        self.receipt_data = receipt_data or {}
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        paper = QFrame()
        paper.setStyleSheet("background-color: white; border-radius: 8px; border: 1px solid #d1d5db;")
        self.paper_layout = QVBoxLayout(paper)
        self.paper_layout.setContentsMargins(20, 20, 20, 20)
        
        self.receipt_text = QTextEdit()
        self.receipt_text.setReadOnly(True)
        self.receipt_text.setFont(QFont("Tahoma", 10))
        self.receipt_text.setStyleSheet("border: none; background: transparent;")
        self.paper_layout.addWidget(self.receipt_text)
        
        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        self.update_receipt_ui(config)
        
        top_btns = QHBoxLayout()
        print_btn = QPushButton("พิมพ์")
        print_btn.setStyleSheet("QPushButton { background-color: #10b981; color: white; border: none; border-radius: 8px; padding: 10px; font-weight: bold; font-size: 14px; } QPushButton:hover { background-color: #059669; }")
        print_btn.clicked.connect(self.print_receipt)
        
        settings_btn = QPushButton("ตั้งค่า")
        settings_btn.setStyleSheet("QPushButton { background-color: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; font-weight: bold; } QPushButton:hover { background-color: #f3f4f6; }")
        settings_btn.clicked.connect(self.open_settings)
        
        top_btns.addWidget(print_btn)
        top_btns.addWidget(settings_btn)
        self.paper_layout.addLayout(top_btns)
        
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setStyleSheet("QPushButton { background-color: #fee2e2; color: #dc2626; border: none; border-radius: 8px; padding: 8px; font-weight: bold; } QPushButton:hover { background-color: #fecaca; }")
        cancel_btn.clicked.connect(self.reject)
        self.paper_layout.addWidget(cancel_btn)
        
        new_bill_btn = QPushButton("บิลใหม่")
        new_bill_btn.setStyleSheet("QPushButton { background-color: #111827; color: white; border: none; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 16px; } QPushButton:hover { background-color: #374151; }")
        new_bill_btn.clicked.connect(self.accept)
        self.paper_layout.addWidget(new_bill_btn)
        
        main_layout.addWidget(paper)

    def open_settings(self):
        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        dialog = ReceiptSettingsDialog(self, config, self.receipt_data)
        dialog.exec()

    def update_receipt_ui(self, config):
        if not hasattr(self, 'receipt_text'): return
        
        header_text = config.get('receipt_header', '')
        if not header_text:
            header_text = "บริษัท ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง จำกัด\n480 หมู่บ้านคำเจริญ ม.1 ต.แสนสุข\nอ.วารินชำราบ จ.อุบลราชธานี 34190\nโทร. 061-935-4497 | Line: @popstarshop"
            
        footer_text = config.get('receipt_footer', '')
        if not footer_text:
            footer_text = "ขอบคุณที่ใช้บริการ\nโอกาสหน้าเชิญใหม่ครับ/ค่ะ"
        
        branch = self.receipt_data.get('branch', 'สำนักงานใหญ่')
        cashier = self.receipt_data.get('cashier', 'พนักงาน')
        receipt_no = self.receipt_data.get('doc_number', '-')
        date_str = self.receipt_data.get('date', '-')
        total_amount = self.receipt_data.get('total', 0.0)
        method_str = "เงินสด" if self.receipt_data.get('payment_method') == 'cash' else "โอนเงิน/QR"
        
        header_html = "<br>".join([f"<b>{line}</b>" for line in header_text.split('\n')])
        footer_html = "<br>".join([f"<b>{line}</b>" for line in footer_text.split('\n')])
        
        items_html = ""
        for item in self.receipt_data.get('items', []):
            name  = item.get('name', '')
            qty   = item.get('qty', 1)
            price = item.get('price', 0.0)
            total = item.get('total', 0.0)
            items_html += f"""
            <tr><td colspan="2" style="padding-top: 4px;">{name}</td></tr>
            <tr>
                <td style="color: #444; padding-left: 10px;">{qty} x {price:,.2f}</td>
                <td align="right">{total:,.2f}</td>
            </tr>
            """
            
        html = f"""
        <html>
        <body style="font-family: 'Tahoma', sans-serif; font-size: 13px; color: black; margin: 0; padding: 10px;">
            <div style="text-align: center; font-size: 14px; margin-bottom: 8px;">
                {header_html}
            </div>
            <hr style="border: none; border-top: 1px dashed black; margin: 4px 0;">
            <div style="text-align: center; font-weight: bold; margin-bottom: 8px;">
                ใบเสร็จรับเงิน/ใบกำกับภาษีอย่างย่อ
            </div>
            <hr style="border: none; border-top: 1px dashed black; margin: 4px 0;">
            <div style="margin-bottom: 8px;">
                สาขา: {branch}<br>
                พนักงาน: {cashier}<br>
                เลขที่: {receipt_no}<br>
                วันที่: {date_str}
            </div>
            <hr style="border: none; border-top: 1px dashed black; margin: 4px 0;">
            <table width="100%" style="border-collapse: collapse; font-size: 13px;">
                {items_html}
            </table>
            <hr style="border: none; border-top: 1px dashed black; margin: 8px 0;">
            <table width="100%" style="font-weight: bold;">
                <tr>
                    <td>ยอดรวมสุทธิ</td>
                    <td align="right" style="font-size: 16px;">{total_amount:,.2f} บาท</td>
                </tr>
            </table>
            <div style="text-align: center; margin-top: 8px;">
                (รวมภาษีมูลค่าเพิ่มแล้ว)<br>
                ชำระโดย: {method_str}
            </div>
            <hr style="border: none; border-top: 1px dashed black; margin: 8px 0;">
            <div style="text-align: center; margin-top: 8px;">
                {footer_html}
            </div>
        </body>
        </html>
        """
        self.receipt_text.setHtml(html)

    def print_receipt(self):
        parent_window = self.parent()
        config = getattr(parent_window, 'config', {}) if parent_window else {}
        
        printer_name = config.get('receipt_printer', '')
        if not printer_name:
            QMessageBox.warning(self, "Warning", "กรุณาตั้งค่าเครื่องพิมพ์ใบเสร็จ (ปุ่มตั้งค่า) ก่อน!")
            return
            
        try:
            print_escpos_receipt(printer_name, self.receipt_data, config)
            QMessageBox.information(self, "สำเร็จ", "สั่งพิมพ์ใบเสร็จเรียบร้อยแล้วครับ!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"เกิดข้อผิดพลาดในการพิมพ์:\n{traceback.format_exc()}")
