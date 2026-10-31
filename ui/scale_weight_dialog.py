from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QMessageBox, QFrame, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QTimer
from database.models import init_db, Product


def is_scale_product(product):
    """
    ตรวจสอบว่าสินค้าเป็นประเภทชั่งน้ำหนักหรือไม่ (สินค้าชั่งน้ำหนักเท่านั้น)
    - มี flag is_scale_item / is_scale / is_weight
    - หรือชื่อสินค้ามีคำว่า ชั่ง, ซั่ง, กก., กิโลกรัม
    - หรือหน่วยเป็น กก. / kg
    - หรือ SKU / Barcode เป็น scale PLU (800xxx, 801xxx)
    """
    if not product:
        return False
    if isinstance(product, dict):
        if product.get('is_scale_item') or product.get('is_scale') or product.get('is_weight'):
            return True
        name = str(product.get('name_th') or '')
        sku = str(product.get('sku_code') or '')
        barcode = str(product.get('barcode') or '')
        unit = str(product.get('unit') or product.get('unit_name') or '')
    else:
        if getattr(product, 'is_scale_item', False) or getattr(product, 'is_scale', False) or getattr(product, 'is_weight', False):
            return True
        name = str(getattr(product, 'name_th', '') or '')
        sku = str(getattr(product, 'sku_code', '') or '')
        barcode = str(getattr(product, 'barcode', '') or '')
        unit = str(getattr(product, 'unit', '') or getattr(product, 'unit_name', '') or '')

    combined = f"{name} {sku} {barcode}".lower()
    if 'ชั่ง' in combined or 'ซั่ง' in combined:
        return True
    if '(กก.)' in combined or '(กก)' in combined or 'กก.' in combined or 'กิโลกรัม' in combined:
        return True
    if unit in ['กก.', 'กก', 'kg', 'KG', 'กิโลกรัม']:
        return True
    if sku.startswith('800') or sku.startswith('801') or (len(sku) == 6 and sku.startswith('80')):
        return True
    if barcode.startswith('800') or barcode.startswith('801') or (len(barcode) == 6 and barcode.startswith('80')):
        return True
    return False


class ScaleWeightDialog(QDialog):
    """
    หน้าต่างสินค้าชั่งน้ำหนัก:
    - กรองและแสดงเฉพาะสินค้าชั่งน้ำหนักอย่างเดียว
    - รองรับการยิงบาร์โค้ด / สแกน QR สินค้าชั่งน้ำหนัก
    - หรือค้นหา / เลือกจากรายชื่อสินค้าชั่งน้ำหนัก
    - ใส่จำนวนกิโลกรัม (กก.) ทศนิยม 3 ตำแหน่ง
    - คำนวณราคาและส่งเข้าตะกร้าสินค้า
    """
    def __init__(self, parent=None, db_path="pos.db", target_product=None, initial_weight=1.000):
        super().__init__(parent)
        self.parent_window = parent
        self.db_path = db_path
        self.target_product = target_product
        self.selected_product = target_product if (target_product and is_scale_product(target_product)) else None
        self.entered_weight = max(0.001, float(initial_weight or 1.000))
        self.products_list = []

        self.setWindowTitle("สินค้าชั่งน้ำหนัก (ระบุกิโลกรัม)")
        self.setFixedWidth(450)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, sans-serif; }
            QLabel { color: #1e293b; font-size: 14px; }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background: white; border: 1px solid #cbd5e1; border-radius: 8px;
                padding: 6px 10px; font-size: 14px; color: #0f172a;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border-color: #0d9488;
            }
            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 2px solid #cbd5e1;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #0f172a;
                selection-background-color: #0d9488;
                selection-color: #ffffff;
                border: 2px solid #0d9488;
                outline: none;
                font-size: 14px;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 40px;
                color: #0f172a;
                padding: 6px 10px;
                border-bottom: 1px solid #f1f5f9;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #ccfbf1;
                color: #0f766e;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #0d9488;
                color: #ffffff;
                font-weight: bold;
            }
        """)

        self.setup_ui()
        self.load_products()
        if self.selected_product:
            self.select_product(self.selected_product)
            self.weight_input.setValue(self.entered_weight)
            self.update_product_info()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 14, 18, 14)

        # Header Box (Compact & clean)
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #0f766e; border-radius: 8px; padding: 6px 12px;")
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(2)

        title_lbl = QLabel("ขายสินค้าชั่งน้ำหนัก (กิโลกรัม)")
        title_lbl.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        sub_lbl = QLabel("เฉพาะสินค้าประเภทชั่งน้ำหนักเท่านั้น ระบุกิโลกรัม")
        sub_lbl.setStyleSheet("color: #ccfbf1; font-size: 12px;")
        h_layout.addWidget(title_lbl)
        h_layout.addWidget(sub_lbl)
        layout.addWidget(header_frame)

        # 1. Barcode / QR Scan Field (Default Focused)
        scan_box = QVBoxLayout()
        scan_box.setSpacing(4)
        scan_lbl = QLabel("สแกนบาร์โค้ด / QR สินค้า หรือพิมพ์รหัส:")
        scan_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #0f766e;")
        self.scan_input = QLineEdit()
        self.scan_input.setFixedHeight(38)
        self.scan_input.setPlaceholderText("ยิงบาร์โค้ด / QR หรือ SKU สินค้าชั่งน้ำหนัก...")
        self.scan_input.setStyleSheet("border: 2px dashed #0d9488; background: #f0fdfa; font-weight: bold; font-size: 14px; padding: 4px 8px;")
        self.scan_input.returnPressed.connect(self.on_scan_barcode)
        scan_box.addWidget(scan_lbl)
        scan_box.addWidget(self.scan_input)
        layout.addLayout(scan_box)

        # 2. Product Selector Dropdown
        prod_box = QVBoxLayout()
        prod_box.setSpacing(4)
        prod_lbl = QLabel("หรือเลือกสินค้าชั่งน้ำหนักจากรายการ:")
        prod_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #334155;")
        self.prod_combo = QComboBox()
        self.prod_combo.setFixedHeight(38)
        self.prod_combo.setMaxVisibleItems(12)
        self.prod_combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.prod_combo.currentIndexChanged.connect(self.on_product_combo_changed)
        prod_box.addWidget(prod_lbl)
        prod_box.addWidget(self.prod_combo)
        layout.addLayout(prod_box)

        # Product Info Banner
        self.info_card = QFrame()
        self.info_card.setStyleSheet("background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 10px;")
        info_layout = QHBoxLayout(self.info_card)
        info_layout.setContentsMargins(8, 4, 8, 4)
        self.prod_name_lbl = QLabel("กรุณาเลือกหรือสแกนสินค้าชั่งน้ำหนัก")
        self.prod_name_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #0f172a;")
        self.prod_price_lbl = QLabel("฿0.00 / กก.")
        self.prod_price_lbl.setStyleSheet("font-weight: bold; font-size: 15px; color: #b91c1c;")
        info_layout.addWidget(self.prod_name_lbl, 1)
        info_layout.addWidget(self.prod_price_lbl, 0)
        layout.addWidget(self.info_card)

        # 3. Weight Input Field (กิโลกรัม)
        weight_box = QVBoxLayout()
        weight_box.setSpacing(4)
        weight_lbl = QLabel("น้ำหนักสินค้า (กิโลกรัม):")
        weight_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #0d9488;")

        weight_row = QHBoxLayout()
        self.weight_input = QDoubleSpinBox()
        self.weight_input.setDecimals(3)
        self.weight_input.setRange(0.001, 999.000)
        self.weight_input.setSingleStep(0.100)
        self.weight_input.setValue(self.entered_weight)
        self.weight_input.setStyleSheet("font-size: 20px; font-weight: bold; color: #0f172a; height: 44px; padding: 4px 8px;")
        self.weight_input.valueChanged.connect(self.update_calc_total)

        kg_unit_lbl = QLabel("กก. (kg)")
        kg_unit_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #475569;")
        weight_row.addWidget(self.weight_input, 1)
        weight_row.addWidget(kg_unit_lbl)
        weight_box.addWidget(weight_lbl)
        weight_box.addLayout(weight_row)
        layout.addLayout(weight_box)

        # Calculated Total Price Display
        total_frame = QFrame()
        total_frame.setStyleSheet("background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 8px 12px;")
        tot_layout = QHBoxLayout(total_frame)
        tot_layout.setContentsMargins(10, 6, 10, 6)
        tot_label = QLabel("รวมเป็นเงิน:")
        tot_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #991b1b;")
        self.calc_total_lbl = QLabel("฿0.00")
        self.calc_total_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #b91c1c;")
        tot_layout.addWidget(tot_label)
        tot_layout.addStretch()
        tot_layout.addWidget(self.calc_total_lbl)
        layout.addWidget(total_frame)

        # Action Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setFixedHeight(42)
        cancel_btn.setStyleSheet("background: #e2e8f0; color: #475569; border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 14px;")
        cancel_btn.clicked.connect(self.reject)

        self.submit_btn = QPushButton("เพิ่มลงตะกร้าสินค้า (Enter)")
        self.submit_btn.setFixedHeight(42)
        self.submit_btn.setStyleSheet("background: #0d9488; color: white; border-radius: 8px; padding: 8px 18px; font-weight: bold; font-size: 15px;")
        self.submit_btn.clicked.connect(self.on_submit)

        btn_row.addWidget(cancel_btn, 1)
        btn_row.addWidget(self.submit_btn, 2)
        layout.addLayout(btn_row)

        # Focus scan input immediately
        QTimer.singleShot(100, self.scan_input.setFocus)

    def load_products(self):
        session = init_db(f"sqlite:///{self.db_path}")
        try:
            products = session.query(Product).filter(Product.is_active == True).all()  # noqa: E712
            if not products:
                return

            # กรองเฉพาะสินค้าชั่งน้ำหนักอย่างเดียว
            self.products_list = [p for p in products if is_scale_product(p)]
            self.products_list.sort(key=lambda p: (p.name_th or '').lower())

            self.prod_combo.clear()
            if not self.products_list:
                self.prod_combo.addItem("ไม่มีสินค้าประเภทชั่งน้ำหนักในระบบ", None)
                self.selected_product = None
                self.update_product_info()
                return

            for p in self.products_list:
                price = p.pos_price or p.default_price or 0.0
                self.prod_combo.addItem(f"{p.sku_code} - {p.name_th} (฿{price:,.2f}/กก.)", p.id)

            if not self.selected_product and self.products_list:
                self.selected_product = self.products_list[0]
                self.update_product_info()
        finally:
            session.close()

    def select_product(self, prod):
        if not prod:
            return
        prod_id = prod.get('id') if isinstance(prod, dict) else getattr(prod, 'id', None)
        for i in range(self.prod_combo.count()):
            if self.prod_combo.itemData(i) == prod_id:
                self.prod_combo.setCurrentIndex(i)
                break
        self.selected_product = prod
        self.update_product_info()

    def on_product_combo_changed(self, idx):
        if hasattr(self, 'products_list') and 0 <= idx < len(self.products_list):
            self.selected_product = self.products_list[idx]
            self.update_product_info()

    def update_product_info(self):
        if not self.selected_product:
            self.prod_name_lbl.setText("ไม่พบสินค้าชั่งน้ำหนัก")
            self.prod_price_lbl.setText("฿0.00 / กก.")
            self.update_calc_total()
            return

        price = float(self.selected_product.pos_price or self.selected_product.default_price or 0.0)
        self.prod_name_lbl.setText(f"{self.selected_product.name_th}")
        self.prod_price_lbl.setText(f"฿{price:,.2f} / กก.")
        self.update_calc_total()

    def update_calc_total(self):
        if not self.selected_product:
            self.calc_total_lbl.setText("฿0.00")
            return
        price = float(self.selected_product.pos_price or self.selected_product.default_price or 0.0)
        weight = float(self.weight_input.value())
        total = price * weight
        self.calc_total_lbl.setText(f"฿{total:,.2f}")

    def on_scan_barcode(self):
        from services.barcode_lookup import lookup_product, normalize_scan_text
        from services.scale_service import ScaleBarcodeParser

        raw_code = self.scan_input.text()
        code, digits = normalize_scan_text(raw_code)
        if not code:
            return

        session = init_db(f"sqlite:///{self.db_path}")
        try:
            result = lookup_product(session, raw_code, scale_parser=ScaleBarcodeParser)
            status = result.get('status')
            prod = result.get('product')
            if status == 'ambiguous' and result.get('products'):
                prod = result['products'][0]

            if prod is None:
                search_code = digits or code
                prod = session.query(Product).filter(
                    (Product.barcode == search_code) |
                    (Product.sku_code == search_code) |
                    (Product.sku_code.endswith(search_code))
                ).first()

            if prod:
                # ตรวจสอบว่าสินค้าเป็นประเภทชั่งน้ำหนักหรือไม่
                if not is_scale_product(prod):
                    QMessageBox.warning(
                        self,
                        "แจ้งเตือน",
                        f"สินค้า '{prod.name_th}' เป็นสินค้าขายตามจำนวนชิ้น ไม่ใช่สินค้าประเภทชั่งน้ำหนัก\n(ฟังก์ชันนี้ใช้ได้เฉพาะสินค้าชั่งน้ำหนักเท่านั้น)"
                    )
                    self.scan_input.selectAll()
                    return

                self.select_product(prod)
                if status == 'scale' and result.get('scale', {}).get('weight'):
                    try:
                        self.weight_input.setValue(float(result['scale']['weight']))
                    except Exception:
                        pass
                self.scan_input.clear()
                # Focus ไปที่ช่องใส่น้ำหนัก
                self.weight_input.setFocus()
                self.weight_input.selectAll()
            else:
                shown = digits if digits and digits != code else code
                QMessageBox.warning(self, "ไม่พบสินค้า", f"ไม่พบสินค้าที่มีรหัสหรือบาร์โค้ด: '{shown}'")
                self.scan_input.selectAll()
        finally:
            session.close()

    def on_submit(self):
        if not self.selected_product:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกสินค้าประเภทชั่งน้ำหนักก่อนบันทึก")
            return

        if not is_scale_product(self.selected_product):
            QMessageBox.warning(self, "แจ้งเตือน", "สินค้าที่เลือกไม่ใช่สินค้าประเภทชั่งน้ำหนัก")
            return

        weight = float(self.weight_input.value())
        if weight <= 0:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุน้ำหนักที่ถูกต้อง (มากกว่า 0)")
            return

        self.entered_weight = weight
        self.accept()
