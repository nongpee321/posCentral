import logging
import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from database.models import init_db, QtyPromotion, Product

logger = logging.getLogger("pos_promotions_dialog")


class PromotionListDialog(QDialog):
    """
    หน้าต่างตรวจสอบรายการโปรโมชั่น (เช่น ซื้อ 3 แพ็ค 100, ซื้อ N แถม M, ลดราคาพิเศษ)
    """
    def __init__(self, parent=None, db_path='pos.db', branch_name='ไม่ระบุสาขา', sync_worker=None, api_url='', pos_token=''):
        super().__init__(parent)
        self.db_path = db_path
        self.branch_name = branch_name or 'สาขาปัจจุบัน'
        self.sync_worker = sync_worker
        self.api_url = (api_url or '').rstrip('/')
        self.pos_token = pos_token or ''

        self.setObjectName("PromotionDialog")
        self.setWindowTitle(f"รายการโปรโมชั่น - {self.branch_name}")
        self.resize(1000, 620)
        self.setMinimumSize(850, 500)
        self.setStyleSheet("""
            #PromotionDialog {
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
        self.load_promotions_data()

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

        title_lbl = QLabel(f"รายการโปรโมชั่นที่ใช้งานได้: {self.branch_name}")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #0f172a;")

        self.summary_lbl = QLabel("กำลังโหลดข้อมูลโปรโมชั่น...")
        self.summary_lbl.setStyleSheet("color: #475569; font-size: 11pt; font-weight: 500;")

        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.summary_lbl)

        layout.addWidget(header_frame)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        type_lbl = QLabel("ประเภทโปรโมชั่น:")
        type_lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f1f5f9;")

        self.type_combo = QComboBox()
        self.type_combo.setStyleSheet("""
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
        self.type_combo.addItem("ทุกประเภท", userData=None)
        self.type_combo.addItem("ราคาชุด / ยกแพ็ค (Bundle)", userData="bundle_price")
        self.type_combo.addItem("ซื้อแถมสินค้า (Free Item)", userData="free_item")
        self.type_combo.addItem("ส่วนลดพิเศษ (Discount)", userData="discount")
        self.type_combo.currentIndexChanged.connect(self._filter_table)

        search_lbl = QLabel("ค้นหา:")
        search_lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #f1f5f9;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("พิมพ์ชื่อโปรโมชั่น, รหัส, หรือชื่อสินค้า...")
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

        self.refresh_btn = QPushButton("รีเฟรชโปรโมชั่น")
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
        self.refresh_btn.clicked.connect(self.refresh_from_server)

        filter_layout.addWidget(type_lbl)
        filter_layout.addWidget(self.type_combo)
        filter_layout.addWidget(search_lbl)
        filter_layout.addWidget(self.search_input, 1)
        filter_layout.addWidget(self.refresh_btn)

        layout.addLayout(filter_layout)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "รหัสโปรโมชั่น",
            "ชื่อโปรโมชั่น",
            "ประเภท",
            "สินค้าที่ร่วมรายการ",
            "เงื่อนไขโปรโมชั่น",
            "สถานะ"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
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
        hint_lbl = QLabel("ระบบจะคำนวณและลดราคาโปรโมชั่นให้อัตโนมัติในหน้าขายทันทีเมื่อสั่งซื้อครบตามจำนวนที่กำหนด")
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

    def load_promotions_data(self):
        try:
            session = init_db(f'sqlite:///{self.db_path}')
            promotions = session.query(QtyPromotion).filter(QtyPromotion.is_active == True).all()

            # Pre-load products map for names
            product_ids = set()
            for p in promotions:
                if p.product_id: product_ids.add(p.product_id)
                if p.free_product_id: product_ids.add(p.free_product_id)

            prod_map = {}
            if product_ids:
                products = session.query(Product).filter(Product.id.in_(list(product_ids))).all()
                prod_map = {prod.id: prod.name_th for prod in products}

            session.close()

            self._populate_table(promotions, prod_map)
        except Exception as e:
            logger.exception("Error loading promotions data")
            self.summary_lbl.setText("ไม่สามารถอ่านข้อมูลโปรโมชั่นได้")

    def _populate_table(self, promotions, prod_map):
        self.table.setRowCount(0)
        total_items = len(promotions)

        for row_idx, p in enumerate(promotions):
            self.table.insertRow(row_idx)

            code = str(p.code or '-')
            name = str(p.name or 'โปรโมชั่น')
            promo_type = p.promo_type or 'bundle_price'
            prod_name = prod_map.get(p.product_id, f"รหัสสินค้า: {p.product_id}")

            # Formatting promo condition & type label
            min_qty = float(p.min_qty or 1.0)
            min_qty_str = f"{int(min_qty)}" if min_qty.is_integer() else f"{min_qty:g}"

            if promo_type == 'bundle_price':
                type_label = "ราคาชุด / แพ็ค"
                b_price = float(p.bundle_price or 0.0)
                condition_str = f"ซื้อครบ {min_qty_str} ชิ้น ในราคาพิเศษ {b_price:,.2f} บาท"
            elif promo_type == 'free_item':
                type_label = "ซื้อแถมฟรี"
                free_qty = float(p.free_qty or 1.0)
                free_qty_str = f"{int(free_qty)}" if free_qty.is_integer() else f"{free_qty:g}"
                free_name = prod_map.get(p.free_product_id, prod_name)
                condition_str = f"ซื้อครบ {min_qty_str} ชิ้น แถมฟรี {free_name} x {free_qty_str}"
            elif promo_type == 'discount':
                type_label = "ลดราคา"
                disc_val = float(p.discount_value or 0.0)
                if p.discount_type == 'percent':
                    condition_str = f"ซื้อครบ {min_qty_str} ชิ้น ลดทันที {disc_val:g}%"
                else:
                    condition_str = f"ซื้อครบ {min_qty_str} ชิ้น ลดทันที {disc_val:,.2f} บาท"
            else:
                type_label = "โปรโมชั่นพิเศษ"
                condition_str = f"ซื้อครบ {min_qty_str} ชิ้น"

            item_code = QTableWidgetItem(code)
            item_code.setForeground(QColor("#0f172a"))

            item_name = QTableWidgetItem(name)
            item_name.setForeground(QColor("#0f172a"))

            item_type = QTableWidgetItem(type_label)
            item_type.setForeground(QColor("#0284c7"))
            item_type.setData(Qt.UserRole, promo_type)

            item_prod = QTableWidgetItem(prod_name)
            item_prod.setForeground(QColor("#0f172a"))

            item_cond = QTableWidgetItem(condition_str)
            item_cond.setForeground(QColor("#16a34a"))
            font = item_cond.font()
            font.setBold(True)
            item_cond.setFont(font)

            item_status = QTableWidgetItem("เปิดใช้งาน")
            item_status.setForeground(QColor("#15803d"))
            item_status.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row_idx, 0, item_code)
            self.table.setItem(row_idx, 1, item_name)
            self.table.setItem(row_idx, 2, item_type)
            self.table.setItem(row_idx, 3, item_prod)
            self.table.setItem(row_idx, 4, item_cond)
            self.table.setItem(row_idx, 5, item_status)

        if total_items == 0:
            self.summary_lbl.setText("ขณะนี้ยังไม่มีแคมเปญโปรโมชั่นที่เปิดใช้งาน")
        else:
            self.summary_lbl.setText(f"พบโปรโมชั่นทั้งหมด: {total_items:,} รายการ")

    def _filter_table(self):
        query = self.search_input.text().strip().lower()
        selected_type = self.type_combo.currentData()

        visible_count = 0
        for r in range(self.table.rowCount()):
            code = self.table.item(r, 0).text().lower() if self.table.item(r, 0) else ""
            name = self.table.item(r, 1).text().lower() if self.table.item(r, 1) else ""
            type_item = self.table.item(r, 2)
            row_type = type_item.data(Qt.UserRole) if type_item else ""
            prod = self.table.item(r, 3).text().lower() if self.table.item(r, 3) else ""
            cond = self.table.item(r, 4).text().lower() if self.table.item(r, 4) else ""

            # Check text query
            text_match = True
            if query:
                text_match = (query in code) or (query in name) or (query in prod) or (query in cond)

            # Check type filter
            type_match = True
            if selected_type is not None:
                type_match = (row_type == selected_type)

            is_visible = text_match and type_match
            self.table.setRowHidden(r, not is_visible)
            if is_visible:
                visible_count += 1

        self.summary_lbl.setText(f"แสดง: {visible_count:,} รายการ")

    def refresh_from_server(self):
        """
        รีเฟรชดึงข้อมูลโปรโมชั่นล่าสุดจาก ERP Server
        """
        if self.sync_worker and hasattr(self.sync_worker, 'trigger_sync'):
            self.summary_lbl.setText("กำลังซิงค์โปรโมชั่นล่าสุดจาก ERP...")
            self.sync_worker.trigger_sync()
            self.load_promotions_data()
            QMessageBox.information(self, "แจ้งเตือน", "สั่งซิงค์โปรโมชั่นล่าสุดจาก ERP เรียบร้อยแล้ว")
        elif self.api_url and self.pos_token:
            self.summary_lbl.setText("กำลังดาวน์โหลดโปรโมชั่นล่าสุด...")
            try:
                headers = {'Authorization': f'Bearer {self.pos_token}', 'Accept': 'application/json'}
                resp = requests.get(f'{self.api_url}/api/pos/promotions', headers=headers, timeout=10)
                if resp.status_code == 200:
                    promos = resp.json()
                    session = init_db(f'sqlite:///{self.db_path}')
                    session.query(QtyPromotion).delete(synchronize_session=False)
                    for item in promos:
                        session.add(QtyPromotion(
                            id=item.get('id'),
                            code=item.get('code'),
                            name=item.get('name') or '',
                            promo_type=item.get('promo_type') or 'bundle_price',
                            product_id=item.get('product_id'),
                            min_qty=float(item.get('min_qty') or 1.0),
                            free_product_id=item.get('free_product_id'),
                            free_qty=float(item.get('free_qty') or 0.0),
                            discount_type=item.get('discount_type'),
                            discount_value=float(item.get('discount_value') or 0.0),
                            bundle_price=float(item.get('bundle_price')) if item.get('bundle_price') is not None else None,
                            branch_id=item.get('branch_id'),
                            is_active=True,
                        ))
                    session.commit()
                    session.close()
                    self.load_promotions_data()
                    QMessageBox.information(self, "สำเร็จ", "อัปเดตข้อมูลโปรโมชั่นจากเซิร์ฟเวอร์เรียบร้อยแล้ว")
                else:
                    QMessageBox.warning(self, "แจ้งเตือน", f"เซิร์ฟเวอร์ตอบกลับสถานะ: {resp.status_code}")
            except Exception as e:
                QMessageBox.warning(self, "ข้อผิดพลาด", f"ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์เพื่อดึงโปรโมชั่นได้: {str(e)}")
        else:
            self.load_promotions_data()
            QMessageBox.information(self, "แจ้งเตือน", "โหลดข้อมูลโปรโมชั่นจากฐานข้อมูลเรียบร้อยแล้ว")
