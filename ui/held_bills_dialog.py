import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt

class HeldBillsDialog(QDialog):
    def __init__(self, parent=None, held_bills=None):
        super().__init__(parent)
        self.setWindowTitle("รายการบิลที่พักไว้ (Held Bills)")
        self.setFixedSize(650, 420)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, sans-serif; }
            QLabel { color: #0f172a; }
            QTableWidget {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background: white;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f1f5f9;
                padding: 6px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #cbd5e1;
                color: #334155;
            }
            QPushButton {
                font-weight: bold;
                border-radius: 6px;
            }
        """)

        self.held_bills = held_bills or []
        self.selected_bill = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title = QLabel("รายการบิลที่พักไว้ในระบบ")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.count_lbl = QLabel(f"มีบิลพักอยู่ {len(self.held_bills)} ใบ")
        self.count_lbl.setStyleSheet("font-size: 14px; color: #64748b; font-weight: bold;")
        header_layout.addWidget(self.count_lbl)
        layout.addLayout(header_layout)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["เลขที่พัก", "ป้ายกำกับ / หมายเหตุ", "เวลาที่พัก", "ยอดรวม", "การจัดการ"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self.populate_table()

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("ปิดหน้าต่าง")
        close_btn.setStyleSheet("background-color: #e2e8f0; color: #334155; padding: 8px 16px; border: 1px solid #cbd5e1;")
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def populate_table(self):
        self.table.setRowCount(0)
        for i, bill in enumerate(self.held_bills):
            row = self.table.rowCount()
            self.table.insertRow(row)

            hold_no = bill.get('hold_no') or f"HOLD-{i+1}"
            label = bill.get('label') or bill.get('note') or "บิลพัก"
            time_str = bill.get('createdAt') or bill.get('time') or "-"
            if 'T' in time_str:
                time_str = time_str.split('T')[1][:8]
            total = float(bill.get('total_amount') or 0.0)

            no_item = QTableWidgetItem(hold_no)
            no_item.setTextAlignment(Qt.AlignCenter)
            label_item = QTableWidgetItem(label)
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignCenter)
            total_item = QTableWidgetItem(f"฿{total:,.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_item.setForeground(Qt.darkRed)

            self.table.setItem(row, 0, no_item)
            self.table.setItem(row, 1, label_item)
            self.table.setItem(row, 2, time_item)
            self.table.setItem(row, 3, total_item)

            resume_btn = QPushButton("ดึงกลับมาขาย")
            resume_btn.setStyleSheet("background-color: #3b82f6; color: white; padding: 4px 10px; border-radius: 4px;")
            resume_btn.clicked.connect(lambda _, b=bill: self.choose_bill(b))
            self.table.setCellWidget(row, 4, resume_btn)

    def choose_bill(self, bill):
        self.selected_bill = bill
        self.accept()
