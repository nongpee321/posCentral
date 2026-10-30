import traceback
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QMessageBox, QFrame, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from database.models import init_db, Product

class ScaleWeightDialog(QDialog):
    """
    หน้าต่างสินค้าชั่งน้ำหนัก:
    - รองรับการยิงบาร์โค้ด / สแกน QR สินค้า
    - หรือค้นหา / เลือกจากรายชื่อสินค้า
    - ใส่จำนวนกิโลกรัม (กก.) ทศนิยม 3 ตำแหน่ง
    - คำนวณราคาและส่งเข้าตะกร้าสินค้า
    """
    def __init__(self, parent=None, db_path="pos.db"):
        super().__init__(parent)
        self.parent_window = parent
        self.db_path = db_path
        self.selected_product = None
        self.entered_weight = 1.000
        
        self.setWindowTitle("สินค้าชั่งน้ำหนัก (สแกนบาร์โค้ด/QR และระบุกิโลกรัม)")
        self.setFixedWidth(520)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, sans-serif; }
            QLabel { color: #1e293b; font-size: 14px; }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background: white; border: 1px solid #cbd5e1; border-radius: 8px;
                padding: 10px; font-size: 15px; color: #0f172a;
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

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Box
        header_frame = QFrame()
        header_frame.setStyleSheet("background: linear-gradient(135deg, #0d9488 0%, #115e59 100%); border-radius: 10px; padding: 12px;")
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(10, 8, 10, 8)
        
        title_lbl = QLabel("ขายสินค้าชั่งน้ำหนัก (กิโลกรัม)")
        title_lbl.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        sub_lbl = QLabel("ยิงบาร์โค้ด / QR สินค้า หรือเลือกรายการ แล้วระบุกิโลกรัม")
        sub_lbl.setStyleSheet("color: #ccfbf1; font-size: 13px;")
        h_layout.addWidget(title_lbl)
        h_layout.addWidget(sub_lbl)
        layout.addWidget(header_frame)

        # 1. Barcode / QR Scan Field (Default Focused)
        scan_box = QVBoxLayout()
        scan_lbl = QLabel("สแกนบาร์โค้ด / QR สินค้า หรือพิมพ์รหัส:")
        scan_lbl.setStyleSheet("font-weight: bold; color: #0f766e;")
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("ยิงบาร์โค้ด / QR หรือ SKU ที่นี่แล้วกด Enter...")
        self.scan_input.setStyleSheet("border: 2px dashed #0d9488; background: #f0fdfa; font-weight: bold;")
        self.scan_input.returnPressed.connect(self.on_scan_barcode)
        scan_box.addWidget(scan_lbl)
        scan_box.addWidget(self.scan_input)
        layout.addLayout(scan_box)

        # 2. Product Selector Dropdown
        prod_box = QVBoxLayout()
        prod_lbl = QLabel("หรือเลือกสินค้าจากรายการ:")
        prod_lbl.setStyleSheet("font-weight: bold; color: #334155;")
        self.prod_combo = QComboBox()
        self.prod_combo.setMaxVisibleItems(12)
        self.prod_combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.prod_combo.currentIndexChanged.connect(self.on_product_combo_changed)
        prod_box.addWidget(prod_lbl)
        prod_box.addWidget(self.prod_combo)
        layout.addLayout(prod_box)

        # Product Info Banner
        self.info_card = QFrame()
        self.info_card.setStyleSheet("background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px;")
        info_layout = QHBoxLayout(self.info_card)
        self.prod_name_lbl = QLabel("กรุณาเลือกหรือสแกนสินค้า")
        self.prod_name_lbl.setStyleSheet("font-weight: bold; font-size: 15px; color: #0f172a;")
        self.prod_price_lbl = QLabel("฿0.00 / กก.")
        self.prod_price_lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #b91c1c;")
        info_layout.addWidget(self.prod_name_lbl, 1)
        info_layout.addWidget(self.prod_price_lbl, 0)
        layout.addWidget(self.info_card)

        # 3. Weight Input Field (กิโลกรัม)
        weight_box = QVBoxLayout()
        weight_lbl = QLabel("น้ำหนักสินค้า (กิโลกรัม):")
        weight_lbl.setStyleSheet("font-weight: bold; font-size: 15px; color: #0d9488;")
        
        weight_row = QHBoxLayout()
        self.weight_input = QDoubleSpinBox()
        self.weight_input.setDecimals(3)
        self.weight_input.setRange(0.001, 999.000)
        self.weight_input.setSingleStep(0.100)
        self.weight_input.setValue(1.000)
        self.weight_input.setStyleSheet("font-size: 22px; font-weight: bold; color: #0f172a; height: 50px;")
        self.weight_input.valueChanged.connect(self.update_calc_total)
        
        kg_unit_lbl = QLabel("กก. (kg)")
        kg_unit_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #475569;")
        
        weight_row.addWidget(self.weight_input, 1)
        weight_row.addWidget(kg_unit_lbl)
        weight_box.addWidget(weight_lbl)
        weight_box.addLayout(weight_row)
        layout.addLayout(weight_box)

        # Quick Weight Buttons (+100g, +250g, +500g, +1kg)
        quick_row = QHBoxLayout()
        for q_label, q_val in [("0.5 กก.", 0.5), ("1.0 กก.", 1.0), ("1.5 กก.", 1.5), ("2.0 กก.", 2.0)]:
            btn = QPushButton(q_label)
            btn.setStyleSheet("background: #e2e8f0; color: #334155; border-radius: 6px; padding: 6px; font-weight: bold;")
            btn.clicked.connect(lambda checked=False, v=q_val: self.weight_input.setValue(v))
            quick_row.addWidget(btn)
        layout.addLayout(quick_row)

        # Calculated Total Price Display
        total_frame = QFrame()
        total_frame.setStyleSheet("background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 12px;")
        tot_layout = QHBoxLayout(total_frame)
        tot_label = QLabel("รวมเป็นเงิน:")
        tot_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #991b1b;")
        self.calc_total_lbl = QLabel("฿0.00")
        self.calc_total_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #b91c1c;")
        tot_layout.addWidget(tot_label)
        tot_layout.addStretch()
        tot_layout.addWidget(self.calc_total_lbl)
        layout.addWidget(total_frame)

        # Action Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setStyleSheet("background: #e2e8f0; color: #475569; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 15px;")
        cancel_btn.clicked.connect(self.reject)
        
        self.submit_btn = QPushButton("เพิ่มลงตะกร้าสินค้า (Enter)")
        self.submit_btn.setStyleSheet("background: #0d9488; color: white; border-radius: 8px; padding: 12px; font-weight: bold; font-size: 16px;")
        self.submit_btn.clicked.connect(self.on_submit)
        
        btn_row.addWidget(cancel_btn, 1)
        btn_row.addWidget(self.submit_btn, 2)
        layout.addLayout(btn_row)

        # Focus scan input immediately
        QTimer.singleShot(100, self.scan_input.setFocus)

    def load_products(self):
        session = init_db(f"sqlite:///{self.db_path}")
        try:
            products = session.query(Product).filter(Product.is_active == True).all()
            if not products:
                return

            def sort_key(p):
                name = (p.name_th or '').lower()
                is_sc = getattr(p, 'is_scale_item', False) or ('กก' in name) or ('ชั่ง' in name) or ('สด' in name) or ('กิโล' in name)
                return (0 if is_sc else 1, p.name_th or '')

            self.products_list = sorted(products, key=sort_key)
            self.prod_combo.clear()
            for p in self.products_list:
                price = p.pos_price or p.default_price or 0.0
                self.prod_combo.addItem(f"{p.sku_code} - {p.name_th} (฿{price:,.2f}/กก.)", p.id)

            if self.products_list:
                self.selected_product = self.products_list[0]
                self.update_product_info()
        finally:
            session.close()

    def on_product_combo_changed(self, idx):
        if hasattr(self, 'products_list') and 0 <= idx < len(self.products_list):
            self.selected_product = self.products_list[idx]
            self.update_product_info()

    def update_product_info(self):
        if not self.selected_product:
            self.prod_name_lbl.setText("ไม่พบสินค้า")
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
        code = self.scan_input.text().strip()
        if not code:
            return
            
        session = init_db(f"sqlite:///{self.db_path}")
        try:
            # 1. ลองค้นหาตรงตาม Barcode หรือ SKU
            prod = session.query(Product).filter(
                (Product.barcode == code) | 
                (Product.sku_code == code) |
                (Product.sku_code.endswith(code))
            ).first()
            
            if prod:
                self.selected_product = prod
                # เลื่อน combo ให้ตรง
                for i in range(self.prod_combo.count()):
                    if self.prod_combo.itemData(i) == prod.id:
                        self.prod_combo.setCurrentIndex(i)
                        break
                self.update_product_info()
                self.scan_input.clear()
                # Focus ไปที่ช่องใส่น้ำหนัก
                self.weight_input.setFocus()
                self.weight_input.selectAll()
            else:
                QMessageBox.warning(self, "ไม่พบสินค้า", f"ไม่พบสินค้าที่มีรหัสหรือบาร์โค้ด: '{code}'")
                self.scan_input.selectAll()
        finally:
            session.close()

    def on_submit(self):
        if not self.selected_product:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเลือกสินค้าก่อนบันทึก")
            return
            
        weight = float(self.weight_input.value())
        if weight <= 0:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาระบุน้ำหนักที่ถูกต้อง (มากกว่า 0)")
            return
            
        self.entered_weight = weight
        self.accept()
