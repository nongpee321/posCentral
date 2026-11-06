import sys
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from database.models import init_db, Product, Category

logger = logging.getLogger("pos_stock_check")


class StockCheckDialog(QDialog):
    """
    หน้าต่างตรวจสอบสต็อกสินค้าคงเหลือเฉพาะสาขาที่ Token เชื่อมต่ออยู่
    พร้อมฟิลเตอร์ค้นหาและกรองตามหมวดหมู่สินค้า
    """
    def __init__(self, parent=None, db_path='pos.db', branch_name='ไม่ระบุสาขา', sync_worker=None, api_url='', pos_token=''):
        super().__init__(parent)
        self.db_path = db_path
        self.branch_name = branch_name or 'สาขาปัจจุบัน'
        self.sync_worker = sync_worker
        self.api_url = api_url
        self.pos_token = pos_token
        self.categories_map = {}

        self.setObjectName("StockDialog")
        self.setWindowTitle(f"ตรวจสอบสต็อกสินค้าคงเหลือ - {self.branch_name}")
        self.resize(980, 620)
        self.setMinimumSize(820, 520)
        self.setStyleSheet("""
            #StockDialog {
                background-color: #1e293b;
                color: #ffffff;
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
                border: none;
            }
            QMessageBox QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)

        self._init_ui()
        self.load_categories()
        self.load_stock_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header bar
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)

        title_lbl = QLabel(f"สต็อกสินค้าคงเหลือ: {self.branch_name}")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #0f172a;")

        self.summary_lbl = QLabel("กำลังโหลดข้อมูลสต็อก...")
        self.summary_lbl.setStyleSheet("color: #475569; font-size: 11pt; font-weight: 500;")

        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.summary_lbl)

        layout.addWidget(header_frame)

        # Filter / Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)

        # Category Filter
        cat_lbl = QLabel("หมวดหมู่:")
        cat_lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f1f5f9;")

        self.category_combo = QComboBox()
        self.category_combo.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 2px solid #38bdf8;
                border-radius: 6px;
                font-size: 11pt;
                background-color: #ffffff;
                color: #0f172a;
                min-width: 180px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #0f172a;
                selection-background-color: #bae6fd;
                selection-color: #0f172a;
            }
        """)
        self.category_combo.currentIndexChanged.connect(self._filter_table)

        search_lbl = QLabel("ค้นหาสินค้า:")
        search_lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f1f5f9;")
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("พิมพ์ชื่อสินค้า, รหัส SKU, หรือบาร์โค้ด...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 2px solid #38bdf8;
                border-radius: 6px;
                font-size: 11pt;
                background-color: #ffffff;
                color: #0f172a;
            }
            QLineEdit:focus {
                border-color: #0284c7;
            }
        """)
        self.search_input.textChanged.connect(self._filter_table)

        self.refresh_btn = QPushButton("รีเฟรชสต็อก")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 10.5pt;
                font-weight: bold;
                padding: 9px 18px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_from_server_or_db)

        search_layout.addWidget(cat_lbl)
        search_layout.addWidget(self.category_combo)
        search_layout.addWidget(search_lbl)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.refresh_btn)

        layout.addLayout(search_layout)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "รหัส SKU",
            "ชื่อสินค้า",
            "หมวดหมู่",
            "บาร์โค้ด",
            "ราคาขาย (บาท)",
            "คงเหลือสาขานี้"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f1f5f9;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                gridline-color: #cbd5e1;
                font-size: 11pt;
            }
            QTableWidget::item {
                color: #0f172a;
                padding: 6px;
            }
            QTableWidget::item:selected {
                background-color: #bae6fd;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #e2e8f0;
                color: #0f172a;
                font-weight: bold;
                padding: 8px 6px;
                border: 1px solid #cbd5e1;
                font-size: 11pt;
            }
        """)

        layout.addWidget(self.table, 1)

        # Footer bar
        footer_layout = QHBoxLayout()
        hint_lbl = QLabel(f"แสดงเฉพาะสินค้าและยอดสต็อกคงเหลือของ: {self.branch_name}")
        hint_lbl.setStyleSheet("color: #94a3b8; font-size: 10pt;")

        close_btn = QPushButton("ปิดหน้าต่าง")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #475569;
                color: #ffffff;
                font-size: 10.5pt;
                font-weight: bold;
                padding: 8px 24px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        close_btn.clicked.connect(self.accept)

        footer_layout.addWidget(hint_lbl)
        footer_layout.addStretch()
        footer_layout.addWidget(close_btn)

        layout.addLayout(footer_layout)

    def load_categories(self):
        try:
            session = init_db(f'sqlite:///{self.db_path}')
            categories = session.query(Category).filter(Category.is_active == True).order_by(Category.name_th).all()
            self.categories_map = {c.id: c.name_th for c in categories}
            session.close()

            self.category_combo.blockSignals(True)
            self.category_combo.clear()
            self.category_combo.addItem("ทุกหมวดหมู่", userData=None)
            for c in categories:
                self.category_combo.addItem(c.name_th, userData=c.id)
            self.category_combo.blockSignals(False)
        except Exception as e:
            logger.exception("Error loading categories")

    def load_stock_data(self):
        try:
            session = init_db(f'sqlite:///{self.db_path}')
            query = session.query(Product).filter(Product.is_active == True)
            self.products_data = query.all()
            session.close()

            self._populate_table(self.products_data)
        except Exception as e:
            logger.exception("Error loading stock data")
            self.summary_lbl.setText("ไม่สามารถอ่านข้อมูลสต็อกได้")

    def _populate_table(self, products):
        self.table.setRowCount(0)
        total_items = len(products)
        in_stock_count = 0

        for row_idx, p in enumerate(products):
            self.table.insertRow(row_idx)

            sku = str(p.sku_code or '')
            name = str(p.name_th or '')
            cat_name = self.categories_map.get(p.category_id, 'ทั่วไป')
            barcode = str(p.barcode or '')
            price = f"{float(p.pos_price or p.default_price or 0.0):,.2f}"
            
            raw_stock = p.stock_qty
            if raw_stock is not None:
                stock_val = float(raw_stock)
                if stock_val > 0:
                    in_stock_count += 1
                stock_str = f"{stock_val:,.2f}" if p.is_scale_item else f"{int(stock_val):,}"
            else:
                stock_str = "ไม่จำกัด / ไม่ระบุ"

            # Create items with clear dark font color
            item_sku = QTableWidgetItem(sku)
            item_sku.setForeground(QColor("#0f172a"))

            item_name = QTableWidgetItem(name)
            item_name.setForeground(QColor("#0f172a"))

            item_cat = QTableWidgetItem(cat_name)
            item_cat.setForeground(QColor("#0f172a"))
            item_cat.setData(Qt.UserRole, p.category_id)

            item_barcode = QTableWidgetItem(barcode)
            item_barcode.setForeground(QColor("#0f172a"))

            item_price = QTableWidgetItem(price)
            item_price.setForeground(QColor("#0f172a"))
            item_price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            item_stock = QTableWidgetItem(stock_str)
            item_stock.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Highlight low or zero stock with high contrast
            if raw_stock is not None:
                if stock_val <= 0:
                    item_stock.setForeground(QColor("#b91c1c"))  # Dark Red
                    font = item_stock.font()
                    font.setBold(True)
                    item_stock.setFont(font)
                elif stock_val < 5:
                    item_stock.setForeground(QColor("#b45309"))  # Dark Amber
                    font = item_stock.font()
                    font.setBold(True)
                    item_stock.setFont(font)
                else:
                    item_stock.setForeground(QColor("#15803d"))  # Dark Green
                    font = item_stock.font()
                    font.setBold(True)
                    item_stock.setFont(font)
            else:
                item_stock.setForeground(QColor("#475569"))

            self.table.setItem(row_idx, 0, item_sku)
            self.table.setItem(row_idx, 1, item_name)
            self.table.setItem(row_idx, 2, item_cat)
            self.table.setItem(row_idx, 3, item_barcode)
            self.table.setItem(row_idx, 4, item_price)
            self.table.setItem(row_idx, 5, item_stock)

        self.summary_lbl.setText(f"ทั้งหมด: {total_items:,} รายการ | มีสต็อก: {in_stock_count:,} รายการ")

    def _filter_table(self):
        query = self.search_input.text().strip().lower()
        selected_cat_id = self.category_combo.currentData()

        visible_count = 0
        in_stock_visible = 0

        for r in range(self.table.rowCount()):
            sku = self.table.item(r, 0).text().lower() if self.table.item(r, 0) else ""
            name = self.table.item(r, 1).text().lower() if self.table.item(r, 1) else ""
            cat_item = self.table.item(r, 2)
            cat_id = cat_item.data(Qt.UserRole) if cat_item else None
            barcode = self.table.item(r, 3).text().lower() if self.table.item(r, 3) else ""

            # Check text query
            text_match = True
            if query:
                text_match = (query in sku) or (query in name) or (query in barcode)

            # Check category filter
            cat_match = True
            if selected_cat_id is not None:
                cat_match = (cat_id == selected_cat_id)

            is_visible = text_match and cat_match
            self.table.setRowHidden(r, not is_visible)

            if is_visible:
                visible_count += 1
                stock_text = self.table.item(r, 5).text() if self.table.item(r, 5) else "0"
                try:
                    val = float(stock_text.replace(',', ''))
                    if val > 0:
                        in_stock_visible += 1
                except ValueError:
                    pass

        self.summary_lbl.setText(f"แสดง: {visible_count:,} รายการ | มีสต็อก: {in_stock_visible:,} รายการ")

    def refresh_from_server_or_db(self):
        """
        รีเฟรชข้อมูลสต็อก หากมี sync_worker ให้กระตุ้นดึงข้อมูลล่าสุดจาก ERP
        """
        if self.sync_worker and hasattr(self.sync_worker, 'trigger_sync'):
            self.summary_lbl.setText("กำลังซิงค์สต็อกล่าสุดจาก ERP...")
            self.sync_worker.trigger_sync()
            self.load_categories()
            self.load_stock_data()
            QMessageBox.information(self, "แจ้งเตือน", "สั่งซิงค์ข้อมูลสต็อกล่าสุดจาก ERP เรียบร้อยแล้ว")
        else:
            self.load_categories()
            self.load_stock_data()
            QMessageBox.information(self, "แจ้งเตือน", "โหลดข้อมูลสต็อกปัจจุบันเรียบร้อยแล้ว")
