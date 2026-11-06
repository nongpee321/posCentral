"""
CartItemEditDialog
หน้าต่างแก้ไขรายการสินค้าในตะกร้า:
- แก้ไขจำนวน (ชิ้น) หรือน้ำหนัก (กก.)
- ปรับเปลี่ยนราคาต่อหน่วย (กรณีมีสิทธิ์ / ต้องการปรับ)
- คำนวณยอดรวมให้อัตโนมัติแบบเรียลไทม์
- ปุ่มลัดเพิ่ม/ลด (+1, -1, +0.1, -0.1)
- รองรับการลบรายการออกจากตะกร้าได้โดยตรง
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QDoubleSpinBox
)
from PySide6.QtCore import Qt, Signal


class CartItemEditDialog(QDialog):
    # Signals
    item_updated = Signal(float, float)  # (new_qty, new_price)
    item_deleted = Signal()

    def __init__(self, parent=None, product_name="", current_qty=1.0, unit_price=0.0, is_scale=False):
        super().__init__(parent)
        self.setWindowTitle("แก้ไขรายการสินค้า (Edit Cart Item)")
        self.setFixedWidth(430)
        self.product_name = str(product_name or "")
        self.current_qty = float(current_qty or 1.0)
        self.unit_price = float(unit_price or 0.0)
        self.is_scale = is_scale or ('ชั่ง' in self.product_name.lower() or 'กก' in self.product_name.lower() or (self.current_qty % 1 != 0))
        
        self.result_qty = self.current_qty
        self.result_price = self.unit_price
        self.was_deleted = False

        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QLabel {
                color: #1e293b;
            }
            QDoubleSpinBox {
                background: white;
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 18px;
                font-weight: bold;
                color: #0f172a;
            }
            QDoubleSpinBox:focus {
                border-color: #0284c7;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Card
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #f1f5f9; border-radius: 8px; border: 1px solid #e2e8f0; padding: 10px;")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(4)

        title_lbl = QLabel(self.product_name)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #0f172a;")
        title_lbl.setWordWrap(True)
        header_layout.addWidget(title_lbl)

        unit_str = "กก." if self.is_scale else "หน่วย"
        price_sub = QLabel(f"ราคาต่อ{unit_str}: ฿ {self.unit_price:,.2f}")
        price_sub.setStyleSheet("font-size: 13px; color: #64748b;")
        header_layout.addWidget(price_sub)
        layout.addWidget(header_card)

        # Quantity / Weight Section
        qty_title = QLabel("ระบุจำนวน (ชิ้น) หรือน้ำหนัก (กก.):")
        qty_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #334155;")
        layout.addWidget(qty_title)

        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(0.001, 9999.0)
        self.qty_spin.setDecimals(3 if self.is_scale else 2)
        self.qty_spin.setSingleStep(0.1 if self.is_scale else 1.0)
        self.qty_spin.setValue(self.current_qty)
        self.qty_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qty_spin.valueChanged.connect(self.on_values_changed)
        layout.addWidget(self.qty_spin)

        # Quick Adjust Buttons
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(6)
        
        adjust_steps = [-1.0, +1.0, +2.0, +5.0] if not self.is_scale else [-0.5, -0.1, +0.1, +0.5, +1.0]
        for step in adjust_steps:
            label = f"{step:+g}"
            btn = QPushButton(label)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e2e8f0;
                    color: #1e293b;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #cbd5e1;
                }
            """)
            btn.clicked.connect(lambda _, s=step: self.adjust_qty(s))
            quick_layout.addWidget(btn)
        layout.addLayout(quick_layout)

        # Total Calculation Display Card
        total_card = QFrame()
        total_card.setStyleSheet("background-color: #ecfeff; border: 1px solid #a5f3fc; border-radius: 8px; padding: 10px;")
        total_layout = QHBoxLayout(total_card)
        total_layout.setContentsMargins(12, 8, 12, 8)
        
        total_desc = QLabel("ยอดรวมรายการนี้:")
        total_desc.setStyleSheet("font-size: 14px; font-weight: bold; color: #0e7490;")
        total_layout.addWidget(total_desc)

        total_layout.addStretch()

        self.total_lbl = QLabel()
        self.total_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #0891b2;")
        total_layout.addWidget(self.total_lbl)
        layout.addWidget(total_card)

        self.update_total_display()

        # Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.delete_btn = QPushButton("ลบรายการนี้")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 6px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #fecaca;
            }
        """)
        self.delete_btn.clicked.connect(self.on_delete_clicked)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("บันทึก")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        save_btn.clicked.connect(self.on_save_clicked)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def adjust_qty(self, step):
        new_val = max(0.001, round(self.qty_spin.value() + step, 3))
        self.qty_spin.setValue(new_val)

    def on_values_changed(self):
        self.update_total_display()

    def update_total_display(self):
        val = self.qty_spin.value()
        tot = round(val * self.unit_price, 2)
        self.total_lbl.setText(f"฿ {tot:,.2f}")

    def on_save_clicked(self):
        self.result_qty = round(self.qty_spin.value(), 3)
        self.result_price = self.unit_price
        self.was_deleted = False
        self.item_updated.emit(self.result_qty, self.result_price)
        self.accept()

    def on_delete_clicked(self):
        self.was_deleted = True
        self.item_deleted.emit()
        self.accept()
