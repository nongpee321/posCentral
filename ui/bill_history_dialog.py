# -*- coding: utf-8 -*-
import json
import logging
import requests
from datetime import datetime
from decimal import Decimal

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame,
    QSplitter, QWidget, QInputDialog, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from database.models import init_db, Sale, SaleItem, Payment, Outbox
from ui.receipt_dialog import ReceiptDialog

logger = logging.getLogger("BillHistoryDialog")


class BillHistoryDialog(QDialog):
    """
    หน้าต่างประวัติรายการขาย / พิมพ์ซ้ำ / ยกเลิกบิล (Void) / แก้ไขบิล (Edit Bill)
    - เรียกดูบิลทั้งหมดในกะปัจจุบัน หรือบิลวันนี้
    - ค้นหาเลขที่ใบเสร็จ
    - พิมพ์ใบเสร็จซ้ำ (Reprint)
    - ยกเลิกบิล (Void) คืนสต๊อกและปรับยอดกะ
    - แก้ไขบิล (Edit Bill) ดึงรายการและส่วนลดเดิมกลับเข้าตะกร้าเพื่อคิดเงินใหม่
    """

    edit_bill_requested = Signal(object)  # ส่ง sale object กลับไปให้ MainWindow

    def __init__(self, parent=None, db_path="pos.db", config=None, current_shift=None):
        super().__init__(parent)
        self.setWindowTitle("ประวัติบิล / ยกเลิกบิล / พิมพ์ซ้ำ (Bill History & Void)")
        self.setMinimumSize(980, 640)
        self.resize(1020, 680)

        self.db_path = db_path
        self.config = config or {}
        self.current_shift = current_shift or {}
        self.selected_sale = None

        self.setStyleSheet("""
            QDialog {
                background-color: #f1f5f9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            }
            QLabel {
                color: #0f172a;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                gridline-color: #f1f5f9;
                selection-background-color: #e0f2fe;
                selection-color: #0369a1;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
            }
        """)

        self.init_ui()
        self.load_sales()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header bar
        header_bar = QHBoxLayout()

        title_lbl = QLabel("ประวัติรายการขาย / ยกเลิกบิล (Bill History & Void)")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e293b;")
        header_bar.addWidget(title_lbl)

        header_bar.addStretch()

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("กะปัจจุบัน", "shift")
        self.filter_combo.addItem("วันนี้ทั้งหมด", "today")
        self.filter_combo.addItem("ทั้งหมด (All)", "all")
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background: white; border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 6px 12px; font-size: 13px; font-weight: bold; color: #1e293b;
            }
        """)
        self.filter_combo.currentIndexChanged.connect(self.load_sales)
        header_bar.addWidget(self.filter_combo)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหาเลขบิล, ชื่อลูกค้า, หรือยอดเงิน...")
        self.search_input.setFixedWidth(280)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: white; border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 6px 10px; font-size: 13px;
            }
        """)
        self.search_input.textChanged.connect(self.filter_table)
        header_bar.addWidget(self.search_input)

        refresh_btn = QPushButton("รีเฟรช")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; border-radius: 6px;
                padding: 7px 14px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        refresh_btn.clicked.connect(self.load_sales)
        header_bar.addWidget(refresh_btn)

        main_layout.addLayout(header_bar)

        # Splitter: Upper list of bills, Lower details
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top Section: Sales Table
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.sales_table = QTableWidget()
        self.sales_table.setColumnCount(8)
        self.sales_table.setHorizontalHeaderLabels([
            "เลขที่ใบเสร็จ", "เวลาขาย", "จำนวนรายการ", "ยอดก่อนลด", "ส่วนลด", "ยอดสุทธิ", "วิธีชำระ", "สถานะ"
        ])
        self.sales_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.sales_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.sales_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sales_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sales_table.itemSelectionChanged.connect(self.on_sale_selected)
        top_layout.addWidget(self.sales_table)

        splitter.addWidget(top_widget)

        # Bottom Section: Bill Details & Action Buttons
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)

        # Left: Items table
        items_frame = QFrame()
        items_frame.setStyleSheet("background: white; border: 1px solid #cbd5e1; border-radius: 6px;")
        items_layout = QVBoxLayout(items_frame)
        items_layout.setContentsMargins(8, 8, 8, 8)

        items_title = QLabel("รายการสินค้าในบิล:")
        items_title.setStyleSheet("font-weight: bold; color: #334155;")
        items_layout.addWidget(items_title)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(["ชื่อสินค้า", "จำนวน", "ราคา/หน่วย", "รวม"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        items_layout.addWidget(self.items_table)
        bottom_layout.addWidget(items_frame, 3)

        # Right: Detail Card & Actions
        action_frame = QFrame()
        action_frame.setStyleSheet("background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px;")
        action_layout = QVBoxLayout(action_frame)
        action_layout.setSpacing(8)

        self.detail_info_lbl = QLabel("กรุณาเลือกบิลจากตารางด้านบน")
        self.detail_info_lbl.setStyleSheet("font-size: 13px; line-height: 1.4; color: #1e293b;")
        self.detail_info_lbl.setWordWrap(True)
        action_layout.addWidget(self.detail_info_lbl)

        action_layout.addStretch()

        # Action Buttons
        self.reprint_btn = QPushButton("พิมพ์ใบเสร็จซ้ำ (Reprint)")
        self.reprint_btn.setEnabled(False)
        self.reprint_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; border-radius: 6px;
                padding: 10px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #0369a1; }
            QPushButton:disabled { background-color: #94a3b8; color: #e2e8f0; }
        """)
        self.reprint_btn.clicked.connect(self.reprint_bill)
        action_layout.addWidget(self.reprint_btn)

        self.edit_btn = QPushButton("แก้ไขบิล (Edit Bill)")
        self.edit_btn.setEnabled(False)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #d97706; color: white; border-radius: 6px;
                padding: 10px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #b45309; }
            QPushButton:disabled { background-color: #94a3b8; color: #e2e8f0; }
        """)
        self.edit_btn.clicked.connect(self.edit_bill)
        action_layout.addWidget(self.edit_btn)

        self.void_btn = QPushButton("ยกเลิกบิล (Void)")
        self.void_btn.setEnabled(False)
        self.void_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; border-radius: 6px;
                padding: 10px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #b91c1c; }
            QPushButton:disabled { background-color: #94a3b8; color: #e2e8f0; }
        """)
        self.void_btn.clicked.connect(self.void_bill)
        action_layout.addWidget(self.void_btn)

        bottom_layout.addWidget(action_frame, 2)

        splitter.addWidget(bottom_widget)
        splitter.setSizes([360, 240])
        main_layout.addWidget(splitter)

        # Footer Bar
        footer_layout = QHBoxLayout()
        self.status_bar_lbl = QLabel("")
        self.status_bar_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        footer_layout.addWidget(self.status_bar_lbl)

        footer_layout.addStretch()

        close_btn = QPushButton("ปิดหน้าต่าง")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #64748b; color: white; border-radius: 6px;
                padding: 8px 20px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #475569; }
        """)
        close_btn.clicked.connect(self.close)
        footer_layout.addWidget(close_btn)

        main_layout.addLayout(footer_layout)

    def load_sales(self):
        """โหลดรายการบิลจาก SQLite"""
        self.all_sales = []
        try:
            session = init_db(f'sqlite:///{self.db_path}')
            query = session.query(Sale).order_by(Sale.created_at.desc())

            filter_mode = self.filter_combo.currentData()
            if filter_mode == 'shift':
                shift_id = self.current_shift.get('local_id') or self.current_shift.get('id')
                if shift_id:
                    query = query.filter(Sale.shift_id == shift_id)
            elif filter_mode == 'today':
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(Sale.created_at >= today_start)

            sales = query.limit(100).all()

            for s in sales:
                items_data = [
                    {
                        'product_id': it.product_id,
                        'name': it.name,
                        'qty': it.qty,
                        'unit_price': it.unit_price,
                        'total_price': it.total_price,
                        'is_weight_item': getattr(it, 'is_weight_item', False)
                    } for it in (s.items or [])
                ]
                self.all_sales.append({
                    'local_sale_id': s.local_sale_id,
                    'server_receipt_id': s.server_receipt_id,
                    'doc_number': s.doc_number or s.local_sale_id,
                    'created_at': s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else "-",
                    'total_amount': float(s.total_amount or 0.0),
                    'received_amount': float(s.received_amount or 0.0),
                    'discount_amount': float(getattr(s, 'discount_amount', 0.0) or 0.0),
                    'payment_method': s.payment_method or 'cash',
                    'cash_amount': float(s.cash_amount or 0.0),
                    'transfer_amount': float(s.transfer_amount or 0.0),
                    'status': s.status or 'pending',
                    'cashier_salesman_id': s.cashier_salesman_id,
                    'shift_id': s.shift_id,
                    'customer_name': s.customer_name,
                    'customer_tax_id': s.customer_tax_id,
                    'customer_address': s.customer_address,
                    'is_full_tax': bool(s.is_full_tax),
                    'items': items_data
                })

            session.close()
            self.display_sales(self.all_sales)
            self.status_bar_lbl.setText(f"พบทั้งหมด {len(self.all_sales)} บิล")
        except Exception as e:
            logger.exception("Error loading sales from SQLite")
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถโหลดประวัติบิลได้:\n{str(e)}")

    def display_sales(self, sales_list):
        self.sales_table.setRowCount(0)
        for s in sales_list:
            row = self.sales_table.rowCount()
            self.sales_table.insertRow(row)

            doc_item = QTableWidgetItem(s['doc_number'])
            doc_item.setData(Qt.UserRole, s)
            doc_item.setFont(QFont("Tahoma", 10, QFont.Bold))

            time_item = QTableWidgetItem(s['created_at'])
            items_count_item = QTableWidgetItem(f"{len(s['items'])} รายการ")
            items_count_item.setTextAlignment(Qt.AlignCenter)

            subtotal_val = round(s['total_amount'] + s['discount_amount'], 2)
            sub_item = QTableWidgetItem(f"{subtotal_val:,.2f}")
            sub_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            disc_val = s['discount_amount']
            disc_item = QTableWidgetItem(f"-฿{disc_val:,.2f}" if disc_val > 0 else "0.00")
            disc_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if disc_val > 0:
                disc_item.setForeground(QColor("#dc2626"))
                disc_item.setFont(QFont("Tahoma", 10, QFont.Bold))

            net_item = QTableWidgetItem(f"฿{s['total_amount']:,.2f}")
            net_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            net_item.setFont(QFont("Tahoma", 10, QFont.Bold))

            pm_text = {
                'cash': 'เงินสด',
                'transfer': 'โอนเงิน/QR',
                'mixed': 'เงินสด+โอน'
            }.get(s['payment_method'], s['payment_method'])
            pm_item = QTableWidgetItem(pm_text)
            pm_item.setTextAlignment(Qt.AlignCenter)

            status_map = {
                'synced': 'ซิงก์สำเร็จ',
                'pending': 'รอซิงก์',
                'failed': 'ซิงก์ไม่ผ่าน',
                'cancelled': 'ยกเลิกแล้ว (Void)'
            }
            st_text = status_map.get(s['status'], s['status'])
            st_item = QTableWidgetItem(st_text)
            st_item.setTextAlignment(Qt.AlignCenter)

            if s['status'] == 'cancelled':
                st_item.setForeground(QColor("#dc2626"))
                st_item.setFont(QFont("Tahoma", 10, QFont.Bold))
                doc_item.setForeground(QColor("#94a3b8"))
            elif s['status'] == 'synced':
                st_item.setForeground(QColor("#16a34a"))
            elif s['status'] == 'pending':
                st_item.setForeground(QColor("#d97706"))

            self.sales_table.setItem(row, 0, doc_item)
            self.sales_table.setItem(row, 1, time_item)
            self.sales_table.setItem(row, 2, items_count_item)
            self.sales_table.setItem(row, 3, sub_item)
            self.sales_table.setItem(row, 4, disc_item)
            self.sales_table.setItem(row, 5, net_item)
            self.sales_table.setItem(row, 6, pm_item)
            self.sales_table.setItem(row, 7, st_item)

        self.reprint_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        self.void_btn.setEnabled(False)
        self.items_table.setRowCount(0)
        self.detail_info_lbl.setText("กรุณาเลือกบิลจากตารางด้านบน")

    def filter_table(self, query):
        q = (query or "").strip().lower()
        if not q:
            self.display_sales(self.all_sales)
            return

        filtered = [
            s for s in self.all_sales
            if q in s['doc_number'].lower()
            or q in (s['customer_name'] or '').lower()
            or q in str(s['total_amount'])
            or q in s['payment_method'].lower()
        ]
        self.display_sales(filtered)

    def on_sale_selected(self):
        selected_rows = self.sales_table.selectedItems()
        if not selected_rows:
            self.selected_sale = None
            self.reprint_btn.setEnabled(False)
            self.edit_btn.setEnabled(False)
            self.void_btn.setEnabled(False)
            return

        row = self.sales_table.currentRow()
        item = self.sales_table.item(row, 0)
        if not item:
            return

        sale = item.data(Qt.UserRole)
        self.selected_sale = sale

        # Populate Items table
        self.items_table.setRowCount(0)
        for it in sale['items']:
            r = self.items_table.rowCount()
            self.items_table.insertRow(r)

            name_item = QTableWidgetItem(it['name'])
            qty_item = QTableWidgetItem(f"{float(it['qty']):g}")
            qty_item.setTextAlignment(Qt.AlignCenter)

            u_price = float(it['unit_price'])
            price_item = QTableWidgetItem(f"{u_price:,.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            tot = float(it['total_price'])
            tot_item = QTableWidgetItem(f"{tot:,.2f}")
            tot_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.items_table.setItem(r, 0, name_item)
            self.items_table.setItem(r, 1, qty_item)
            self.items_table.setItem(r, 2, price_item)
            self.items_table.setItem(r, 3, tot_item)

        # Populate detail info
        subtotal = round(sale['total_amount'] + sale['discount_amount'], 2)
        status_thai = {
            'synced': 'ซิงก์สำเร็จ (ERP)',
            'pending': 'รอซิงก์ (ออฟไลน์)',
            'failed': 'ซิงก์ไม่ผ่าน',
            'cancelled': 'ยกเลิกแล้ว (Void)'
        }.get(sale['status'], sale['status'])

        cust_line = f"ลูกค้า: {sale['customer_name']}\n" if sale['customer_name'] else ""
        self.detail_info_lbl.setText(
            f"เลขที่: {sale['doc_number']}\n"
            f"เวลาขาย: {sale['created_at']}\n"
            f"{cust_line}"
            f"ยอดก่อนลด: ฿{subtotal:,.2f}\n"
            f"ส่วนลด: ฿{sale['discount_amount']:,.2f}\n"
            f"ยอดสุทธิ: ฿{sale['total_amount']:,.2f}\n"
            f"เงินสดรับ: ฿{sale['received_amount']:,.2f}\n"
            f"สถานะ: {status_thai}"
        )

        self.reprint_btn.setEnabled(True)
        # Edit bill is always available (if already void, cashier can still reload items to re-sell)
        self.edit_btn.setEnabled(True)
        # Void bill is only available if not already cancelled
        self.void_btn.setEnabled(sale['status'] != 'cancelled')

    def reprint_bill(self):
        """พิมพ์ใบเสร็จซ้ำ (Reprint)"""
        if not self.selected_sale:
            return

        sale = self.selected_sale
        receipt_items_data = [
            {
                'name': it['name'],
                'qty': it['qty'],
                'unit_price': it['unit_price'],
                'total_price': it['total_price'],
                'is_weight_item': it.get('is_weight_item', False)
            } for it in sale['items']
        ]

        receipt_data = {
            'doc_number': sale['doc_number'],
            'subtotal': round(sale['total_amount'] + sale['discount_amount'], 2),
            'total': sale['total_amount'],
            'discount_amount': sale['discount_amount'],
            'satang_discount': 0.0,
            'payment_method': sale['payment_method'],
            'cash_received': sale['received_amount'],
            'item_count': len(receipt_items_data),
            'total_qty': sum(float(it.get('qty', 0) or 0) for it in receipt_items_data),
            'is_full_tax': sale['is_full_tax'],
            'customer_name': sale['customer_name'],
            'customer_tax_id': sale['customer_tax_id'],
            'customer_address': sale['customer_address'],
            'cashier': str(sale['cashier_salesman_id'] or self.config.get('cashier_name', '01')),
            'cashier_name': self.config.get('cashier_name', 'Unknown'),
            'branch': self.config.get('branch_name', ''),
            'date': sale['created_at'],
            'items': receipt_items_data,
            'is_reprint': True  # Flag reprint
        }

        dlg = ReceiptDialog(self, receipt_data=receipt_data)
        dlg.exec()

    def void_bill(self):
        """ยกเลิกบิล (Void) คืนสต๊อกและยอดเงิน"""
        if not self.selected_sale:
            return

        sale = self.selected_sale
        if sale['status'] == 'cancelled':
            QMessageBox.warning(self, "แจ้งเตือน", "บิลนี้ถูกยกเลิกไปแล้ว")
            return

        # 1. ยืนยันการยกเลิก
        confirm = QMessageBox.question(
            self,
            "ยืนยันการยกเลิกบิล (Void)",
            f"ต้องการยกเลิกบิล {sale['doc_number']}\nยอดสุทธิ: ฿{sale['total_amount']:,.2f}\n\n"
            f"การยกเลิกจะคืนสต๊อกสินค้าและปรับลดยอดเงินในระบบ ยืนยันหรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # 2. ระบุเหตุผลการยกเลิก
        reason, ok = QInputDialog.getText(
            self,
            "เหตุผลการยกเลิกบิล",
            "กรุณาระบุเหตุผลการยกเลิก:",
            QLineEdit.EchoMode.Normal,
            "ลูกค้าขอยกเลิก / คีย์ผิด"
        )
        if not ok or not reason.strip():
            QMessageBox.warning(self, "แจ้งเตือน", "ต้องระบุเหตุผลในการยกเลิกบิล")
            return
        reason = reason.strip()

        # 3. ดำเนินการยกเลิก (Void)
        success = self._execute_void(sale, reason)
        if success:
            QMessageBox.information(self, "สำเร็จ", f"ยกเลิกบิล {sale['doc_number']} เรียบร้อยแล้ว")
            self.load_sales()

    def edit_bill(self):
        """
        แก้ไขบิล (Edit Bill)
        - ตรวจสอบว่าตะกร้าปัจจุบันว่างหรือไม่
        - ยกเลิกบิลเดิม (ถ้ายังไม่ได้ยกเลิก)
        - ส่งสัญญาณให้ MainWindow ดึงรายการและส่วนลดกลับเข้าตะกร้า
        """
        if not self.selected_sale:
            return

        sale = self.selected_sale
        parent_window = self.parent()

        # ตรวจสอบว่าตะกร้ามีสินค้าค้างหรือไม่
        if parent_window and hasattr(parent_window, 'cart_table') and parent_window.cart_table.rowCount() > 0:
            QMessageBox.warning(
                self,
                "แจ้งเตือน",
                "มีสินค้าค้างอยู่ในตะกร้าหน้าขายปัจจุบัน\nกรุณาคิดเงินให้เสร็จ พักบิล หรือล้างตะกร้าก่อนแก้ไขบิลเดิม"
            )
            return

        # ถ้ายกเลิกแล้ว: โหลดเข้าตะกร้าได้ทันที
        if sale['status'] == 'cancelled':
            confirm = QMessageBox.question(
                self,
                "ดึงรายการกลับเข้าตะกร้า",
                f"บิล {sale['doc_number']} ถูกยกเลิกไปแล้ว\nต้องการดึงรายการสินค้าและส่วนลดกลับเข้าตะกร้าเพื่อคิดเงินใหม่ใช่หรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.edit_bill_requested.emit(sale)
                self.accept()
            return

        # ถ้ายังไม่ยกเลิก: ยืนยันการยกเลิกบิลเดิมก่อน
        confirm = QMessageBox.question(
            self,
            "ยืนยันแก้ไขบิล",
            f"ระบบจะทำการยกเลิกบิลเดิม ({sale['doc_number']})\n"
            f"และดึงรายการสินค้าทั้งหมดพร้อมส่วนลดกลับเข้าตะกร้า\n"
            f"เพื่อให้คุณแก้ไขรายการ/จำนวน/ส่วนลด แล้วคิดเงินใหม่\n\nต้องการดำเนินการต่อหรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # ยกเลิกบิลเดิม
        reason = f"แก้ไขบิล: ดึงรายการกลับมาคิดเงินใหม่ ({sale['doc_number']})"
        success = self._execute_void(sale, reason)
        if not success:
            return

        # ส่งรายการกลับเข้าตะกร้า
        self.edit_bill_requested.emit(sale)
        self.accept()

    def _execute_void(self, sale, reason):
        """ส่งคำขอยกเลิกบิลไป ERP หรืออัปเดตในเครื่อง"""
        api_url = (self.config.get('api_url') or "").rstrip("/")
        pos_token = self.config.get('pos_token') or ""

        # กรณีบิลซิงก์ขึ้น ERP แล้ว -> ต้องยิงไปยกเลิกที่ ERP ด้วย
        if sale['status'] == 'synced' and api_url and pos_token:
            try:
                headers = {
                    'Authorization': f"Bearer {pos_token}",
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
                server_shift_id = (
                    self.current_shift.get('server_id')
                    or self.current_shift.get('id')
                    or sale.get('shift_id')
                )
                payload = {
                    'receipt_no': sale['doc_number'],
                    'shift_id': server_shift_id,
                    'reason': reason
                }

                resp = requests.post(
                    f"{api_url}/api/pos/receipt/void",
                    json=payload,
                    headers=headers,
                    timeout=15
                )

                if resp.status_code not in (200, 201):
                    err_msg = "เซิร์ฟเวอร์ปฏิเสธการยกเลิกบิล"
                    try:
                        resp_json = resp.json()
                        err_msg = resp_json.get('message', err_msg)
                    except Exception:
                        err_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    QMessageBox.critical(self, "ไม่สามารถยกเลิกบิลได้", f"ERP แจ้งข้อผิดพลาด:\n{err_msg}")
                    return False
            except Exception as e:
                logger.exception("Error calling void API")
                QMessageBox.critical(self, "ข้อผิดพลาดเครือข่าย", f"ไม่สามารถติดต่อ ERP ได้:\n{str(e)}")
                return False

        # อัปเดตสถานะใน SQLite เป็น cancelled
        try:
            session = init_db(f'sqlite:///{self.db_path}')
            db_sale = session.query(Sale).filter_by(local_sale_id=sale['local_sale_id']).first()
            if db_sale:
                db_sale.status = 'cancelled'

            # ยกเลิก Outbox ที่ค้างอยู่ (ถ้ามี)
            outbox_entries = session.query(Outbox).filter_by(aggregate_id=sale['local_sale_id']).all()
            for ob in outbox_entries:
                ob.status = 'cancelled'
                ob.last_error = f"Voided locally: {reason}"

            session.commit()
            session.close()
            return True
        except Exception as e:
            logger.exception("Error updating sale status to cancelled in SQLite")
            QMessageBox.critical(self, "ข้อผิดพลาดฐานข้อมูล", f"ไม่สามารถอัปเดตสถานะบิลในเครื่องได้:\n{str(e)}")
            return False
