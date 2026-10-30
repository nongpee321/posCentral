import traceback
import json
import sqlite3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

class PendingSyncDialog(QDialog):
    """
    หน้าต่างตรวจสอบรายการบิลค้าง Sync:
    - แสดงรายการบิลที่รอส่งขึ้น ERP หรือบิลที่ติดปัญหา
    - ปรับแต่ง UI ให้คมชัด สวยงาม สีสันตรงตามมาตรฐาน PopStar POS
    """
    def __init__(self, parent=None, db_path="pos.db"):
        super().__init__(parent)
        self.parent_window = parent
        self.db_path = db_path
        
        self.setWindowTitle("รายการบิลค้าง Sync (Offline / Pending Sales)")
        self.resize(880, 530)
        self.setStyleSheet("""
            QDialog { 
                background-color: #f8fafc; 
                font-family: 'Segoe UI', Tahoma, sans-serif; 
            }
            QLabel { 
                color: #0f172a; 
                font-size: 14px; 
            }
            QTableWidget {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                gridline-color: #e2e8f0;
                font-size: 13.5px;
                selection-background-color: #e0f2fe;
                selection-color: #0369a1;
            }
            QTableWidget::item {
                padding: 6px 8px;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f1f5f9;
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid #cbd5e1;
                font-weight: bold;
                color: #1e293b;
                font-size: 13.5px;
            }
            QHeaderView::section:vertical {
                background-color: #f8fafc;
                color: #64748b;
                border-right: 1px solid #e2e8f0;
                padding: 0 4px;
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
                border: 1px solid #1d4ed8;
            }
            QMessageBox QPushButton:hover {
                background-color: #1d4ed8;
            }
            QMessageBox QPushButton:pressed {
                background-color: #1e40af;
            }
        """)
        
        self.setup_ui()
        worker = getattr(self.parent_window, 'sync_worker', None)
        if worker:
            worker.manual_sync_finished.connect(self.on_manual_sync_finished)
        self.load_pending_sales()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Box with clean Qt gradient and bold white text
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b91c1c, stop:1 #991b1b);
                border-radius: 10px;
                border: 1px solid #7f1d1d;
            }
        """)
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(16, 14, 16, 14)
        h_layout.setSpacing(4)
        
        title_lbl = QLabel("ตรวจสอบรายการบิลค้างส่งเข้า ERP")
        title_lbl.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; background: transparent;")
        
        self.subtitle_lbl = QLabel("กำลังโหลดข้อมูลบิลค้าง...")
        self.subtitle_lbl.setStyleSheet("color: #fee2e2; font-size: 13.5px; font-weight: 500; background: transparent;")
        
        h_layout.addWidget(title_lbl)
        h_layout.addWidget(self.subtitle_lbl)
        layout.addWidget(header_frame)

        # Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["เลขที่บิล", "วันที่/เวลา", "ยอดรวม", "วิธีชำระ", "สถานะ", "สาเหตุ/ข้อผิดพลาด"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(self.table.styleSheet() + " QTableWidget { alternate-background-color: #f8fafc; }")
        layout.addWidget(self.table)

        # Bottom Actions
        btn_layout = QHBoxLayout()
        self.sync_now_btn = QPushButton("สั่ง Sync ทันที (Retry Sync)")
        self.sync_now_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.sync_now_btn.clicked.connect(self.trigger_sync_now)

        self.delete_btn = QPushButton("ลบบิลค้างนี้ (Discard)")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e11d48;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #be123c;
            }
            QPushButton:pressed {
                background-color: #9f1239;
            }
        """)
        self.delete_btn.clicked.connect(self.delete_selected_bill)

        self.clear_all_btn = QPushButton("ล้างบิลค้างทั้งหมด")
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff1f2;
                color: #e11d48;
                border: 1px solid #fecdd3;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffe4e6;
            }
            QPushButton:pressed {
                background-color: #fecdd3;
            }
        """)
        self.clear_all_btn.clicked.connect(self.clear_all_pending_bills)

        close_btn = QPushButton("ปิดหน้าต่าง")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
            QPushButton:pressed {
                background-color: #94a3b8;
            }
        """)
        close_btn.clicked.connect(self.accept)

        btn_layout.addWidget(self.sync_now_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.clear_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def load_pending_sales(self):
        try:
            con = sqlite3.connect(self.db_path)
            cur = con.cursor()
            cur.execute("""
                SELECT local_sale_id, doc_number, created_at, total_amount, payment_method, status, sync_error
                FROM sales
                WHERE status IN ('pending', 'failed')
                ORDER BY created_at DESC;
            """)
            rows = cur.fetchall()
            con.close()

            self.table.setRowCount(0)
            for row_idx, r in enumerate(rows):
                self.table.insertRow(row_idx)
                
                doc_no = str(r[1] or r[0][:13])
                dt = str(r[2] or '-')[:19]
                amt = f"฿{float(r[3] or 0):,.2f}"
                pm = "เงินสด" if r[4] == 'cash' else ("โอน/QR" if r[4] == 'transfer' else str(r[4] or '-'))
                st = "รอส่ง" if r[5] == 'pending' else "ส่งไม่ผ่าน"
                
                err_text = ""
                if r[6]:
                    try:
                        err_obj = json.loads(r[6])
                        err_text = err_obj.get('message', r[6]) if isinstance(err_obj, dict) else str(r[6])
                    except Exception:
                        err_text = str(r[6])

                item_doc = QTableWidgetItem(doc_no)
                item_doc.setData(Qt.UserRole, r[0]) # store local_sale_id
                item_doc.setForeground(QColor("#0f172a"))
                f_bold = QFont()
                f_bold.setBold(True)
                item_doc.setFont(f_bold)
                self.table.setItem(row_idx, 0, item_doc)

                item_dt = QTableWidgetItem(dt)
                item_dt.setForeground(QColor("#334155"))
                self.table.setItem(row_idx, 1, item_dt)

                amt_item = QTableWidgetItem(amt)
                amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                amt_item.setForeground(QColor("#0f172a"))
                amt_item.setFont(f_bold)
                self.table.setItem(row_idx, 2, amt_item)

                item_pm = QTableWidgetItem(pm)
                item_pm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_pm.setForeground(QColor("#334155"))
                self.table.setItem(row_idx, 3, item_pm)
                
                st_item = QTableWidgetItem(st)
                st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                st_item.setFont(f_bold)
                if r[5] == 'failed':
                    st_item.setForeground(QColor("#dc2626")) # red
                else:
                    st_item.setForeground(QColor("#d97706")) # amber
                self.table.setItem(row_idx, 4, st_item)
                
                item_err = QTableWidgetItem(err_text if err_text else "-")
                item_err.setForeground(QColor("#64748b" if not err_text else "#dc2626"))
                self.table.setItem(row_idx, 5, item_err)

            count = len(rows)
            if count > 0:
                self.subtitle_lbl.setText(f"พบบิลค้าง Sync จำนวน {count} บิล (ระบบจะพยายามส่งซ้ำอัตโนมัติ)")
            else:
                self.subtitle_lbl.setText("ไม่มีบิลค้างส่ง — บิลทั้งหมดถูกบันทึกขึ้น ERP เรียบร้อยสมบูรณ์แล้ว")
        except Exception as e:
            self.subtitle_lbl.setText(f"เกิดข้อผิดพลาดในการอ่านข้อมูล: {e}")

    def trigger_sync_now(self):
        worker = getattr(self.parent_window, 'sync_worker', None)
        if not worker:
            QMessageBox.warning(self, "แจ้งเตือน", "ระบบ Sync Background ไม่ได้ทำงานอยู่")
            return
        self.sync_now_btn.setEnabled(False)
        self.sync_now_btn.setText("กำลังส่งบิล...")
        worker.force_sync(retry_failed=True)

    def on_manual_sync_finished(self, success, message):
        self.sync_now_btn.setEnabled(True)
        self.sync_now_btn.setText("สั่ง Sync ทันที (Retry Sync)")
        self.load_pending_sales()
        worker = getattr(self.parent_window, 'sync_worker', None)
        if worker and hasattr(self.parent_window, 'update_pending_sync_badge'):
            self.parent_window.update_pending_sync_badge(worker.get_pending_count())
        if success:
            QMessageBox.information(self, "ส่งบิลสำเร็จ", message)
        else:
            QMessageBox.warning(self, "ส่งบิลไม่สำเร็จ", message)

    def delete_selected_bill(self):
        cur_row = self.table.currentRow()
        if cur_row < 0:
            if self.table.rowCount() == 1:
                cur_row = 0
            else:
                QMessageBox.warning(self, "แจ้งเตือน", "กรุณาคลิกเลือกบิลในตารางที่ต้องการลบก่อน")
                return

        item = self.table.item(cur_row, 0)
        if not item:
            return
        sale_id = item.data(Qt.UserRole)
        doc_no = item.text()

        reply = QMessageBox.question(
            self,
            "ยืนยันการลบบิลค้าง",
            f"คุณต้องการลบบิลเลขที่ {doc_no} ออกจากคิวส่งใช่หรือไม่?\n\n(บิลจะถูกปรับสถานะเป็นยกเลิก และไม่ส่งขึ้น ERP)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                import sqlite3
                con = sqlite3.connect(self.db_path)
                cur = con.cursor()
                cur.execute("UPDATE sales SET status = 'cancelled', sync_error = 'ผู้ใช้ยกเลิกบิลค้าง' WHERE local_sale_id = ?", (sale_id,))
                cur.execute("UPDATE outbox SET status = 'cancelled', last_error = 'ผู้ใช้ยกเลิกบิลค้าง' WHERE aggregate_id = ?", (sale_id,))
                con.commit()
                con.close()

                self.load_pending_sales()
                worker = getattr(self.parent_window, 'sync_worker', None)
                if worker and hasattr(self.parent_window, 'update_pending_sync_badge'):
                    self.parent_window.update_pending_sync_badge(worker.get_pending_count())
                QMessageBox.information(self, "สำเร็จ", f"ลบบิล {doc_no} เรียบร้อยแล้ว")
            except Exception as e:
                QMessageBox.critical(self, "เกิดข้อผิดพลาด", f"ไม่สามารถลบบิลได้: {e}")

    def clear_all_pending_bills(self):
        count = self.table.rowCount()
        if count == 0:
            QMessageBox.information(self, "แจ้งเตือน", "ไม่มีบิลค้างส่งในระบบ")
            return

        reply = QMessageBox.question(
            self,
            "ยืนยันการล้างบิลค้างทั้งหมด",
            f"คุณต้องการยกเลิกและลบบิลค้างทั้งหมดจำนวน {count} บิลใช่หรือไม่?\n\n(บิลทั้งหมดจะถูกปรับสถานะเป็นยกเลิก และไม่ส่งขึ้น ERP)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                import sqlite3
                con = sqlite3.connect(self.db_path)
                cur = con.cursor()
                cur.execute("UPDATE sales SET status = 'cancelled', sync_error = 'ผู้ใช้ยกเลิกบิลค้างทั้งหมด' WHERE status IN ('pending', 'failed')")
                cur.execute("UPDATE outbox SET status = 'cancelled', last_error = 'ผู้ใช้ยกเลิกบิลค้างทั้งหมด' WHERE status IN ('pending', 'failed')")
                con.commit()
                con.close()

                self.load_pending_sales()
                worker = getattr(self.parent_window, 'sync_worker', None)
                if worker and hasattr(self.parent_window, 'update_pending_sync_badge'):
                    self.parent_window.update_pending_sync_badge(worker.get_pending_count())
                QMessageBox.information(self, "สำเร็จ", "ล้างบิลค้างทั้งหมดเรียบร้อยแล้ว")
            except Exception as e:
                QMessageBox.critical(self, "เกิดข้อผิดพลาด", f"ไม่สามารถล้างบิลได้: {e}")
