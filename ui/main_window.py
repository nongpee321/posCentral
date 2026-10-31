# -*- coding: utf-8 -*-

import sys

import os

import json

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 

                               QHBoxLayout, QPushButton, QLabel, QLineEdit, 

                               QGridLayout, QScrollArea, QFrame, QTableWidget, QHeaderView,

                               QInputDialog, QMessageBox, QTableWidgetItem, QDialog)

from PySide6.QtCore import Qt, QTimer

from PySide6.QtGui import QIcon

import requests



from sync_worker import SyncWorker

from database.models import (

    init_db, Product, Category, PosReceipt, PosReceiptItem, PosShift,

    Sale, SaleItem, Payment, Outbox, SyncLog, ScaleProfile,

    get_pos_data_paths, backup_pos_db, restore_pos_db

)

from services.scale_service import ScaleBarcodeParser

from services.barcode_lookup import lookup_product, matched_unit_factor, normalize_scan_text

from sqlalchemy.orm import Session



class MainWindow(QMainWindow):

    def __init__(self, db_path="pos.db", is_offline_login=False):

        super().__init__()

        self.db_path = db_path

        self.is_offline_login = is_offline_login

        self.has_shown_online_switch_notification = False

        paths = get_pos_data_paths()

        self.app_data_dir = paths['base_dir']

        self.config_file = os.path.join(self.app_data_dir, 'config.json')

        self.config = self.load_config()

        if self.config.pop('cashier_pin', None) is not None:

            self.save_config()

        self.current_shift = None

        self.customer_display = None

        self.discount_amount = 0.0

        self.discount_label = ""

        self._active_cashier_pin = ""

        self.setWindowTitle("PopCentral POS")

        

        # Set Window Icon

        import sys

        from PySide6.QtGui import QIcon

        if getattr(sys, 'frozen', False):

            base_path = os.path.dirname(sys.executable)

        else:

            base_path = os.path.dirname(os.path.dirname(__file__))

        icon_path = os.path.join(base_path, 'assets', 'icon.ico')

        if os.path.exists(icon_path):

            self.setWindowIcon(QIcon(icon_path))

            

        self.setMinimumSize(960, 680)

        self.resize(1024, 768)

        

        self.setStyleSheet("""

            QMainWindow { background-color: #f1f5f9; }

            QToolTip { color: #000000; background-color: #ffffff; border: 1px solid #94a3b8; font-size: 14px; font-weight: bold; padding: 4px; }

            QLabel { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }

            QPushButton { 

                font-family: 'Segoe UI'; font-weight: bold; border-radius: 6px; 

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

            QInputDialog {

                background-color: #ffffff;

            }

            QInputDialog QLabel {

                color: #0f172a;

                font-size: 14px;

                font-weight: 600;

            }

            QInputDialog QLineEdit {

                background-color: #f8fafc;

                color: #0f172a;

                border: 1.5px solid #cbd5e1;

                border-radius: 6px;

                padding: 6px 10px;

                font-size: 14px;

            }

            QInputDialog QPushButton {

                background-color: #2563eb;

                color: #ffffff;

                font-size: 13.5px;

                font-weight: bold;

                border-radius: 6px;

                padding: 6px 18px;

                min-width: 75px;

                min-height: 28px;

                border: 1px solid #1d4ed8;

            }

            QInputDialog QComboBox, QComboBox {

                background-color: #ffffff;

                color: #0f172a;

                border: 1.5px solid #3b82f6;

                border-radius: 6px;

                padding: 6px 12px;

                font-size: 14px;

                font-weight: 600;

                min-height: 32px;

            }

            QInputDialog QComboBox:hover, QComboBox:hover {

                border-color: #2563eb;

            }

            QInputDialog QComboBox::drop-down, QComboBox::drop-down {

                subcontrol-origin: padding;

                subcontrol-position: top right;

                width: 30px;

                border-left: 1px solid #cbd5e1;

                background-color: #f1f5f9;

                border-top-right-radius: 6px;

                border-bottom-right-radius: 6px;

            }

            QInputDialog QComboBox QAbstractItemView, QComboBox QAbstractItemView {

                background-color: #ffffff;

                color: #0f172a;

                border: 1.5px solid #cbd5e1;

                selection-background-color: #2563eb;

                selection-color: #ffffff;

                font-size: 14px;

                padding: 4px;

            }



        """)



        # Main Central Widget

        central_widget = QWidget()

        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        main_layout.setContentsMargins(10, 10, 10, 10)

        main_layout.setSpacing(10)

        

        # 1. Top Bar

        top_bar = self.create_top_bar()

        main_layout.addWidget(top_bar)

        

        # 2. Main Content (Left: Products, Right: Cart)

        content_layout = QHBoxLayout()

        content_layout.setSpacing(10)

        

        # Left Panel (Products)

        left_panel = self.create_products_panel()

        content_layout.addWidget(left_panel, 6) # 60% width

        

        # Right Panel (Cart)

        right_panel = self.create_cart_panel()

        content_layout.addWidget(right_panel, 4) # 40% width

        

        main_layout.addLayout(content_layout)



        # โหลดรายการสินค้าจากฐานข้อมูล SQLite ในเครื่องทันทีตั้งแต่เปิดหน้าต่าง (Offline-Ready)

        self.load_products_from_db()

        

        QTimer.singleShot(500, self.check_config_and_start)

        

    def load_config(self):

        if os.path.exists(self.config_file):

            try:

                with open(self.config_file, 'r') as f:

                    config = json.load(f)

                if not config.get('receipt_paper_size_v110_user_set'):

                    config['receipt_paper_size'] = '80mm'

                return config

            except Exception:

                pass

        return {

            'api_url': 'http://localhost:8000', 

            'pos_token': '',

            'receipt_printer': '',

            'receipt_copies': 1,

            'receipt_paper_size': '80mm',

            'receipt_header': 'PopCentral POS\nบริษัท ป๊อบ เซ็นทรัล จำกัด\n480 ถนนสุคนธสวัสดิ์ เขตลาดพร้าว กรุงเทพฯ 10230\nเลขประจำตัวผู้เสียภาษี 0105566003246',

            'receipt_footer': 'ขอบคุณที่ใช้บริการ'

        }

        

    def save_config(self):

        with open(self.config_file, 'w') as f:

            json.dump(self.config, f)

            

    def check_config_and_start(self):

        if hasattr(self, 'branch_label') and self.config.get('branch_name'):

            b_name = self.config.get('branch_name', '')

            dev_id = self.config.get('device_id', '')

            self.branch_label.setText(f"สาขา: {b_name}")

            self.branch_label.setToolTip(f"สาขา: {b_name}" + (f"\nรหัสเครื่อง: {dev_id}" if dev_id else ""))

            self.branch_label.show()

        if self.config.get('cashier_name'):

            name = self.config.get('cashier_name')

            self.logged_in_cashier = True

            if hasattr(self, 'cashier_btn') and hasattr(self, 'logout_btn'):

                self.cashier_btn.setText(f"แคชเชียร์: {name}")

                self.cashier_btn.setStyleSheet("QPushButton { background-color: #10b981; border: none; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 13px;} QPushButton:hover { background-color: #059669; }")

                self.logout_btn.setText(f"ออกจากระบบ ({name})" if name else "ออกจากระบบ")

                self.logout_btn.setToolTip(f"ออกจากระบบ ({name})" if name else "ออกจากระบบ")

                self.logout_btn.show()

                self.cashier_btn.hide()

        self.start_sync()

        self.check_active_shift()



    def start_sync(self):

        self.sync_worker = SyncWorker(self.db_path, self.config['api_url'], self.config['pos_token'], config=self.config)

        self.sync_worker.sync_started.connect(self.on_sync_started)

        self.sync_worker.sync_finished.connect(self.on_sync_finished)

        self.sync_worker.products_updated.connect(self.load_products_from_db)

        self.sync_worker.pending_count_updated.connect(self.update_pending_sync_badge)

        self.sync_worker.start()

        

    def show_pending_sync_dialog(self):

        """เปิดหน้าต่างตรวจสอบรายละเอียดบิลที่ค้าง Sync"""

        from ui.pending_sync_dialog import PendingSyncDialog

        dialog = PendingSyncDialog(self, db_path=self.db_path)

        dialog.exec()



    def update_pending_sync_badge(self, count):

        if hasattr(self, 'pending_sync_badge'):

            if count > 0:

                self.pending_sync_badge.setText(f"ค้างส่ง: {count} บิล")

                self.pending_sync_badge.show()

            else:

                self.pending_sync_badge.setText("ส่งข้อมูลครบแล้ว")

                self.pending_sync_badge.hide()

        

    def on_sync_started(self):

        self.network_status.setText("กำลังส่งข้อมูล...")

        self.network_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #16a34a; background: #dcfce7; padding: 4px 10px; border-radius: 12px;")



    def on_sync_finished(self, success, message):

        if success:

            was_offline = getattr(self, 'is_offline_login', False) or "Offline" in self.network_status.text()

            self.network_status.setText("ออนไลน์ (Online)")

            self.network_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #16a34a; background: #dcfce7; padding: 4px 10px; border-radius: 12px;")

            self.network_status.setToolTip("เชื่อมต่อปกติ (Online Mode)")



            # เมื่อต่อเน็ตกลับมาติดอัตโนมัติ ให้สลับโหมดเงียบๆ โดยไม่แสดงป๊อปอัพกวนใจแคชเชียร์

            if was_offline:

                self.is_offline_login = False

                self.has_shown_online_switch_notification = True

                self.load_products_from_db()



            if getattr(self, 'manual_sync_requested', False):

                self.manual_sync_requested = False

                # Refresh UI grid to show updated names/prices

                self.load_products_from_db()

                QMessageBox.information(self, "สำเร็จ", "ซิงค์ข้อมูลใหม่เรียบร้อยแล้ว")

        else:

            self.network_status.setText("ออฟไลน์ (Offline)")

            self.network_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #ca8a04; background: #fef08a; padding: 4px 10px; border-radius: 12px;")

            self.network_status.setToolTip(str(message))

            self.has_shown_online_switch_notification = False

            if getattr(self, 'manual_sync_requested', False):

                self.manual_sync_requested = False

                QMessageBox.warning(self, "ผิดพลาด", f"ไม่สามารถซิงค์ข้อมูลได้:\n{message}")

    def reload_categories_ui(self):

        """โหลดและสร้างปุ่มหมวดหมู่ (ทำครั้งเดียว ไม่ลบสร้างซ้ำตอนกดเลือกหมวดหมู่)"""

        session = init_db(f'sqlite:///{self.db_path}')

        try:

            cats = session.query(Category).order_by(Category.id).all()

        finally:

            session.close()



        # Clear existing category buttons safely

        while self.cat_layout.count():

            item = self.cat_layout.takeAt(0)

            w = item.widget()

            if w:

                w.hide()

                w.setParent(None)

                w.deleteLater()



        self.cat_buttons = {}



        all_btn = QPushButton("ทั้งหมด")

        all_btn.setToolTip("ทั้งหมด")

        all_btn.setFixedSize(100, 40)

        all_btn.clicked.connect(lambda: self.on_category_selected(None))

        self.cat_layout.addWidget(all_btn)

        self.cat_buttons[None] = all_btn



        for cat in cats:

            btn = QPushButton(cat.name_th)

            btn.setFixedSize(100, 40)

            btn.setToolTip(cat.name_th)

            btn.clicked.connect(lambda checked=False, c=cat.id: self.on_category_selected(c))

            self.cat_layout.addWidget(btn)

            self.cat_buttons[cat.id] = btn



        self.cat_layout.addStretch()



    def on_category_selected(self, cat_id=None):

        """เลือกหมวดหมู่: อัปเดตสีปุ่มหมวดหมู่โดยไม่ทำลาย Widget และเรนเดอร์สินค้าเฉพาะหมวดหมู่นั้น"""

        self.current_cat_id = cat_id



        # Update category buttons styling smoothly

        if hasattr(self, 'cat_buttons'):

            for cid, btn in self.cat_buttons.items():

                if cid == cat_id:

                    btn.setStyleSheet("QPushButton { background-color: #0284c7; color: white; border-radius: 6px; font-weight: bold; }")

                else:

                    btn.setStyleSheet("QPushButton { background-color: #f1f5f9; color: #333; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: bold; } QPushButton:hover { background-color: #e2e8f0; }")



        self.render_products_grid(cat_id=cat_id, limit=60, offset=0)



    def load_products_from_db(self, cat_id=None):

        """เรียกเมื่อเริ่มต้นระบบ หรือเมื่อ Sync ข้อมูลสินค้าเสร็จสิ้น"""

        if not hasattr(self, 'cat_buttons') or not self.cat_buttons:

            self.reload_categories_ui()



        target_cat = cat_id if cat_id is not None else getattr(self, 'current_cat_id', None)

        self.on_category_selected(target_cat)



    def render_products_grid(self, cat_id=None, limit=60, offset=0):

        """เรนเดอร์รายการสินค้าลงในตารางแบบจำกัดจำนวน (Page-based) เพื่อความเร็วสูงสุดและไม่ค้าง/ไม่เด้ง"""

        # Clear existing product buttons safely

        while self.prod_grid.count():

            item = self.prod_grid.takeAt(0)

            w = item.widget()

            if w:

                w.hide()

                w.setParent(None)

                w.deleteLater()



        session = init_db(f'sqlite:///{self.db_path}')

        try:

            query = session.query(Product).filter(Product.is_active == True)

            if cat_id is not None:

                query = query.filter(Product.category_id == cat_id)



            total_count = query.count()

            products = query.order_by(Product.name_th).offset(offset).limit(limit).all()



            row, col = 0, 0

            for p in products:

                price_to_show = p.pos_price if p.pos_price is not None and p.pos_price > 0 else p.default_price

                is_promo = bool(getattr(p, 'is_promotion', False))

                if is_promo:

                    btn_text = f"{p.name_th}\n\n฿{price_to_show:.2f} (ลดพิเศษ)"

                    btn_style = """

                        QPushButton { background-color: #fff1f2; color: #e11d48; border: 2px solid #f43f5e; border-radius: 8px; font-size: 13px; font-weight: bold; }

                        QPushButton:hover { border: 2px solid #be123c; background-color: #ffe4e6; }

                    """

                else:

                    btn_text = f"{p.name_th}\n\n฿{price_to_show:.2f}"

                    btn_style = """

                        QPushButton { background-color: white; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-weight: bold; }

                        QPushButton:hover { border: 2px solid #0284c7; background-color: #f0f9ff; }

                    """

                prod_btn = QPushButton(btn_text)

                prod_btn.setFixedSize(130, 130)

                prod_btn.setToolTip(p.name_th)

                prod_btn.setStyleSheet(btn_style)



                p_dict = {

                    'id': p.id,

                    'sku_code': str(p.sku_code),

                    'name_th': str(p.name_th),

                    'default_price': float(p.default_price or 0.0),

                    'pos_price': float(p.pos_price) if p.pos_price is not None else None,

                    'is_promotion': is_promo,

                    'is_scale_item': bool(p.is_scale_item),

                    'stock_qty': float(p.stock_qty) if p.stock_qty is not None else 999999,

                }

                prod_btn.clicked.connect(lambda checked=False, item=p_dict: self.handle_product_click(item))

                self.prod_grid.addWidget(prod_btn, row, col)

                col += 1

                if col > 3:

                    col = 0

                    row += 1



            # ถ้ายังมีสินค้าเหลือ ให้แสดงปุ่มโหลดเพิ่มเติม

            remaining = total_count - (offset + len(products))

            if remaining > 0:

                more_btn = QPushButton(f"ดูสินค้าเพิ่มเติม\n(เหลืออีก {remaining} รายการ)")

                more_btn.setFixedSize(130, 130)

                more_btn.setStyleSheet("""

                    QPushButton { background-color: #f0f9ff; color: #0284c7; border: 2px dashed #0284c7; border-radius: 8px; font-size: 13px; font-weight: bold; }

                    QPushButton:hover { background-color: #e0f2fe; border: 2px solid #0284c7; }

                """)

                more_btn.clicked.connect(lambda: self.load_more_products(cat_id, limit, offset + limit))

                self.prod_grid.addWidget(more_btn, row, col)

        finally:

            session.close()



    def load_more_products(self, cat_id, limit, next_offset):

        """โหลดสินค้าแถวถัดไปมาต่อท้ายโดยไม่ต้องโหลดใหม่ทั้งหมด"""

        # ลบปุ่ม "ดูสินค้าเพิ่มเติม" ตัวเดิมออก

        if self.prod_grid.count() > 0:

            last_item = self.prod_grid.takeAt(self.prod_grid.count() - 1)

            w = last_item.widget()

            if w:

                w.hide()

                w.setParent(None)

                w.deleteLater()



        session = init_db(f'sqlite:///{self.db_path}')

        try:

            query = session.query(Product).filter(Product.is_active == True)

            if cat_id is not None:

                query = query.filter(Product.category_id == cat_id)



            total_count = query.count()

            products = query.order_by(Product.name_th).offset(next_offset).limit(limit).all()



            current_count = self.prod_grid.count()

            row = current_count // 4

            col = current_count % 4



            for p in products:

                price_to_show = p.pos_price if p.pos_price is not None and p.pos_price > 0 else p.default_price

                is_promo = bool(getattr(p, 'is_promotion', False))

                if is_promo:

                    btn_text = f"{p.name_th}\n\n฿{price_to_show:.2f} (ลดพิเศษ)"

                    btn_style = """

                        QPushButton { background-color: #fff1f2; color: #e11d48; border: 2px solid #f43f5e; border-radius: 8px; font-size: 13px; font-weight: bold; }

                        QPushButton:hover { border: 2px solid #be123c; background-color: #ffe4e6; }

                    """

                else:

                    btn_text = f"{p.name_th}\n\n฿{price_to_show:.2f}"

                    btn_style = """

                        QPushButton { background-color: white; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-weight: bold; }

                        QPushButton:hover { border: 2px solid #0284c7; background-color: #f0f9ff; }

                    """

                prod_btn = QPushButton(btn_text)

                prod_btn.setFixedSize(130, 130)

                prod_btn.setToolTip(p.name_th)

                prod_btn.setStyleSheet(btn_style)



                p_dict = {

                    'id': p.id,

                    'sku_code': str(p.sku_code),

                    'name_th': str(p.name_th),

                    'default_price': float(p.default_price or 0.0),

                    'pos_price': float(p.pos_price) if p.pos_price is not None else None,

                    'is_promotion': is_promo,

                    'is_scale_item': bool(p.is_scale_item),

                    'stock_qty': float(p.stock_qty) if p.stock_qty is not None else 999999,

                }

                prod_btn.clicked.connect(lambda checked=False, item=p_dict: self.handle_product_click(item))

                self.prod_grid.addWidget(prod_btn, row, col)

                col += 1

                if col > 3:

                    col = 0

                    row += 1



            remaining = total_count - (next_offset + len(products))

            if remaining > 0:

                more_btn = QPushButton(f"ดูสินค้าเพิ่มเติม\n(เหลืออีก {remaining} รายการ)")

                more_btn.setFixedSize(130, 130)

                more_btn.setStyleSheet("""

                    QPushButton { background-color: #f0f9ff; color: #0284c7; border: 2px dashed #0284c7; border-radius: 8px; font-size: 13px; font-weight: bold; }

                    QPushButton:hover { background-color: #e0f2fe; border: 2px solid #0284c7; }

                """)

                more_btn.clicked.connect(lambda: self.load_more_products(cat_id, limit, next_offset + limit))

                self.prod_grid.addWidget(more_btn, row, col)

        finally:

            session.close()



    def handle_product_click(self, product):

        from ui.scale_weight_dialog import is_scale_product
        is_scale = is_scale_product(product)

        prod_name = product.get('name_th', '') if isinstance(product, dict) else getattr(product, 'name_th', '')

        if is_scale:

            weight, ok = QInputDialog.getDouble(self, "สินค้าน้ำหนัก", f"ระบุน้ำหนักสำหรับ '{prod_name}' (กก.):", 1.0, 0.001, 999.0, 3)

            if ok and weight > 0:

                self.add_to_cart(product, qty=weight, is_scale=True)

        else:

            self.add_to_cart(product, qty=1.0)



    def manual_backup_db(self):

        try:

            dest = backup_pos_db(self.db_path, comment="manual")

            if dest:

                QMessageBox.information(self, "สำรองข้อมูลสำเร็จ", f"สำรองฐานข้อมูลเรียบร้อยแล้วที่:\n{dest}")

            else:

                QMessageBox.warning(self, "แจ้งเตือน", "ไม่พบไฟล์ฐานข้อมูลหรือสำรองข้อมูลไม่สำเร็จ")

        except Exception as e:

            QMessageBox.critical(self, "เกิดข้อผิดพลาด", f"ไม่สามารถสำรองฐานข้อมูลได้:\n{e}")



    def manual_restore_db(self):

        from PySide6.QtWidgets import QFileDialog

        paths = get_pos_data_paths()

        backup_file, _ = QFileDialog.getOpenFileName(

            self,

            "เลือกไฟล์สำรองเพื่อกู้คืนฐานข้อมูล",

            paths['backup_dir'],

            "SQLite Backup (*.db);;All Files (*.*)"

        )

        if not backup_file:

            return

            

        reply = QMessageBox.question(

            self,

            "ยืนยันการกู้คืนฐานข้อมูล",

            f"คำเตือน: การกู้คืนจะนำเข้าข้อมูลจากไฟล์สำรอง:\n{backup_file}\n\nระบบจะทำการสำรองฐานข้อมูลปัจจุบันไว้ก่อนกู้คืน ต้องการดำเนินการต่อหรือไม่?",

            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No

        )

        if reply == QMessageBox.StandardButton.Yes:

            try:

                restore_pos_db(backup_file)

                self.load_products_from_db()

                QMessageBox.information(self, "กู้คืนสำเร็จ", "กู้คืนฐานข้อมูลเรียบร้อยแล้ว กรุณารีสตาร์ทโปรแกรมเพื่อความเสถียรสูงสุด")

            except Exception as e:

                QMessageBox.critical(self, "เกิดข้อผิดพลาด", f"กู้คืนฐานข้อมูลล้มเหลว:\n{e}")



    def handle_barcode_scan(self):

        raw_query = str(self.search_input.text())

        query, digits = normalize_scan_text(raw_query)

        if not query:
            return

        session = None

        try:

            db_path = getattr(self, 'db_path', os.path.join(self.app_data_dir, 'data', 'pos.db'))

            session = init_db(f"sqlite:///{db_path}")

            result = lookup_product(session, raw_query, scale_parser=ScaleBarcodeParser)

            status = result.get('status')

            if status == 'scale':

                product = result['product']
                weight = result['scale'].get('weight') or 1.0
                session.close()
                session = None
                self.add_to_cart(product, qty=weight, is_scale=True)
                self.search_input.clear()
                return

            if status == 'ambiguous':

                products = result.get('products') or []
                labels = [f"{p.name_th}  [{p.barcode or p.sku_code}]  {float(p.pos_price if p.pos_price is not None else (p.default_price or 0)):,.2f}" for p in products]
                choice, ok = QInputDialog.getItem(self, "พบสินค้าหลายรายการ", f"รหัส '{result.get('code')}' ตรงกับสินค้าหลายรายการ กรุณาเลือก:", labels, 0, False)
                if not ok:
                    self.search_input.selectAll()
                    return
                product = products[labels.index(choice)]
                status = 'found'
                result['product'] = product

            if status == 'found':

                product = result['product']
                unit_factor = matched_unit_factor(session, product.id, raw_query)
                session.close()
                session = None
                self._add_scanned_product(product, unit_factor)
                return

            session.close()
            session = None

            # Not in the local replica: ask the ERP directly (same search the web uses),
            # e.g. a product or barcode created after the last product sync.
            online_product = self._lookup_product_online(digits or query)

            if online_product is not None:

                self._add_scanned_product(online_product, 1.0)
                return

            shown = digits if digits and digits != query else query
            note = f"\n(แปลงจากแป้นพิมพ์ภาษาไทยเป็น: {digits})" if digits and digits != query else ""
            QMessageBox.warning(self, "ไม่พบสินค้า", f"ไม่พบสินค้าในระบบ: '{shown}'{note}\n\nหากยิงบาร์โค้ดแล้วตัวเลขไม่ครบ ให้ตรวจว่าแป้นพิมพ์เป็นภาษาอังกฤษ (EN) และลองยิงใหม่อีกครั้ง")
            self.search_input.selectAll()

        except Exception:

            import traceback

            QMessageBox.critical(self, "Error", f"Error scanning barcode:\n{traceback.format_exc()}")

        finally:

            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass



    def _add_scanned_product(self, product, unit_factor=1.0):

        from ui.scale_weight_dialog import is_scale_product

        if is_scale_product(product):

            name = product.get('name_th') if isinstance(product, dict) else product.name_th
            weight, ok = QInputDialog.getDouble(self, "สินค้าน้ำหนัก", f"ระบุน้ำหนักสำหรับ '{name}' (กก.):", 1.0, 0.001, 999.0, 3)

            if ok and weight > 0:
                self.add_to_cart(product, qty=weight, is_scale=True)
                self.search_input.clear()

            return

        try:
            qty = float(unit_factor or 1.0)
        except (TypeError, ValueError):
            qty = 1.0

        self.add_to_cart(product, qty=qty if qty > 0 else 1.0)
        self.search_input.clear()



    def _lookup_product_online(self, code):

        """Exact lookup on the ERP when the code is missing from the local replica.

        Caches the product and all of its barcodes locally so the next scan works offline."""

        api_url = (self.config.get('api_url') or '').rstrip('/')
        pos_token = self.config.get('pos_token') or ''
        code = str(code or '').strip()

        if not api_url or not pos_token or not code:
            return None

        headers = {'Authorization': f'Bearer {pos_token}', 'Accept': 'application/json'}
        branch_id = self.config.get('branch_id') or ''
        attempts = [
            {'q': code, 'exact': 1, 'lookup': 'mixed'},
        ]
        stripped = code.lstrip('0')
        if code.isdigit() and len(stripped) >= 6:
            attempts.append({'q': stripped, 'exact': 0})

        for params in attempts:

            if branch_id:
                params['branch_id'] = branch_id

            try:
                res = requests.get(f"{api_url}/api/pos/products", params=params, headers=headers, timeout=4)
            except Exception:
                return None

            if res.status_code != 200:
                continue

            try:
                data = res.json()
            except Exception:
                continue

            if isinstance(data, dict):
                data = data.get('data') or data.get('products') or []

            rows = [row for row in (data or []) if isinstance(row, dict) and row.get('id')]

            if params.get('exact'):
                matches = rows
            else:
                # partial ERP search: accept only one product whose code really contains the digits
                matches = []
                for row in rows:
                    codes = [str(row.get('sku_code') or '')] + [str((b or {}).get('barcode') or '') for b in (row.get('barcodes') or [])]
                    if any(stripped and stripped in c for c in codes):
                        matches.append(row)

            if len(matches) == 1:
                return self._cache_online_product(matches[0])

        return None



    def _cache_online_product(self, row):

        from database.models import ProductBarcode

        session = None

        try:

            session = init_db(f"sqlite:///{self.db_path}")
            pid = int(row['id'])
            codes = []

            for bc in (row.get('barcodes') or []):
                code = str((bc or {}).get('barcode') or '').strip()
                if code and code not in codes:
                    codes.append(code)

            name_th = str(row.get('name_th') or '')
            sku = str(row.get('sku_code') or (codes[0] if codes else pid))

            prod = session.query(Product).filter_by(id=pid).first() or Product(id=pid)
            prod.sku_code = sku
            prod.name_th = name_th
            prod.default_price = float(row.get('default_price') or 0.0)
            prod.pos_price = float(row.get('pos_price') if row.get('pos_price') is not None else (row.get('default_price') or 0.0))
            prod.category_id = row.get('product_category_id')
            prod.image_url = row.get('image_url')
            prod.is_active = bool(row.get('is_active', True))
            prod.barcode = codes[0] if codes else sku
            prod.is_scale_item = bool(row.get('is_scale') or row.get('is_scale_item') or ('ชั่ง' in name_th) or ('(กก' in name_th))

            # another local row may already own this sku_code (stale replica) -> drop it
            clash = session.query(Product).filter(Product.sku_code == sku, Product.id != pid).first()
            if clash is not None:
                session.delete(clash)
                session.flush()

            session.merge(prod)
            session.query(ProductBarcode).filter(ProductBarcode.product_id == pid).delete(synchronize_session=False)

            for code in codes:
                session.add(ProductBarcode(product_id=pid, barcode=code, barcode_norm=(code.lstrip('0') or '0')))

            session.commit()

            cached = session.query(Product).filter_by(id=pid).first()
            if cached is None:
                return None

            return {
                'id': cached.id,
                'sku_code': cached.sku_code,
                'name_th': cached.name_th,
                'default_price': cached.default_price,
                'pos_price': cached.pos_price,
                'is_scale_item': cached.is_scale_item,
                'barcode': cached.barcode,
            }

        except Exception:

            if session is not None:
                session.rollback()

            # still sell it even if caching fails
            return {
                'id': row.get('id'),
                'sku_code': row.get('sku_code'),
                'name_th': row.get('name_th'),
                'default_price': row.get('default_price'),
                'pos_price': row.get('pos_price'),
                'is_scale_item': bool(row.get('is_scale')),
            }

        finally:

            if session is not None:
                session.close()



    def add_quick_product(self, barcode):

        if not self.current_shift:

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเปิดกะก่อนเริ่มการขาย")

            return



        name, ok1 = QInputDialog.getText(self, "เพิ่มสินค้าใหม่ด่วน", "ชื่อสินค้า:")

        if not ok1 or not name.strip(): return

        

        price, ok2 = QInputDialog.getDouble(self, "เพิ่มสินค้าใหม่ด่วน", "ราคาขาย:", 0, 0, 99999, 2)

        if not ok2: return

        

        try:

            db_path = getattr(self, 'db_path', self.db_path)

            session = init_db(f"sqlite:///{db_path}")

            

            # Create a quick local product

            import random

            new_prod = Product(

                id=-random.randint(1000000, 9999999),

                sku_code=barcode,

                name_th=name.strip(),

                default_price=price,

                pos_price=price,

                is_active=True

            )

            session.add(new_prod)

            session.commit()

            

            # Add to cart immediately

            self.add_to_cart(new_prod)

            self.search_input.clear()

            

            # Refresh products view if "All" is selected

            self.load_products_from_db()

            

            session.close()

            QMessageBox.information(self, "สำเร็จ", f"เพิ่มสินค้า {name.strip()} แล้ว (สินค้าจะเซฟไว้ขายในเครื่องนี้)")

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error adding product:\n{traceback.format_exc()}")



    def add_to_cart(self, product, qty=1.0, is_scale=False):

        if not self.current_shift:

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเปิดกะก่อนเริ่มการขาย")

            return

            

        session = init_db(f'sqlite:///{self.db_path}')

        db_product = session.query(Product).filter_by(id=product.get('id') if isinstance(product, dict) else getattr(product, 'id')).first()

        stock_qty = db_product.stock_qty if db_product and db_product.stock_qty is not None else 999999

        session.close()



        prod_id = product.get('id') if isinstance(product, dict) else getattr(product, 'id')

        try:

            prod_id = int(prod_id)

        except (TypeError, ValueError):

            prod_id = str(prod_id)

        prod_name = product.get('name_th') if isinstance(product, dict) else getattr(product, 'name_th')

        # Use pos_price (promotion/special price) if available, otherwise default_price

        if isinstance(product, dict):

            prod_price = float(product.get('pos_price') if product.get('pos_price') is not None else (product.get('default_price') or 0.0))

        else:

            prod_price = float(getattr(product, 'pos_price') if getattr(product, 'pos_price', None) is not None else (getattr(product, 'default_price', 0.0) or 0.0))



        try:

            # If not scale item, check if product already in cart and increment

            if not is_scale:

                matching_rows = []

                for row in range(self.cart_table.rowCount()):

                    item = self.cart_table.item(row, 0)

                    if not item: continue

                    row_product_id = item.data(Qt.UserRole)

                    try:

                        row_product_id = int(row_product_id)

                    except (TypeError, ValueError):

                        row_product_id = str(row_product_id)

                    row_price = self.cart_table.item(row, 2)

                    if row_product_id == prod_id and row_price and round(float(row_price.text()) - prod_price, 2) == 0:

                        matching_rows.append(row)



                if matching_rows:

                    keep_row = matching_rows[0]

                    current_cart_qty = sum(

                        float(self.cart_table.item(row, 1).text())

                        for row in matching_rows

                        if self.cart_table.item(row, 1)

                    )

                    if current_cart_qty + qty > stock_qty:

                        QMessageBox.warning(self, "แจ้งเตือน", f"สต็อกไม่พอ (เหลือ {stock_qty:g} ชิ้น)")

                        return



                    new_qty = current_cart_qty + qty

                    self.cart_table.item(keep_row, 1).setText(f"{new_qty:g}")

                    self.cart_table.item(keep_row, 3).setText(f"{prod_price * new_qty:.2f}")

                    for duplicate_row in reversed(matching_rows[1:]):

                        self.cart_table.removeRow(duplicate_row)

                    self.update_cart_total()

                    return

            

            if stock_qty <= 0:

                QMessageBox.warning(self, "แจ้งเตือน", f"สินค้าหมดสต็อก (เหลือ {stock_qty:g} ชิ้น)")

                return

            if stock_qty < 20:

                QMessageBox.warning(self, "แจ้งเตือน", f"สินค้าเหลือน้อย (เหลือ {stock_qty:g} ชิ้น)")

                

            row = self.cart_table.rowCount()

            self.cart_table.insertRow(row)

            

            name_str = str(prod_name) if prod_name else ""

            if is_scale:

                name_str = f"{name_str} [ชั่งน้ำหนัก]"

            name_item = QTableWidgetItem(name_str)

            name_item.setToolTip(name_str)

            name_item.setData(Qt.UserRole, prod_id)

            

            qty_item = QTableWidgetItem(f"{qty:g}")

            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            

            price_item = QTableWidgetItem(f"{prod_price:.2f}")

            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            

            total_item = QTableWidgetItem(f"{prod_price * qty:.2f}")

            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            

            self.cart_table.setItem(row, 0, name_item)

            self.cart_table.setItem(row, 1, qty_item)

            self.cart_table.setItem(row, 2, price_item)

            self.cart_table.setItem(row, 3, total_item)

            

            manage_widget = QWidget()

            manage_layout = QHBoxLayout(manage_widget)

            manage_layout.setContentsMargins(0, 0, 0, 0)

            manage_layout.setSpacing(4)

            

            edit_btn = QPushButton("แก้ไข")

            edit_btn.setStyleSheet("background-color: #f59e0b; color: white; border-radius: 4px; padding: 4px 8px;")

            edit_btn.clicked.connect(self.edit_cart_item)

            

            del_btn = QPushButton("ลบ")

            del_btn.setStyleSheet("background-color: #ef4444; color: white; border-radius: 4px; padding: 4px 8px;")

            del_btn.clicked.connect(self.edit_cart_item)

            

            manage_layout.addWidget(edit_btn)

            manage_layout.addWidget(del_btn)

            

            self.cart_table.setCellWidget(row, 4, manage_widget)

            

            self.update_cart_total()

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error adding product:\n{traceback.format_exc()}")

    def edit_cart_item(self):

        try:

            button = self.sender()

            if not button: return

            index = self.cart_table.indexAt(button.parent().pos())

            if not index.isValid(): return

            row = index.row()

            

            if button.text() == "ลบ":

                self.cart_table.removeRow(row)

                self.update_cart_total()

                return

                

            qty_item = self.cart_table.item(row, 1)

            if not qty_item: return

            

            product_id = self.cart_table.item(row, 0).data(Qt.UserRole)

            session = init_db(f'sqlite:///{self.db_path}')

            from database.models import Product

            db_product = session.query(Product).filter_by(id=product_id).first()

            stock_qty = db_product.stock_qty if db_product and db_product.stock_qty is not None else 999999

            session.close()

            

            current_qty = float(qty_item.text())

            new_qty, ok = QInputDialog.getDouble(self, "แก้ไขจำนวน", "จำนวนใหม่:", current_qty, 0.01, 9999, 2)

            

            if ok:

                if new_qty > stock_qty:

                    QMessageBox.warning(self, "แจ้งเตือน", f"สต็อกไม่พอ (เหลือ {stock_qty:g} ชิ้น)")

                    return

                    

                qty_item.setText(str(new_qty))

                price_item = self.cart_table.item(row, 2)

                if price_item:

                    price = float(price_item.text())

                    total_item = self.cart_table.item(row, 3)

                    if total_item:

                        total_item.setText(f"{new_qty * price:.2f}")

                self.update_cart_total()

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error editing cart:\n{traceback.format_exc()}")

    def delete_cart_item(self):

        try:

            button = self.sender()

            if not button: return

            index = self.cart_table.indexAt(button.parent().pos())

            if not index.isValid(): return

            row = index.row()

            self.cart_table.removeRow(row)

            self.update_cart_total()

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error deleting item:\n{traceback.format_exc()}")

        

    def _compute_rounded_totals(self, subtotal):

        from decimal import Decimal

        sub_dec = Decimal(str(round(max(0.0, float(subtotal or 0.0)), 2))).quantize(Decimal('0.01'))

        disc_dec = min(Decimal(str(round(max(0.0, float(getattr(self, 'discount_amount', 0.0))), 2))).quantize(Decimal('0.01')), sub_dec)

        net_total = max(Decimal('0.00'), sub_dec - disc_dec).quantize(Decimal('0.01'))

        return {

            'subtotal': float(sub_dec),

            'manual_discount': float(disc_dec),

            'satang_discount': 0.0,

            'total_discount': float(disc_dec),

            'grand_total': float(net_total),

        }



    def update_cart_total(self):

        try:

            subtotal = 0.0

            for row in range(self.cart_table.rowCount()):

                item = self.cart_table.item(row, 3)

                if item:

                    subtotal += float(item.text().replace(',', ''))

            

            # Reset discount if cart is empty

            if subtotal <= 0:

                self.discount_amount = 0.0

                self.discount_label = ""

            

            totals = self._compute_rounded_totals(subtotal)

            discount = totals['manual_discount']

            grand_total = totals['grand_total']

            

            if hasattr(self, 'subtotal_val'):

                self.subtotal_val.setText(f"฿{subtotal:,.2f}")

            if hasattr(self, 'discount_container'):

                if discount > 0:

                    lbl = f" ({self.discount_label})" if self.discount_label else ""

                    self.discount_title_lbl.setText(f"ส่วนลด{lbl}:")

                    self.discount_val.setText(f"-฿{discount:,.2f}")

                    self.discount_container.show()

                else:

                    self.discount_container.hide()

            elif hasattr(self, 'discount_val'):

                if discount > 0:

                    lbl = f" ({self.discount_label})" if self.discount_label else ""

                    self.discount_title_lbl.setText(f"ส่วนลด{lbl}:")

                    self.discount_val.setText(f"-฿{discount:,.2f}")

                else:

                    self.discount_title_lbl.setText("ส่วนลด:")

                    self.discount_val.setText("-฿0.00")

            

            self.total_val.setText(f"฿{grand_total:,.2f}")

            if hasattr(self, 'customer_display') and self.customer_display and not self.customer_display.isHidden():

                self.customer_display.update_cart(self.cart_table, grand_total, subtotal=subtotal, discount=discount)

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error updating total:\n{traceback.format_exc()}")

        

    def create_top_bar(self):

        frame = QFrame()

        frame.setStyleSheet("background-color: white; border-radius: 8px; padding: 4px 8px;")

        layout = QHBoxLayout(frame)

        layout.setContentsMargins(10, 4, 10, 4)

        layout.setSpacing(6)

        

        logo = QLabel()

        import os, sys

        from PySide6.QtGui import QPixmap

        

        # Determine base path for cx_Freeze or normal execution

        if getattr(sys, 'frozen', False):

            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))

        else:

            base_path = os.path.dirname(os.path.dirname(__file__))

            

        logo_path = os.path.join(base_path, 'assets', 'logo.png')

        if os.path.exists(logo_path):

            pixmap = QPixmap(logo_path).scaledToHeight(36, Qt.SmoothTransformation)

            logo.setPixmap(pixmap)

        else:

            logo.setText("PopCentral POS")

            logo.setStyleSheet("font-size: 18px; font-weight: bold; color: #b91c1c;")

        

        version_label = QLabel("v1.2.21")

        version_label.setStyleSheet("font-size: 13px; color: #64748b; font-weight: bold; background: #e2e8f0; padding: 2px 6px; border-radius: 8px;")

        

        b_name = self.config.get('branch_name', 'กำลังตรวจสอบ...')

        dev_id = self.config.get('device_id', '')

        self.branch_label = QLabel(f"สาขา: {b_name}")

        self.branch_label.setToolTip(f"สาขา: {b_name}" + (f"\nรหัสเครื่อง: {dev_id}" if dev_id else ""))

        self.branch_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e3a8a; background: #dbeafe; padding: 3px 8px; border-radius: 6px; border: 1px solid #93c5fd;")

        self.branch_label.hide()

        

        self.network_status = QLabel("ออนไลน์ (Online)")

        self.network_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #ca8a04; background: #fef08a; padding: 3px 8px; border-radius: 6px;")

        

        # Pending Sync Badge (Clickable to view and retry)

        self.pending_sync_badge = QLabel("ค้างส่ง: 0 บิล")

        self.pending_sync_badge.setStyleSheet("font-size: 12px; font-weight: bold; color: #b91c1c; background: #fee2e2; padding: 3px 8px; border-radius: 6px; border: 1px solid #f87171; cursor: pointer;")

        self.pending_sync_badge.setCursor(Qt.PointingHandCursor)

        self.pending_sync_badge.setToolTip("คลิกเพื่อดูรายละเอียดบิลค้าง Sync และสั่งส่งซ้ำ")

        self.pending_sync_badge.mousePressEvent = lambda e: self.show_pending_sync_dialog()

        self.pending_sync_badge.hide()



        # Action Buttons

        self.fs_btn = QPushButton("เต็มจอ")

        self.fs_btn.setFixedHeight(30)

        self.fs_btn.setToolTip('ย่อจอ / เต็มจอ (F11)')

        self.fs_btn.setStyleSheet("""

            QPushButton { background-color: #f8fafc; border: 1px solid #cbd5e1; color: #0f172a; border-radius: 6px; font-size: 13px; font-weight: bold; padding: 4px 10px; }

            QPushButton:hover { background-color: #e2e8f0; }

        """)

        self.fs_btn.clicked.connect(self.toggle_fullscreen)

        

        self.clock_label = QLabel("00:00:00")

        self.clock_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f172a; background: #e0f2fe; padding: 3px 8px; border-radius: 6px; border: 1px solid #bae6fd;")

        

        # Update clock every second

        self.timer = QTimer(self)

        self.timer.timeout.connect(self.update_clock)

        self.timer.start(1000)

        self.update_clock()

        

        # Cashier Button

        self.logged_in_cashier = bool(self.config.get('cashier_name'))

        initial_cashier_name = self.config.get('cashier_name', '')



        self.cashier_btn = QPushButton(f"แคชเชียร์: {initial_cashier_name}" if initial_cashier_name else "เข้าสู่ระบบ")

        self.cashier_btn.setToolTip('แคชเชียร์')

        self.cashier_btn.setStyleSheet("""

            QPushButton { background-color: #10b981; border: none; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 13px; }

            QPushButton:hover { background-color: #059669; }

        """)

        if initial_cashier_name:

            self.cashier_btn.hide()

        self.cashier_btn.clicked.connect(self.login_cashier)

        

        display_logout = f"ออกจากระบบ ({initial_cashier_name})" if initial_cashier_name else "ออกจากระบบ"

        self.logout_btn = QPushButton(display_logout)

        self.logout_btn.setToolTip(f'ออกจากระบบ ({initial_cashier_name})' if initial_cashier_name else 'ออกจากระบบ')

        self.logout_btn.setStyleSheet("""

            QPushButton { background-color: #ef4444; border: none; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 13px; }

            QPushButton:hover { background-color: #dc2626; }

        """)

        if not initial_cashier_name:

            self.logout_btn.hide()

        self.logout_btn.clicked.connect(self.logout_cashier)

        

        # Shift Button

        self.shift_btn = QPushButton("เปิดกะ")

        self.shift_btn.setToolTip('จัดการกะ (Shift)')

        self.shift_btn.setStyleSheet("""

            QPushButton { background-color: #f59e0b; border: none; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 13px; }

            QPushButton:hover { background-color: #d97706; }

        """)

        self.shift_btn.clicked.connect(self.toggle_shift)

        

        # Hamburger Menu Button

        from PySide6.QtWidgets import QMenu

        from PySide6.QtGui import QAction

        

        menu_btn = QPushButton("เมนู")

        menu_btn.setStyleSheet("""

            QPushButton { background-color: #f1f5f9; border: 1px solid #cbd5e1; color: #475569; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 13px; }

            QPushButton:hover { background-color: #e2e8f0; }

            QPushButton::menu-indicator { image: none; }

        """)

        

        main_menu = QMenu(self)

        main_menu.setStyleSheet("""

            QMenu { background-color: white; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px; }

            QMenu::item { padding: 8px 25px 8px 20px; font-size: 14px; font-weight: bold; color: #334155; }

            QMenu::item:selected { background-color: #f1f5f9; color: #0284c7; border-radius: 4px; }

        """)

        

        action_revenue = main_menu.addAction("ดูรายได้วันนี้")

        action_revenue.triggered.connect(self.show_today_revenue)



        action_shift_report = main_menu.addAction("เช็คบิลกะ / พิมพ์ใบกะ (Z-Report)")

        action_shift_report.triggered.connect(self.show_shift_z_report)

        

        main_menu.addSeparator()



        action_cfd = main_menu.addAction("เปิด/ปิด จอฝั่งลูกค้า (Customer Display)")

        action_cfd.triggered.connect(self.toggle_customer_display)

        

        action_sync = main_menu.addAction("ซิงค์ข้อมูล (Sync Data)")

        action_sync.triggered.connect(self.manual_sync)

        

        main_menu.addSeparator()

        action_drawer = main_menu.addAction("เปิดลิ้นชัก (Open Drawer)")

        action_drawer.triggered.connect(self.manual_open_drawer)

        

        main_menu.addSeparator()

        

        action_backup = main_menu.addAction("สำรองฐานข้อมูล (Backup Database)")

        action_backup.triggered.connect(self.manual_backup_db)

        

        action_restore = main_menu.addAction("กู้คืนฐานข้อมูล (Restore Database)")

        action_restore.triggered.connect(self.manual_restore_db)



        main_menu.addSeparator()

        

        action_settings = main_menu.addAction("ตั้งค่าเชื่อมต่อ ERP (API & Token)")

        action_settings.triggered.connect(self.open_settings)

        

        action_printer = main_menu.addAction("ตั้งค่าเครื่องพิมพ์ใบเสร็จ (Printer Settings)")

        action_printer.triggered.connect(self.open_printer_settings)



        main_menu.addSeparator()

        action_manual = main_menu.addAction("คู่มือการใช้งาน (User Manual)")

        action_manual.triggered.connect(self.open_manual_dialog)

        

        menu_btn.setMenu(main_menu)

        

        layout.addWidget(logo)

        layout.addWidget(version_label)

        layout.addStretch()

        layout.addWidget(self.branch_label)

        layout.addWidget(self.network_status)

        layout.addWidget(self.pending_sync_badge)

        layout.addWidget(self.fs_btn)

        layout.addWidget(self.clock_label)

        layout.addWidget(self.shift_btn)

        layout.addWidget(self.cashier_btn)

        layout.addWidget(self.logout_btn)

        layout.addWidget(menu_btn)

        

        return frame



    def toggle_customer_display(self):

        from ui.customer_display import CustomerDisplayWindow

        if not self.customer_display:

            self.customer_display = CustomerDisplayWindow(self)

        if self.customer_display.isHidden():

            self.customer_display.show()

        else:

            self.customer_display.hide()

            

    def logout_cashier(self):

        if QMessageBox.question(self, "ยืนยันการล็อกเอาท์", "คุณต้องการล็อกเอาท์ออกจากระบบแคชเชียร์ใช่หรือไม่?") == QMessageBox.Yes:

            self.logged_in_cashier = False

            self._active_cashier_pin = ""

            self.config['cashier_name'] = ""

            self.config['cashier_code'] = ""

            self.config.pop('offline_auth', None)

            self.save_config()

            self.cashier_btn.setText("ยังไม่เข้าสู่ระบบ")

            self.cashier_btn.setStyleSheet("QPushButton { background-color: #64748b; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #475569; }")

            self.cashier_btn.show()

            self.logout_btn.hide()

            QMessageBox.information(self, "สำเร็จ", "ล็อกเอาท์เรียบร้อยแล้ว")

        self.check_active_shift()



    def login_cashier(self):

        if not self.config.get('pos_token'):

            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาตั้งค่า API URL และ Token ก่อนเข้าสู่ระบบ")

            return

            

        from ui.login_dialog import CashierLoginDialog

        dialog = CashierLoginDialog(

            self,

            api_url=self.config.get('api_url', ''),

            pos_token=self.config.get('pos_token', ''),

            cached_offline_auth=self.config.get('offline_auth'),

            default_cashier_code=self.config.get('cashier_username') or self.config.get('cashier_code', ''),

        )

        if dialog.exec() == QDialog.Accepted:

            cashier = dialog.selected_cashier

            if cashier:

                name = cashier.get('name', cashier.get('code', 'Unknown'))

                self.config['cashier_name'] = name

                self.config['cashier_code'] = str(cashier.get('code') or '')

                if dialog.offline_auth:

                    self.config['offline_auth'] = dialog.offline_auth

                else:

                    self.config.pop('offline_auth', None)

                self.config.pop('cashier_pin', None)

                self._active_cashier_pin = getattr(dialog, 'entered_pin', '')

                self.save_config()

                self.cashier_btn.setText(f"แคชเชียร์: {name}")

                self.cashier_btn.setStyleSheet("QPushButton { background-color: #10b981; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #059669; }")

                self.logged_in_cashier = True

                

                # Show Logout button

                self.logout_btn.setText(f"ออกจากระบบ ({name})" if name else "ออกจากระบบ"); self.logout_btn.setToolTip(f"ออกจากระบบ ({name})" if name else "ออกจากระบบ")

                self.logout_btn.show()

                self.cashier_btn.hide()

                

                QMessageBox.information(self, "สำเร็จ", f"เข้าสู่ระบบแคชเชียร์: {name} สำเร็จ")

                self.current_shift = None

                self.shift_btn.setText("เปิดกะ")

                self.shift_btn.setStyleSheet("QPushButton { background-color: #f59e0b; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #d97706; }")

                self.check_active_shift(show_resume_dialog=False)



    def toggle_shift(self):

        headers = {

            'Authorization': f"Bearer {self.config.get('pos_token', '')}",

            'Accept': 'application/json'

        }

            

        if getattr(self, 'current_shift', None):

            # Refresh shift details from server before opening close dialog

            try:

                shift_params = {}

                if self.config.get('branch_id'):

                    shift_params['branch_id'] = self.config['branch_id']

                if self.config.get('cashier_id'):

                    shift_params['cashier_id'] = self.config['cashier_id']

                s_res = requests.get(

                    f"{self.config['api_url']}/api/pos/shift",

                    headers=headers,

                    params=shift_params,

                    timeout=5

                )

                if s_res.status_code == 200:

                    latest_shift = s_res.json().get('shift')

                    if latest_shift:

                        self.current_shift.update(latest_shift)

            except Exception:

                pass



            # Close Shift

            from ui.shift_dialog import ShiftCloseDialog

            dialog = ShiftCloseDialog(self, expected_cash=float(self.current_shift.get('expected_cash', 0.0)))

            if dialog.exec() == QDialog.Accepted:

                shift_id = self.current_shift.get('id') or self.current_shift.get('server_id')

                try:

                    res = requests.post(

                        f"{self.config['api_url']}/api/pos/shift/close",

                        headers=headers,

                        json={'shift_id': shift_id, 'counted_cash': dialog.counted_cash},

                        timeout=15

                    )

                    if res.status_code == 200:

                        data = res.json()

                        diff_val = data.get('shift', {}).get('cash_difference', 0.0)

                        diff_str = f"฿ {diff_val:,.2f}"

                        QMessageBox.information(self, "สำเร็จ", f"ปิดกะเรียบร้อย\nยอดขาด/เกิน: {diff_str}")

                        old_shift = dict(self.current_shift or {})

                        self._close_shift_local(dialog.counted_cash, synced=True)

                        from ui.receipt_dialog import ShiftReportDialog

                        shift_payload = old_shift

                        shift_payload.update(data.get('shift', {}))

                        shift_payload['counted_cash'] = dialog.counted_cash

                        shift_payload['cash_difference'] = diff_val

                        shift_payload['status'] = 'closed'

                        ShiftReportDialog(self, shift_payload).exec()

                    else:

                        err_msg = res.json().get('message', res.text) if res.text else 'API Error'

                        reply = QMessageBox.question(self, 'ข้อผิดพลาดจากเซิร์ฟเวอร์', f'เซิร์ฟเวอร์แจ้งว่า: {err_msg}\n\nคุณต้องการบังคับปิดกะในเครื่อง (Force Close) หรือไม่?', QMessageBox.Yes | QMessageBox.No)

                        if reply == QMessageBox.Yes:

                            self._close_shift_local(dialog.counted_cash, synced=True)

                            QMessageBox.information(self, 'สำเร็จ', 'บังคับปิดกะในเครื่องเรียบร้อยแล้ว')

                except requests.exceptions.RequestException:

                    reply = QMessageBox.question(self, "Network Error", "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ ต้องการปิดกะแบบออฟไลน์หรือไม่?", QMessageBox.Yes | QMessageBox.No)

                    if reply == QMessageBox.Yes:

                        self._close_shift_local(dialog.counted_cash, synced=False)

                        QMessageBox.information(self, "สำเร็จ", "ปิดกะแบบออฟไลน์เรียบร้อย\n(ระบบจะส่งข้อมูลขึ้น ERP อัตโนมัติเมื่อออนไลน์)")

        else:

            # Open Shift

            from ui.shift_dialog import ShiftOpenDialog

            dialog = ShiftOpenDialog(self, cashier_name=self.config.get('cashier_name', 'Unknown'), api_url=self.config.get('api_url', ''), pos_token=self.config.get('pos_token', ''), branch_name=self.config.get('branch_name', 'สำนักงานใหญ่'))

            if dialog.exec() == QDialog.Accepted:

                # พยายามเชื่อมต่อและเปิดกะออนไลน์กับเซิร์ฟเวอร์ก่อนเสมอ

                shift_payload = {

                    'opening_cash': dialog.opening_cash,

                    'opening_note': getattr(dialog, 'opening_note', '') or None,

                    'cashier': self.config.get('cashier_name', 'Unknown'),

                }

                if self.config.get('cashier_id'):

                    shift_payload['cashier_id'] = self.config['cashier_id']

                if self.config.get('branch_id'):

                    shift_payload['branch_id'] = self.config['branch_id']



                try:

                    res = requests.post(

                        f"{self.config['api_url']}/api/pos/shift/open",

                        headers=headers,

                        json=shift_payload,

                        timeout=12

                    )

                    if res.status_code == 200:

                        data = res.json()

                        shift_obj = data.get('shift', {}) if isinstance(data.get('shift'), dict) else {}

                        server_id = shift_obj.get('id') or data.get('shift_id', 0)

                        local_id = self._open_shift_local(dialog.opening_cash, server_id=server_id, synced=True)

                        if shift_obj:

                            self.current_shift = dict(shift_obj)

                            self.current_shift['server_id'] = server_id

                            self.current_shift['id'] = server_id

                            if local_id:

                                self.current_shift['local_id'] = local_id

                        msg_text = "เปิดกะเรียบร้อย (ออนไลน์)"

                        if "มีกะเปิดอยู่แล้ว" in str(data.get('message', '')):

                            msg_text = "เชื่อมต่อกะขายเดิมสำเร็จ (ออนไลน์)"

                        QMessageBox.information(self, "สำเร็จ", msg_text)

                    else:

                        err_msg = res.json().get("message", res.text) if res.text else "API Error"

                        if "มีกะเปิดอยู่แล้ว" in str(err_msg):

                            # กะเปิดอยู่แล้ว ดึงข้อมูลกะกลับมาและเปิดใช้งานปุ่มปิดกะทันที
                            self.check_active_shift(show_resume_dialog=False, force_resume=True)

                            QMessageBox.information(self, "แจ้งเตือน", "มีกะเปิดอยู่แล้วบนระบบ ERP เชื่อมต่อกะขายเดิมสำเร็จ\n(คุณสามารถกด 'ปิดกะ' เพื่อปิดกะเดิม หรือขายต่อได้ทันที)")

                        else:

                            reply = QMessageBox.question(self, "ไม่สามารถเปิดกะออนไลน์ได้", f"เซิร์ฟเวอร์แจ้งว่า: {err_msg}\n\nคุณต้องการเปิดกะแบบออฟไลน์เพื่อขายต่อทันทีหรือไม่?", QMessageBox.Yes | QMessageBox.No)

                            if reply == QMessageBox.Yes:

                                self._open_shift_local(dialog.opening_cash, server_id=None, synced=False)

                                QMessageBox.information(self, "สำเร็จ", "เปิดกะแบบออฟไลน์เรียบร้อย (ระบบจะซิงค์ข้อมูลภายหลัง)")

                except requests.exceptions.RequestException:

                    reply = QMessageBox.question(self, "ไม่พบการเชื่อมต่อเครือข่าย", "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ในขณะนี้ ต้องการเปิดกะแบบออฟไลน์เพื่อเริ่มขายทันทีหรือไม่?\n(ระบบจะส่งข้อมูลเปิดกะขึ้นเซิร์ฟเวอร์ให้อัตโนมัติเมื่อออนไลน์)", QMessageBox.Yes | QMessageBox.No)

                    if reply == QMessageBox.Yes:

                        self._open_shift_local(dialog.opening_cash, server_id=None, synced=False)

                        QMessageBox.information(self, "สำเร็จ", "เปิดกะแบบออฟไลน์เรียบร้อย (ระบบจะส่งข้อมูลขึ้นเซิร์ฟเวอร์เมื่อเชื่อมต่อออนไลน์)")

    

    def _close_shift_local(self, counted_cash, synced=False, closing_note=None):
        try:
            from datetime import datetime
            import json
            import time
            session = init_db(f'sqlite:///{self.db_path}')
            shift_dict = dict(self.current_shift or {})
            local_id = shift_dict.get('local_id')
            server_id = shift_dict.get('id') or shift_dict.get('server_id')

            shift = None
            if local_id:
                shift = session.query(PosShift).filter_by(id=local_id).first()
            if not shift and server_id:
                shift = session.query(PosShift).filter_by(server_id=server_id).first()
            if not shift:
                shift = session.query(PosShift).filter_by(status='open').order_by(PosShift.id.desc()).first()
            if not shift:
                shift = session.query(PosShift).order_by(PosShift.id.desc()).first()

            if not shift:
                shift = PosShift(
                    server_id=server_id,
                    branch_id=self.config.get('branch_id'),
                    cashier_id=self.config.get('cashier_id'),
                    cashier_name=self.config.get('cashier_name'),
                    opening_cash=float(shift_dict.get('opening_cash', 0.0) or 0.0),
                    expected_cash=float(shift_dict.get('expected_cash', 0.0) or 0.0),
                    status='open',
                    sync_status='synced' if synced else 'pending'
                )
                session.add(shift)
                session.flush()

            shift.closed_at = datetime.utcnow()
            shift.counted_cash = float(counted_cash)
            shift.status = 'closed'
            shift.sync_status = 'synced' if synced else 'pending'
            if server_id and not shift.server_id:
                shift.server_id = server_id

            # หากเป็นการปิดกะแบบออฟไลน์ ให้เพิ่มงานลงใน Outbox เพื่อให้ SyncWorker นำไปส่ง ERP
            if not synced:
                target_server_id = shift.server_id or server_id
                outbox_payload = {
                    'shift_id': target_server_id,
                    'local_shift_id': shift.id,
                    'counted_cash': float(counted_cash),
                    'closing_note': closing_note or "ปิดกะออฟไลน์ (Auto-sync)"
                }
                agg_id = str(target_server_id or shift.id)
                existing_ob = session.query(Outbox).filter(
                    Outbox.event_type == 'shift_close',
                    Outbox.aggregate_id == agg_id,
                    Outbox.status.in_(['pending', 'failed'])
                ).first()
                if existing_ob:
                    existing_ob.payload_json = json.dumps(outbox_payload)
                    existing_ob.status = 'pending'
                    existing_ob.retry_count = 0
                else:
                    ob_entry = Outbox(
                        event_type='shift_close',
                        aggregate_id=agg_id,
                        idempotency_key=f"shift-close-{agg_id}-{int(time.time())}",
                        payload_json=json.dumps(outbox_payload),
                        status='pending',
                        retry_count=0
                    )
                    session.add(ob_entry)

            session.commit()
            session.close()

            self.current_shift = None
            self.shift_btn.setText("เปิดกะ")
            if hasattr(self, "branch_label"): self.branch_label.hide()
            self.shift_btn.setStyleSheet("QPushButton { background-color: #f59e0b; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #d97706; }")
            if hasattr(self, 'start_sync'):
                self.start_sync()
        except Exception as e:
            print(f"[POS] Error in _close_shift_local: {e}")

    def _open_shift_local(self, opening_cash, server_id=None, synced=False):
        try:
            session = init_db(f'sqlite:///{self.db_path}')
            new_shift = PosShift(
                server_id=server_id,
                branch_id=self.config.get('branch_id'),
                cashier_id=self.config.get('cashier_id'),
                cashier_name=self.config.get('cashier_name'),
                opening_cash=opening_cash,
                expected_cash=opening_cash,
                status='open',
                sync_status='synced' if synced else 'pending'
            )
            session.add(new_shift)
            session.commit()
            local_id = new_shift.id
            session.close()

            self.current_shift = {
                'id': server_id,
                'server_id': server_id,
                'local_id': local_id,
                'expected_cash': opening_cash,
                'opening_cash': opening_cash
            }
            self.shift_btn.setText("ปิดกะ")
            if hasattr(self, "branch_label"): self.branch_label.show()
            self.shift_btn.setStyleSheet("QPushButton { background-color: #3b82f6; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #2563eb; }")
            if hasattr(self, 'start_sync'):
                self.start_sync()
            return local_id
        except Exception as e:
            print(f"[POS] Error in _open_shift_local: {e}")
            return None

    def check_active_shift(self, show_resume_dialog=False, force_resume=False):
        if not self.config.get('pos_token'): return
        try:
            # Fetch Ping for network status
            ping_res = requests.get(
                f"{self.config['api_url']}/api/pos/ping",
                headers={'Authorization': f"Bearer {self.config['pos_token']}", 'Accept': 'application/json'},
                timeout=3
            )
            if ping_res.status_code == 200:
                data = ping_res.json()
                if 'branch_name' in data and data['branch_name']:
                    self.config['branch_name'] = data['branch_name']
                    if hasattr(self, 'branch_label'):
                        b_name = data['branch_name']
                        dev_id = self.config.get('device_id', '')
                        self.branch_label.setText(f"สาขา: {b_name}")
                        self.branch_label.setToolTip(f"สาขา: {b_name}" + (f"\nรหัสเครื่อง: {dev_id}" if dev_id else ""))
                if 'qr_payment' in data and data['qr_payment']:
                    self.config['promptpay_id'] = data['qr_payment'].get('merchant_ref', '')

            # If local shift has no server id (offline shift), link it when online
            if getattr(self, 'current_shift', None) and not self.current_shift.get('id'):
                try:
                    shift_params = {}
                    if self.config.get('branch_id'):
                        shift_params['branch_id'] = self.config['branch_id']
                    if self.config.get('cashier_id'):
                        shift_params['cashier_id'] = self.config['cashier_id']
                    s_res = requests.get(
                        f"{self.config['api_url']}/api/pos/shift",
                        headers={'Authorization': f"Bearer {self.config['pos_token']}", 'Accept': 'application/json'},
                        params=shift_params,
                        timeout=3
                    )
                    if s_res.status_code == 200:
                        s_data = s_res.json().get('shift')
                        if s_data and s_data.get('id'):
                            self.current_shift['id'] = s_data['id']
                            self.current_shift['server_id'] = s_data['id']
                            session = init_db(f"sqlite:///{self.db_path}")
                            loc_id = self.current_shift.get('local_id')
                            if loc_id:
                                loc_shift = session.query(PosShift).filter_by(id=loc_id).first()
                                if loc_shift:
                                    loc_shift.server_id = s_data['id']
                                    loc_shift.sync_status = 'synced'
                                    session.commit()
                            session.close()
                except Exception:
                    pass

            # If force_resume is requested, fetch and attach active ERP shift
            if force_resume or (not getattr(self, 'current_shift', None) and show_resume_dialog):
                try:
                    shift_params = {}
                    if self.config.get('branch_id'):
                        shift_params['branch_id'] = self.config['branch_id']
                    if self.config.get('cashier_id'):
                        shift_params['cashier_id'] = self.config['cashier_id']
                    s_res = requests.get(
                        f"{self.config['api_url']}/api/pos/shift",
                        headers={'Authorization': f"Bearer {self.config['pos_token']}", 'Accept': 'application/json'},
                        params=shift_params,
                        timeout=5
                    )
                    if s_res.status_code == 200:
                        s_data = s_res.json().get('shift')
                        if s_data and s_data.get('id'):
                            server_id = s_data['id']
                            session = init_db(f"sqlite:///{self.db_path}")
                            loc_shift = session.query(PosShift).filter_by(server_id=server_id).first()
                            if not loc_shift:
                                loc_shift = PosShift(
                                    server_id=server_id,
                                    branch_id=self.config.get('branch_id'),
                                    cashier_id=self.config.get('cashier_id'),
                                    cashier_name=self.config.get('cashier_name'),
                                    opening_cash=float(s_data.get('opening_cash', 0.0) or 0.0),
                                    expected_cash=float(s_data.get('expected_cash', 0.0) or 0.0),
                                    status='open',
                                    sync_status='synced'
                                )
                                session.add(loc_shift)
                                session.commit()
                            local_id = loc_shift.id
                            session.close()

                            self.current_shift = dict(s_data)
                            self.current_shift['id'] = server_id
                            self.current_shift['server_id'] = server_id
                            self.current_shift['local_id'] = local_id

                            self.shift_btn.setText("ปิดกะ")
                            if hasattr(self, "branch_label"): self.branch_label.show()
                            self.shift_btn.setStyleSheet("QPushButton { background-color: #3b82f6; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #2563eb; }")
                except Exception:
                    pass

            if not getattr(self, 'current_shift', None):
                self.shift_btn.setText("เปิดกะ")
                self.shift_btn.setStyleSheet("QPushButton { background-color: #f59e0b; border: none; color: white; padding: 5px 10px; border-radius: 6px; font-weight: bold;} QPushButton:hover { background-color: #d97706; }")
        except Exception:
            pass


    def show_today_revenue(self):

        from datetime import datetime

        session = init_db(f"sqlite:///{self.db_path}")

        receipts = session.query(PosReceipt).all()

        today_total = 0.0

        today_count = 0

        now = datetime.now()

        for r in receipts:

            dt = r.created_at

            if isinstance(dt, str):

                try:

                    dt = datetime.strptime(dt.split('.')[0], "%Y-%m-%d %H:%M:%S")

                except Exception:

                    continue

            if getattr(dt, 'day', None) == now.day and getattr(dt, 'month', None) == now.month and getattr(dt, 'year', None) == now.year:

                today_total += r.total_amount

                today_count += 1

                

        session.close()

        QMessageBox.information(self, "สรุปรายได้วันนี้", f"จำนวนบิลวันนี้: {today_count} บิล\nยอดขายรวมวันนี้: ฿ {today_total:,.2f}")



    def show_shift_z_report(self):

        shift = getattr(self, 'current_shift', None)

        if not shift:

            QMessageBox.warning(self, "แจ้งเตือน", "ยังไม่มีกะที่เปิดอยู่ในขณะนี้ กรุณาเปิดกะก่อนเช็คบิลกะ")

            return



        # Fetch latest real-time shift stats from server or local DB

        shift_data = dict(shift)

        api_url = self.config.get('api_url', '').rstrip('/')

        pos_token = self.config.get('pos_token', '')

        

        if api_url and pos_token:

            try:

                shift_params = {}

                if self.config.get('branch_id'):

                    shift_params['branch_id'] = self.config['branch_id']

                if self.config.get('cashier_id'):

                    shift_params['cashier_id'] = self.config['cashier_id']

                res = requests.get(

                    f"{api_url}/api/pos/shift",

                    headers={'Authorization': f"Bearer {pos_token}", 'Accept': 'application/json'},

                    params=shift_params,

                    timeout=5

                )

                if res.status_code == 200:

                    latest = res.json().get('shift')

                    if latest:

                        shift_data.update(latest)

            except Exception:

                pass



        # Fallback calculate from local SQLite sales if needed

        try:

            session = init_db(f"sqlite:///{self.db_path}")

            shift_id = shift_data.get('id') or shift_data.get('server_id')

            if shift_id:

                local_sales = session.query(Sale).filter_by(shift_id=shift_id).all()

                if local_sales and (not shift_data.get('cash_sales') and not shift_data.get('transfer_sales')):

                    c_sales = sum(s.cash_amount or (s.total_amount if s.payment_method == 'cash' else 0) for s in local_sales)

                    t_sales = sum(s.transfer_amount or (s.total_amount if s.payment_method == 'transfer' else 0) for s in local_sales)

                    shift_data['cash_sales'] = c_sales

                    shift_data['transfer_sales'] = t_sales

                    shift_data['receipt_count'] = len(local_sales)

            session.close()

        except Exception:

            pass



        from ui.receipt_dialog import ShiftReportDialog

        dialog = ShiftReportDialog(self, shift_data)

        dialog.exec()





    def manual_sync(self):

        if hasattr(self, 'sync_worker'):

            self.network_status.setText("รีเฟรช...")

            self.network_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #16a34a; background: #dcfce7; padding: 4px 10px; border-radius: 12px;")

            self.manual_sync_requested = True

            self.sync_worker.force_sync()

            QMessageBox.information(self, "แจ้งเตือน", "ระบบกำลังโหลดข้อมูล กรุณารอสักครู่...")

        else:

            QMessageBox.warning(self, "แจ้งเตือน", "ระบบซิงค์ยังไม่พร้อมทำงาน")

    def manual_open_drawer(self):

        printer_name = self.config.get('receipt_printer', '')

        if not printer_name:

            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(

                self, 

                "ยังไม่ได้ตั้งค่าเครื่องพิมพ์", 

                "ยังไม่ได้เลือกเครื่องพิมพ์ใบเสร็จ (Receipt Printer)\nคุณต้องการตั้งค่าเครื่องพิมพ์ตอนนี้หรือไม่?",

                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No

            )

            if reply == QMessageBox.StandardButton.Yes:

                self.open_printer_settings()

            return

        # Prompt PIN before opening cash drawer
        from ui.drawer_pin_dialog import DrawerPinDialog
        pin_dialog = DrawerPinDialog(
            self,
            api_url=self.config.get('api_url', ''),
            pos_token=self.config.get('pos_token', ''),
            cashier_code=self.config.get('cashier_code') or self.config.get('cashier_username', ''),
            offline_auth=self.config.get('offline_auth'),
            active_pin=getattr(self, '_active_cashier_pin', '')
        )
        if pin_dialog.exec() != QDialog.Accepted:
            return

        try:

            from ui.receipt_dialog import open_cash_drawer

            open_cash_drawer(printer_name)

            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "เปิดลิ้นชัก", f"ส่งคำสั่งเปิดลิ้นชักไปยังเครื่องพิมพ์ '{printer_name}' เรียบร้อยแล้ว")

        except Exception as e:

            from PySide6.QtWidgets import QMessageBox

            error_msg = str(e).replace(self.config.get('pos_token', ''), '***TOKEN_HIDDEN***')

            QMessageBox.critical(self, "Error", f"ไม่สามารถเชื่อมต่อเครื่องพิมพ์ได้:\n{error_msg}")



    def open_printer_settings(self):

        from ui.receipt_dialog import ReceiptSettingsDialog

        dlg = ReceiptSettingsDialog(self, config=self.config)

        if dlg.exec():

            self.config = self.load_config()





    def open_settings(self):

        url, ok1 = QInputDialog.getText(self, "ตั้งค่าเชื่อมต่อเซิร์ฟเวอร์", "กรุณาใส่ API URL:", text=self.config.get('api_url', 'http://localhost:8000'))

        if not ok1: return

        url = url.strip()

        if url.startswith('http://') and not ('localhost' in url or '127.0.0.1' in url):

            QMessageBox.critical(self, "Security Error", "Production API ต้องใช้ https:// เท่านั้นเพื่อความปลอดภัยของระบบ!")

            return

            

        token, ok2 = QInputDialog.getText(self, "ตั้งค่า Token", "กรุณาใส่ POS Device Token:", text=self.config.get('pos_token', ''))

        if not ok2: return

        

        self.config['api_url'] = url

        self.config['pos_token'] = token.strip()

        self.save_config()

        

        # Stop existing worker if running

        if hasattr(self, 'sync_worker'):

            self.sync_worker.stop()

            

        # Restart sync

        self.start_sync()

        QMessageBox.information(self, "สำเร็จ", "บันทึกการตั้งค่าเรียบร้อย ระบบกำลังซิงค์ข้อมูลใหม่")



    def create_products_panel(self):

        frame = QFrame()

        frame.setStyleSheet("background-color: white; border-radius: 8px;")

        layout = QVBoxLayout(frame)

        

        # Search Bar

        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText("พิมพ์ชื่อ, บาร์โค้ด หรือสแกนบาร์โค้ดที่นี่...")

        self.search_input.setStyleSheet("padding: 10px; font-size: 16px; border: 1px solid #cbd5e1; border-radius: 6px; color: black;")

        self.search_input.returnPressed.connect(self.handle_barcode_scan)

        # Barcode scanners "type" very fast. If focus is on the cart table or a button,
        # the first digits used to be swallowed by that widget, so the code arrived
        # incomplete. Route every printable key of the main window into the scan box.
        self._scan_redirect_ts = 0.0

        app_instance = QApplication.instance()

        if app_instance is not None:

            app_instance.installEventFilter(self)

        

        search_btn = QPushButton("ค้นหา")

        search_btn.setStyleSheet("background-color: #0284c7; color: white; padding: 10px 20px; font-size: 16px; border-radius: 6px; font-weight: bold;")

        search_btn.clicked.connect(self.handle_barcode_scan)

        

        search_layout.addWidget(self.search_input)

        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        

        # Categories

        cat_scroll = QScrollArea()

        cat_scroll.setWidgetResizable(True)

        cat_scroll.setFixedHeight(75)

        cat_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; } QWidget#catWidget { background: transparent; }")

        cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        

        cat_widget = QWidget()

        cat_widget.setObjectName("catWidget")

        self.cat_layout = QHBoxLayout(cat_widget)

        self.cat_layout.setContentsMargins(0, 0, 0, 0)

        self.cat_layout.setSpacing(10)

        

        cat_scroll.setWidget(cat_widget)

        layout.addWidget(cat_scroll)

        

        # Products Grid

        prod_scroll = QScrollArea()

        prod_scroll.setWidgetResizable(True)

        prod_scroll.setStyleSheet("border: none; background: #f8fafc;")

        

        prod_container = QWidget()

        self.prod_grid = QGridLayout(prod_container)

        self.prod_grid.setSpacing(10)

        self.prod_grid.setContentsMargins(0, 10, 0, 0)

        

        prod_scroll.setWidget(prod_container)

        layout.addWidget(prod_scroll)

        

        return frame



    def create_cart_panel(self):

        frame = QFrame()

        frame.setStyleSheet("background-color: white; border-radius: 8px;")

        layout = QVBoxLayout(frame)

        layout.setContentsMargins(15, 15, 15, 15)

        

        title = QLabel("ตะกร้าสินค้า")

        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")

        layout.addWidget(title)

        

        # Cart Table

        self.cart_table = QTableWidget(0, 5)

        self.cart_table.setHorizontalHeaderLabels(["รายการ", "จำนวน", "ราคา", "รวม", "จัดการ"])

        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self.cart_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.cart_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.cart_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.cart_table.setStyleSheet("""

            QTableWidget {

                border: 1px solid #cbd5e1;

                border-radius: 8px;

                background: white;

                color: #0f172a;

            }

            QTableWidget::item {

                padding: 4px;

            }

            QTableWidget::item:selected {

                background-color: #e2e8f0;

                color: #0f172a;

            }

            QHeaderView::section {

                background-color: #f8fafc;

                padding: 8px;

                border: none;

                border-bottom: 1px solid #cbd5e1;

                font-weight: bold;

                color: #475569;

            }

        """)

        self.cart_table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.cart_table)

        

        # Totals Frame

        total_frame = QFrame()

        total_frame.setStyleSheet("background-color: #f8fafc; border-radius: 8px; border: 1px solid #cbd5e1; padding: 4px;")

        total_layout = QVBoxLayout(total_frame)

        total_layout.setContentsMargins(10, 8, 10, 8)

        total_layout.setSpacing(4)

        

        # Subtotal row

        subtotal_row = QHBoxLayout()

        subtotal_lbl = QLabel("ยอดรวมสินค้า:")

        subtotal_lbl.setStyleSheet("font-size: 14px; color: #64748b; font-weight: bold;")

        self.subtotal_val = QLabel("฿0.00")

        self.subtotal_val.setStyleSheet("font-size: 15px; color: #334155; font-weight: bold;")

        self.subtotal_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        subtotal_row.addWidget(subtotal_lbl)

        subtotal_row.addWidget(self.subtotal_val)

        total_layout.addLayout(subtotal_row)

        

        # Discount row

        self.discount_container = QWidget()

        self.discount_row = QHBoxLayout(self.discount_container)

        self.discount_row.setContentsMargins(0, 0, 0, 0)

        self.discount_title_lbl = QLabel("ส่วนลด:")

        self.discount_title_lbl.setStyleSheet("font-size: 14px; color: #dc2626; font-weight: bold;")

        self.discount_val = QLabel("-฿0.00")

        self.discount_val.setStyleSheet("font-size: 15px; color: #dc2626; font-weight: bold;")

        self.discount_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.discount_row.addWidget(self.discount_title_lbl)

        self.discount_row.addWidget(self.discount_val)

        self.discount_container.hide()

        total_layout.addWidget(self.discount_container)

        

        # Grand total row

        grand_total_row = QHBoxLayout()

        total_label = QLabel("ยอดชำระสุทธิ:")

        total_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")

        self.total_val = QLabel("฿0.00")

        self.total_val.setStyleSheet("font-size: 26px; font-weight: bold; color: #b91c1c;")

        self.total_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        grand_total_row.addWidget(total_label)

        grand_total_row.addWidget(self.total_val)

        total_layout.addLayout(grand_total_row)

        

        layout.addWidget(total_frame)

        

        # Action Toolbar (Discount + Hold + Recall)

        aux_btn_layout = QHBoxLayout()

        aux_btn_layout.setSpacing(6)

        

        self.scale_btn = QPushButton("ใส่ กก.")

        self.scale_btn.setToolTip("สินค้าชั่งน้ำหนัก (เลือกสินค้าและระบุน้ำหนักเป็นกิโลกรัม)")

        self.scale_btn.setStyleSheet("background-color: #0d9488; color: white; border-radius: 6px; padding: 8px 10px; font-size: 13px; font-weight: bold;")

        self.scale_btn.clicked.connect(self.prompt_scale_weight_item)



        self.discount_btn = QPushButton("ใส่ส่วนลด")

        self.discount_btn.setToolTip("กำหนดส่วนลดเป็นบาท หรือเปอร์เซ็นต์")

        self.discount_btn.setStyleSheet("background-color: #f59e0b; color: white; border-radius: 6px; padding: 8px 10px; font-size: 13px; font-weight: bold;")

        self.discount_btn.clicked.connect(self.apply_discount_prompt)

        

        self.hold_btn = QPushButton("พักบิล")

        self.hold_btn.setToolTip("พักบิลปัจจุบันไว้ชั่วคราวเพื่อรับลูกค้าคนถัดไป")

        self.hold_btn.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 6px; padding: 8px 12px; font-size: 13px; font-weight: bold;")

        self.hold_btn.clicked.connect(self.hold_current_bill)

        

        self.recall_btn = QPushButton("บิลพัก")

        self.recall_btn.setToolTip("ดูและดึงบิลที่พักไว้กลับมาขายต่อ")

        self.recall_btn.setStyleSheet("background-color: #6366f1; color: white; border-radius: 6px; padding: 8px 12px; font-size: 13px; font-weight: bold;")

        self.recall_btn.clicked.connect(self.recall_held_bills)

        

        aux_btn_layout.addWidget(self.scale_btn)

        aux_btn_layout.addWidget(self.discount_btn)

        aux_btn_layout.addWidget(self.hold_btn)

        aux_btn_layout.addWidget(self.recall_btn)

        layout.addLayout(aux_btn_layout)

        

        # Payment Buttons

        btn_layout = QHBoxLayout()

        btn_layout.setSpacing(8)

        

        cancel_bill_btn = QPushButton("ยกเลิกบิล")

        cancel_bill_btn.setToolTip('ยกเลิกบิลปัจจุบัน')

        cancel_bill_btn.setStyleSheet("background-color: #ef4444; color: white; border-radius: 8px; padding: 12px; font-size: 20px; font-weight: bold;")

        cancel_bill_btn.clicked.connect(self.cancel_current_bill)

        

        pay_btn = QPushButton("ชำระเงิน")

        pay_btn.setToolTip('ชำระเงิน')

        pay_btn.setStyleSheet("background-color: #10b981; color: white; border-radius: 8px; padding: 12px; font-size: 20px; font-weight: bold;")

        pay_btn.clicked.connect(self.show_payment_dialog)

        

        btn_layout.addWidget(cancel_bill_btn, 1)

        btn_layout.addWidget(pay_btn, 2)

        layout.addLayout(btn_layout)

        

        return frame

        

    def eventFilter(self, obj, event):

        try:

            from PySide6.QtCore import QEvent

            if event.type() != QEvent.KeyPress:
                return super().eventFilter(obj, event)

            search = getattr(self, 'search_input', None)

            if search is None or obj is search or not isinstance(obj, QWidget):
                return super().eventFilter(obj, event)

            # only the main POS window; dialogs (payment, PIN, discount...) keep their keys
            if obj.window() is not self or not self.isActiveWindow() or not search.isVisible():
                return super().eventFilter(obj, event)

            from PySide6.QtWidgets import QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox

            focus = QApplication.focusWidget()

            if focus is search:
                return super().eventFilter(obj, event)

            if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
                return super().eventFilter(obj, event)

            if isinstance(focus, QComboBox) and focus.isEditable():
                return super().eventFilter(obj, event)

            mods = event.modifiers()

            if mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
                return super().eventFilter(obj, event)

            import time

            key = event.key()

            if key in (Qt.Key_Return, Qt.Key_Enter):

                # Enter that ends a scan whose digits were just redirected into the scan box
                if search.text().strip() and (time.monotonic() - getattr(self, '_scan_redirect_ts', 0.0)) < 2.0:
                    search.setFocus()
                    self._scan_redirect_ts = 0.0
                    self.handle_barcode_scan()
                    return True

                return super().eventFilter(obj, event)

            text = event.text()

            if text and text.isprintable():

                search.setFocus()

                if search.hasSelectedText():
                    search.del_()
                else:
                    search.end(False)

                search.insert(text)
                self._scan_redirect_ts = time.monotonic()
                return True

        except Exception:

            pass

        return super().eventFilter(obj, event)



    def keyPressEvent(self, event):

        # If user starts typing, automatically focus search_input

        if event.text() and event.text().isprintable() and not self.search_input.hasFocus():

            self.search_input.setFocus()

            self.search_input.end(False)

            self.search_input.insert(event.text())

            return

        super().keyPressEvent(event)



    def prompt_scale_weight_item(self):

        """ปุ่มฟังก์ชันชั่งน้ำหนัก: รองรับยิงบาร์โค้ด/QR และระบุกิโลกรัมสำหรับสินค้าชั่งน้ำหนักเท่านั้น"""

        if not self.current_shift:
            QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเปิดกะก่อนเริ่มการขาย")
            return

        from ui.scale_weight_dialog import ScaleWeightDialog, is_scale_product

        selected_indexes = self.cart_table.selectionModel().selectedRows() if self.cart_table.selectionModel() else []
        selected_row = selected_indexes[0].row() if selected_indexes else -1

        target_product = None
        initial_weight = 1.000

        if selected_row >= 0:
            name_item = self.cart_table.item(selected_row, 0)
            product_id = name_item.data(Qt.UserRole) if name_item else None
            if product_id:
                session = init_db(f'sqlite:///{self.db_path}')
                db_product = session.query(Product).filter_by(id=product_id).first()
                session.close()
                if db_product:
                    if not is_scale_product(db_product):
                        QMessageBox.warning(
                            self,
                            "แจ้งเตือน",
                            f"สินค้า '{db_product.name_th}' เป็นสินค้าขายตามจำนวนชิ้น ไม่ใช่สินค้าประเภทชั่งน้ำหนัก\n(ฟังก์ชันนี้ใช้ได้เฉพาะสินค้าชั่งน้ำหนักเท่านั้น)"
                        )
                        return
                    target_product = db_product
                    qty_item = self.cart_table.item(selected_row, 1)
                    if qty_item:
                        try:
                            initial_weight = float(qty_item.text())
                        except ValueError:
                            initial_weight = 1.000

        dialog = ScaleWeightDialog(self, db_path=self.db_path, target_product=target_product, initial_weight=initial_weight)

        if dialog.exec() == QDialog.Accepted:

            if dialog.selected_product and dialog.entered_weight > 0:

                if selected_row >= 0 and target_product and target_product.id == dialog.selected_product.id:
                    new_qty = dialog.entered_weight
                    price_item = self.cart_table.item(selected_row, 2)
                    price = float(price_item.text().replace(',', '')) if price_item else (dialog.selected_product.pos_price or dialog.selected_product.default_price or 0.0)
                    self.cart_table.item(selected_row, 1).setText(f"{new_qty:.3f}")
                    if self.cart_table.item(selected_row, 3):
                        self.cart_table.item(selected_row, 3).setText(f"{new_qty * price:.2f}")
                    self.update_cart_total()
                else:
                    self.add_to_cart(dialog.selected_product, qty=dialog.entered_weight, is_scale=True)



    def apply_discount_prompt(self):

        if self.cart_table.rowCount() == 0:

            QMessageBox.warning(self, "แจ้งเตือน", "ไม่มีสินค้าในตะกร้าสำหรับคิดส่วนลด!")

            return

            

        subtotal = 0.0

        for row in range(self.cart_table.rowCount()):

            item = self.cart_table.item(row, 3)

            if item:

                subtotal += float(item.text().replace(',', ''))

                

        from ui.discount_dialog import DiscountDialog

        dlg = DiscountDialog(self, subtotal=subtotal, current_discount=self.discount_amount, current_label=self.discount_label)

        if dlg.exec() == QDialog.Accepted:

            self.discount_amount = dlg.discount_amount

            self.discount_label = dlg.discount_label

            self.update_cart_total()

            if self.discount_amount == 0.0:

                QMessageBox.information(self, "ส่วนลดบิล", "ล้างส่วนลดเรียบร้อยแล้ว")

            else:

                QMessageBox.information(self, "ส่วนลดบิล", f"บันทึกส่วนลด {self.discount_label or f'฿{self.discount_amount:,.2f}'} เรียบร้อยแล้ว")



    def hold_current_bill(self):

        if self.cart_table.rowCount() == 0:

            QMessageBox.warning(self, "แจ้งเตือน", "ไม่มีสินค้าในตะกร้าที่จะพักบิล!")

            return

            

        note, ok = QInputDialog.getText(self, "พักบิลปัจจุบัน (Hold Bill)", "ระบุชื่อลูกค้าหรือหมายเหตุพักบิล (เว้นว่างได้):")

        if not ok:

            return

            

        note = note.strip() or "ลูกค้าพักบิล"

        

        # Build cart items payload

        cart_items = []

        total_amount = 0.0

        for row in range(self.cart_table.rowCount()):

            name_item = self.cart_table.item(row, 0)

            qty_item = self.cart_table.item(row, 1)

            price_item = self.cart_table.item(row, 2)

            total_item = self.cart_table.item(row, 3)

            if not name_item or not qty_item or not price_item:

                continue

            p_id = name_item.data(Qt.UserRole)

            qty = float(qty_item.text())

            price = float(price_item.text().replace(',', ''))

            tot = float(total_item.text().replace(',', '')) if total_item else qty * price

            total_amount += tot

            cart_items.append({

                "id": p_id,

                "name": name_item.text(),     # product display name (for offline recall)

                "name_th": name_item.text(),  # alias for compatibility

                "qty": qty,

                "unit_price": price,

                "total": tot

            })

            

        # 1. พยายามยิงไปเก็บที่ Server ERP ก่อน

        api_url = (self.config.get('api_url') or 'http://localhost:8000').rstrip('/')

        pos_token = self.config.get('pos_token')

        saved_server = False

        

        if pos_token and self.current_shift:

            try:

                payload = {

                    "branch_id": self.config.get('branch_id', 1),

                    "shift_id": self.current_shift.get('server_id') or self.current_shift.get('id') or 1,

                    "cashier_id": self.config.get('cashier_id', 1),

                    "label": note,

                    "total_amount": total_amount,

                    "payload": {

                        "cart": cart_items,

                        "discount_amount": self.discount_amount,

                        "discount_label": self.discount_label

                    }

                }

                headers = {

                    'Authorization': f'Bearer {pos_token}',

                    'Accept': 'application/json'

                }

                res = requests.post(f"{api_url}/api/pos/held-bills", json=payload, headers=headers, timeout=5)

                if res.status_code in (200, 201):

                    saved_server = True

            except Exception as e:

                print("Hold bill server call error:", e)

                

        # 2. เก็บสำรองไว้ใน local config/file ด้วย เพื่อให้ดูได้เสมอ

        held_file = os.path.join(self.app_data_dir, 'local_held_bills.json')

        local_bills = []

        if os.path.exists(held_file):

            try:

                with open(held_file, 'r', encoding='utf-8') as f:

                    local_bills = json.load(f)

            except Exception:

                local_bills = []

                

        from datetime import datetime

        local_bills.append({

            "id": int(datetime.now().timestamp() * 1000),

            "hold_no": f"H{len(local_bills) + 1:03d}",

            "label": note,

            "createdAt": datetime.now().isoformat(),

            "total_amount": total_amount,

            "discount_amount": self.discount_amount,

            "discount_label": self.discount_label,

            "cart": cart_items

        })

        try:

            with open(held_file, 'w', encoding='utf-8') as f:

                json.dump(local_bills, f, ensure_ascii=False)

        except Exception:

            pass

            

        # ล้างตะกร้าเพื่อรับลูกค้าคนต่อไป

        self.discount_amount = 0.0

        self.discount_label = ""

        self._active_cashier_pin = ""

        self.cart_table.setRowCount(0)

        self.update_cart_total()

        QMessageBox.information(self, "พักบิลสำเร็จ", f"พักบิล '{note}' เรียบร้อยแล้ว\nสามารถเปิดการขายให้ลูกค้ารายต่อไปได้ทันที")



    def recall_held_bills(self):

        # 1. รวบรวมบิลพักทั้งจาก Server ERP และ Local

        all_held = []

        api_url = (self.config.get('api_url') or 'http://localhost:8000').rstrip('/')

        pos_token = self.config.get('pos_token')

        

        if pos_token:

            try:

                headers = {'Authorization': f'Bearer {pos_token}', 'Accept': 'application/json'}

                res = requests.get(f"{api_url}/api/pos/held-bills?branch_id={self.config.get('branch_id', 1)}", headers=headers, timeout=4)

                if res.status_code == 200:

                    data = res.json()

                    all_held.extend(data.get('held_bills', []))

            except Exception as e:

                print("Failed to fetch server held bills:", e)

                

        held_file = os.path.join(self.app_data_dir, 'local_held_bills.json')

        if os.path.exists(held_file):

            try:

                with open(held_file, 'r', encoding='utf-8') as f:

                    local_bills = json.load(f)

                    # Filter out duplicates by label/timestamp

                    server_labels = {b.get('label') for b in all_held}

                    for lb in local_bills:

                        if lb.get('label') not in server_labels:

                            all_held.append(lb)

            except Exception:

                pass

                

        if not all_held:

            QMessageBox.information(self, "แจ้งเตือน", "ไม่มีบิลที่พักไว้ในขณะนี้")

            return

            

        from ui.held_bills_dialog import HeldBillsDialog

        dlg = HeldBillsDialog(self, held_bills=all_held)

        if dlg.exec() == QDialog.Accepted and dlg.selected_bill:

            chosen = dlg.selected_bill

            

            # หากในตะกร้าปัจจุบันมีสินค้าอยู่ ให้ยืนยันก่อนทับ

            if self.cart_table.rowCount() > 0:

                reply = QMessageBox.question(self, "ยืนยันการเรียกบิล", "ในตะกร้าปัจจุบันมีสินค้าอยู่ ต้องการแทนที่ด้วยบิลที่เรียกคืนหรือไม่?", QMessageBox.Yes | QMessageBox.No)

                if reply != QMessageBox.Yes:

                    return

                    

            # payload may be a JSON string (older server responses) — parse safely

            raw_payload = chosen.get('payload')

            if isinstance(raw_payload, str):

                try:

                    raw_payload = json.loads(raw_payload)

                except Exception:

                    raw_payload = {}

            cart_data = chosen.get('cart') or (raw_payload or {}).get('cart') or []

            self.cart_table.setRowCount(0)



            # Open local DB once for offline name/price fallback

            _lookup_session = None

            try:

                _lookup_session = init_db(f'sqlite:///{self.db_path}')

            except Exception:

                pass



            for item in cart_data:

                p_id = item.get('id') or item.get('product_id')

                # Explicit None-check: empty-string must not be treated as missing

                name = item.get('name') if item.get('name') not in (None, '') else item.get('name_th')

                price_val = item.get('unit_price') if item.get('unit_price') is not None else item.get('price')

                qty = float(item.get('qty') or 1)

                price = float(price_val) if price_val is not None else 0.0



                # Offline fallback: look up from local SQLite when name/price is absent

                if _lookup_session and p_id and (not name or price == 0.0):

                    try:

                        db_prod = _lookup_session.query(Product).filter_by(id=int(p_id)).first()

                        if db_prod:

                            if not name:

                                name = db_prod.name_th or ''

                            if price == 0.0:

                                price = float(

                                    db_prod.pos_price if db_prod.pos_price is not None

                                    else (db_prod.default_price or 0.0)

                                )

                    except Exception:

                        pass



                name = name or 'สินค้า'

                tot = qty * price

                

                row = self.cart_table.rowCount()

                self.cart_table.insertRow(row)

                

                name_item = QTableWidgetItem(name)

                name_item.setData(Qt.UserRole, p_id)

                qty_item = QTableWidgetItem(f"{qty:g}")

                qty_item.setTextAlignment(Qt.AlignCenter)

                price_item = QTableWidgetItem(f"{price:.2f}")

                price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                tot_item = QTableWidgetItem(f"{tot:.2f}")

                tot_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                

                self.cart_table.setItem(row, 0, name_item)

                self.cart_table.setItem(row, 1, qty_item)

                self.cart_table.setItem(row, 2, price_item)

                self.cart_table.setItem(row, 3, tot_item)

                

                # Manage widget buttons

                manage_widget = QWidget()

                manage_layout = QHBoxLayout(manage_widget)

                manage_layout.setContentsMargins(0, 0, 0, 0)

                manage_layout.setSpacing(4)

                edit_btn = QPushButton("แก้ไข")

                edit_btn.setStyleSheet("background-color: #f59e0b; color: white; border-radius: 4px; padding: 4px 8px;")

                edit_btn.clicked.connect(self.edit_cart_item)

                del_btn = QPushButton("ลบ")

                del_btn.setStyleSheet("background-color: #ef4444; color: white; border-radius: 4px; padding: 4px 8px;")

                del_btn.clicked.connect(self.edit_cart_item)

                manage_layout.addWidget(edit_btn)

                manage_layout.addWidget(del_btn)

                self.cart_table.setCellWidget(row, 4, manage_widget)

                

            # Close the lookup session

            if _lookup_session:

                try:

                    _lookup_session.close()

                except Exception:

                    pass



            # Restore discount (may be at top-level or inside payload)

            _disc_src = chosen if 'discount_amount' in chosen else (raw_payload or {})

            self.discount_amount = float(_disc_src.get('discount_amount') or 0.0)

            self.discount_label = str(_disc_src.get('discount_label') or "")

            self.update_cart_total()

            

            # ลบบิลออกจาก local file

            if os.path.exists(held_file):

                try:

                    with open(held_file, 'r', encoding='utf-8') as f:

                        lbills = json.load(f)

                    lbills = [b for b in lbills if b.get('id') != chosen.get('id') and b.get('label') != chosen.get('label')]

                    with open(held_file, 'w', encoding='utf-8') as f:

                        json.dump(lbills, f, ensure_ascii=False)

                except Exception:

                    pass

                    

            # ยิง resume ไปที่ Server หากมี ID

            server_id = chosen.get('id')

            if server_id and pos_token and not str(server_id).startswith('17'):

                try:

                    requests.post(f"{api_url}/api/pos/held-bills/{server_id}/resume", headers={'Authorization': f'Bearer {pos_token}'}, timeout=3)

                except Exception:

                    pass

                    

            QMessageBox.information(self, "สำเร็จ", f"ดึงบิล '{chosen.get('label', '')}' กลับมายังตะกร้าเรียบร้อยแล้ว")



    def cancel_current_bill(self, auto_reason=None):

        if isinstance(auto_reason, bool):

            auto_reason = None

            

        if self.cart_table.rowCount() == 0:

            QMessageBox.warning(self, "แจ้งเตือน", "ไม่มีสินค้าในตะกร้า!")

            return

            

        if auto_reason is None:

            options = [

                "ลูกค้าเปลี่ยนใจ / ไม่รับสินค้า",

                "พิมพ์รายการผิด / กดผิด",

                "ลูกค้าชำระเงินไม่ผ่าน",

                "สินค้าชำรุด / มีปัญหา",

                "เหตุผลอื่นๆ (โปรดระบุ)"

            ]

            item, ok = QInputDialog.getItem(self, "ยกเลิกบิล (ล้างตะกร้า)", "กรุณาเลือกสาเหตุการยกเลิกบิล:", options, 0, False)

            if not ok or not item:

                return

            

            if item == "เหตุผลอื่นๆ (โปรดระบุ)":

                reason, ok2 = QInputDialog.getText(self, "ระบุเหตุผลอื่นๆ", "กรุณาระบุเหตุผลที่ต้องการยกเลิก:")

                if not ok2 or not reason.strip():

                    return

            else:

                reason = item

        else:

            reason = auto_reason

            

        try:

            total_amount = 0.0

            items_list = []

            for row in range(self.cart_table.rowCount()):

                name = self.cart_table.item(row, 0).text()

                qty = float(self.cart_table.item(row, 1).text())

                price = float(self.cart_table.item(row, 2).text())

                total = float(self.cart_table.item(row, 3).text())

                total_amount += total

                items_list.append({"name": name, "qty": qty, "price": price, "total": total})

                

            db_path = getattr(self, 'db_path', self.db_path)

            session = init_db(f"sqlite:///{db_path}")

            

            from database.models import CancelledBill

            import json

            

            cancel_record = CancelledBill(

                shift_id=self.current_shift.get('id') if self.current_shift else None,

                reason=reason.strip(),

                total_amount=total_amount,

                items_json=json.dumps(items_list)

            )

            session.add(cancel_record)

            session.commit()

            session.close()

            

            self.cart_table.setRowCount(0)

            self.update_cart_total()

            

            if auto_reason is None:

                QMessageBox.information(self, "สำเร็จ", "ยกเลิกบิลและบันทึกเหตุผลเรียบร้อยแล้ว")

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error cancelling bill:\n{traceback.format_exc()}")

    def show_payment_dialog(self):

        try:

            # Force fetch promptpay_id right before opening dialog

            import requests

            try:

                if self.config.get('pos_token'):

                    ping_res = requests.get(

                        f"{self.config['api_url']}/api/pos/ping",

                        headers={'Authorization': f"Bearer {self.config['pos_token']}", 'Accept': 'application/json'},

                        timeout=3

                    )

                    if ping_res.status_code == 200:

                        data = ping_res.json()

                        if 'branch_name' in data and data['branch_name']:

                            self.config['branch_name'] = data['branch_name']

                            if hasattr(self, 'branch_label'):

                                b_name = data['branch_name']

                                dev_id = self.config.get('device_id', '')

                                self.branch_label.setText(f"สาขา: {b_name}")

                                self.branch_label.setToolTip(f"สาขา: {b_name}" + (f"\nรหัสเครื่อง: {dev_id}" if dev_id else ""))

                        if 'qr_payment' in data and data['qr_payment']:

                            self.config['promptpay_id'] = data['qr_payment'].get('merchant_ref', '')

            except Exception as e:

                print("Failed to fetch ping before payment:", e)



            if not self.current_shift:

                QMessageBox.warning(self, "แจ้งเตือน", "กรุณาเปิดกะก่อนทำการชำระเงิน")

                return

                

            if self.cart_table.rowCount() == 0:

                QMessageBox.warning(self, "แจ้งเตือน", "ไม่มีสินค้าในตะกร้า!")

                return

                

            total_amount = 0.0

            total_items = self.cart_table.rowCount()

            total_qty = 0.0

            

            for row in range(total_items):

                qty_item = self.cart_table.item(row, 1)

                total_item = self.cart_table.item(row, 3)

                if qty_item and total_item:

                    qty = float(qty_item.text())

                    total = float(total_item.text().replace(',', ''))

                    total_qty += qty

                    total_amount += total

                

            totals = self._compute_rounded_totals(total_amount)

            discount = totals['total_discount']

            grand_total = totals['grand_total']

            

            from ui.payment_dialog import PaymentDialog
            from ui.help_dialog import HelpDialog
            dialog = PaymentDialog(self, grand_total, total_items, total_qty, discount_amount=discount)
            
            if hasattr(self, 'customer_display') and self.customer_display and not self.customer_display.isHidden():
                self.customer_display.show_payment("QR", override_amount=grand_total, discount=discount)
                
            if dialog.exec() == QDialog.Accepted:
                if hasattr(dialog, 'discount_amount'):
                    self.discount_amount = float(dialog.discount_amount or 0.0)
                if hasattr(self, 'customer_display') and self.customer_display and not self.customer_display.isHidden():
                    self.customer_display.show_payment("SUCCESS")

                    

                self.process_payment(

                    method=dialog.selected_method,

                    received_amount=dialog.received_amount,

                    change_amount=dialog.change_amount,

                    cash_amount=dialog.cash_amount,

                    transfer_amount=dialog.transfer_amount,

                    is_full_tax=dialog.is_full_tax,

                    customer_info=getattr(dialog, 'customer_info', None)

                )

            else:

                if hasattr(self, 'customer_display') and self.customer_display and not self.customer_display.isHidden():

                    self.customer_display.show_payment("NONE")

                

                if getattr(dialog, 'explicit_cancel_bill', False):

                    self.cancel_current_bill("ยกเลิกจากหน้าชำระเงิน")

                elif getattr(dialog, 'clear_cart_requested', False):

                    self.cancel_current_bill("หมดเวลาชำระเงิน")

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error showing payment dialog:\n{traceback.format_exc()}")



    def process_payment(self, method, received_amount, change_amount, cash_amount=0, transfer_amount=0, is_full_tax=False, customer_info=None):

        try:

            import uuid

            from datetime import datetime

            import json

            

            db_path = getattr(self, 'db_path', self.db_path)

            session = init_db(f"sqlite:///{db_path}")

            

            receipt_id = str(uuid.uuid4())

            total_amount = 0.0

            

            method_map = {

                'เงินสด': 'cash',

                'QR': 'transfer',

                'ผสม (Split)': 'mixed',

                'บัตรเครดิต': 'card',

                'เช็ค': 'check'

            }

            

            if method == 'เงินสด':

                cash_amount = received_amount - change_amount

                transfer_amount = 0

            elif method == 'QR':

                transfer_amount = received_amount

                cash_amount = 0

                

            cust_name = customer_info.get('name') if customer_info else None

            cust_tax = customer_info.get('tax_id') if customer_info else None

            cust_addr = customer_info.get('address') if customer_info else None

            

            # Note: We will save total_amount below after loop

            

            items = []

            api_items = []

            for row in range(self.cart_table.rowCount()):

                name_item = self.cart_table.item(row, 0)

                qty_item = self.cart_table.item(row, 1)

                price_item = self.cart_table.item(row, 2)

                

                if not name_item or not qty_item or not price_item:

                    continue

                    

                product_id = name_item.data(Qt.UserRole)

                qty = float(qty_item.text())

                price = float(price_item.text())

                total = qty * price

                total_amount += total

                

                items.append(PosReceiptItem(

                    receipt_id=receipt_id,

                    product_id=product_id,

                    sku_code='OFFLINE',

                    name=name_item.text(),

                    qty=qty,

                    unit_price=price,

                    total_price=total

                ))

                api_items.append({

                    "product_id": product_id,

                    "qty": qty,

                    "unit_price": price

                })

                

            # Resolve valid active branch_id, cashier_id, shift_id

            active_shift = getattr(self, 'current_shift', None) or {}

            cur_branch_id = active_shift.get('branch_id') or self.config.get('branch_id') or 6

            cur_cashier_id = active_shift.get('cashier_id') or self.config.get('cashier_id') or 21

            cur_shift_id = active_shift.get('id') or active_shift.get('server_id')



            try:

                existing_count = session.query(Sale).count()

                branch_num = int(cur_branch_id or 2)

                term_raw = str(self.config.get('device_id', '01'))

                import re

                digits = re.findall(r'\d+', term_raw)

                term_num = int(digits[-1]) if digits else 1

                doc_no = f"{branch_num:04d}{term_num:02d}{254750 + existing_count + 1:06d}"

            except Exception:

                doc_no = '000201' + datetime.now().strftime('%H%M%S')



            # Calculate standard catalog gross sum and ensure standard catalog prices for ERP
            catalog_gross_sum = 0.0
            sync_items = []
            for it in api_items:
                pid = it.get('product_id')
                p_qty = float(it.get('qty') or 0.0)
                p_price = float(it.get('unit_price') or 0.0)
                std_price = p_price
                if pid:
                    db_p = session.query(Product).filter_by(id=pid).first()
                    if db_p:
                        std_price = float(db_p.pos_price or db_p.default_price or p_price)
                catalog_gross_sum += p_qty * std_price
                sync_items.append({
                    "product_id": pid,
                    "qty": p_qty,
                    "unit_price": std_price
                })

            totals = self._compute_rounded_totals(total_amount)
            catalog_reduction = max(0.0, round(catalog_gross_sum - total_amount, 2)) if total_amount > 0 and catalog_gross_sum > total_amount else 0.0
            manual_discount = totals['manual_discount']
            satang_discount = totals['satang_discount']
            discount_applied = round(totals['total_discount'] + catalog_reduction, 2)
            net_total = totals['grand_total']

            idempotency_key = f"offline-receipt-{receipt_id}"

            # Prepare checkout payment fields for ERP validation
            cash_received_payload = received_amount
            change_amount_payload = max(0, change_amount)
            mixed_cash = cash_amount
            mixed_transfer = transfer_amount

            if method_map.get(method) == 'cash':
                cash_received_payload = max(float(received_amount), float(net_total))
                change_amount_payload = max(0.0, float(cash_received_payload) - float(net_total))
            elif method_map.get(method) == 'mixed' and discount_applied > 0 and total_amount > 0:
                cur_mix_sum = float(mixed_cash) + float(mixed_transfer)
                diff = round(float(net_total) - cur_mix_sum, 2)
                if diff != 0:
                    mixed_cash = round(float(mixed_cash) + diff, 2)

            # Create Sale record

            new_sale = Sale(

                local_sale_id=receipt_id,

                server_receipt_id=None,

                device_id=self.config.get('device_id', 'DEV-01'),

                branch_id=cur_branch_id,

                shift_id=cur_shift_id or (active_shift.get('local_id') if active_shift else None),

                cashier_salesman_id=cur_cashier_id,

                doc_number=doc_no,

                total_amount=net_total,

                received_amount=received_amount,

                discount_amount=discount_applied,

                payment_method=method_map.get(method, 'cash'),

                cash_amount=cash_amount,

                transfer_amount=transfer_amount,

                is_full_tax=is_full_tax,

                customer_name=cust_name,

                customer_tax_id=cust_tax,

                customer_address=cust_addr,

                status='pending',

                idempotency_key=idempotency_key,

                synced_at=None

            )

            

            # Create Payment record

            payment_record = Payment(

                sale_id=receipt_id,

                method=method_map.get(method, 'cash'),

                amount=net_total,

                received_amount=received_amount,

                change_amount=max(0.0, change_amount)

            )



            # Create Outbox record for synchronization queue

            outbox_payload = {

                "local_sale_id": receipt_id,

                "branch_id": cur_branch_id,

                "shift_id": cur_shift_id,

                "cashier_id": cur_cashier_id,

                "method": method_map.get(method, 'cash'),

                "payment_confirmed": True,

                "cash_received": cash_received_payload,

                "cash_amount": mixed_cash if method_map.get(method) == 'mixed' else cash_amount,

                "transfer_amount": mixed_transfer if method_map.get(method) == 'mixed' else transfer_amount,

                "change_amount": change_amount_payload,

                "is_full_tax": is_full_tax,

                "customer_name": cust_name,

                "customer_tax_id": cust_tax,

                "customer_address": cust_addr,

                "discount_amount": float(discount_applied),

                "manual_discount_amount": float(discount_applied),

                "is_offline_sync": True,

                "items": sync_items

            }

            if outbox_payload["method"] in ('transfer', 'mixed'):

                outbox_payload["payment_confirmed"] = True

                outbox_payload["transfer_account_last4"] = "0000"

                outbox_payload["payment_ref"] = "0000"

            outbox_record = Outbox(

                event_type='sale_checkout',

                aggregate_id=receipt_id,

                payload_json=json.dumps(outbox_payload),

                idempotency_key=idempotency_key,

                status='pending'

            )



            # Atomic Transaction to save sale, sale_items, payment, and outbox

            session.add(new_sale)

            session.add_all(items)

            session.add(payment_record)

            session.add(outbox_record)

            

            # Extract data before commit expires the instances

            receipt_items_data = [{'name': i.name, 'qty': i.qty, 'price': i.unit_price, 'total': i.total_price} for i in items]

            

            session.commit()

            session.close()



            if getattr(self, 'sync_worker', None):

                self.sync_worker.force_sync()



            # Update pending sync badge

            if hasattr(self, 'sync_worker') and self.sync_worker:

                pending_count = self.sync_worker.get_pending_count()

                self.update_pending_sync_badge(pending_count)

            

            # Reset discount after successful checkout

            saved_discount = discount_applied

            self.discount_amount = 0.0

            self.discount_label = ""

            

            self.cart_table.setRowCount(0)

            self.update_cart_total()

            

            # Show Receipt Dialog

            from datetime import datetime

            cashier_code = (

                self.config.get('cashier_code')

                or (self.config.get('offline_auth') or {}).get('code')

                or self.config.get('cashier_name', '01')

            )

            receipt_data = {

                'doc_number': doc_no,

                'subtotal': round(total_amount, 2),

                'total': net_total,

                'discount_amount': manual_discount,

                'satang_discount': satang_discount,

                'payment_method': method_map.get(method, 'cash'),

                'cash_received': received_amount,

                'item_count': len(receipt_items_data),

                'total_qty': sum(float(item.get('qty', 0) or 0) for item in receipt_items_data),

                'is_full_tax': is_full_tax,

                'customer_name': cust_name,

                'customer_tax_id': cust_tax,

                'customer_address': cust_addr,

                'cashier': cashier_code,

                'cashier_name': self.config.get('cashier_name', 'Unknown'),

                'branch': self.config.get('branch_name', ''),

                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

                'items': receipt_items_data

            }

            from ui.receipt_dialog import ReceiptDialog

            receipt_dialog = ReceiptDialog(self, receipt_data=receipt_data)

            receipt_dialog.exec()

            

        except Exception as e:

            import traceback

            QMessageBox.critical(self, "Error", f"Error saving receipt:\n{traceback.format_exc()}")

        

    def update_clock(self):

        from datetime import datetime

        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))



    

    def show_help(self):

        from ui.manual_dialog import ManualDialog

        dialog = ManualDialog(self)

        dialog.exec()



    def open_manual_dialog(self):

        from ui.manual_dialog import ManualDialog

        dialog = ManualDialog(self)

        dialog.exec()



    def toggle_fullscreen(self):

        if self.isFullScreen():

            self.showNormal()

            self.fs_btn.setText("เต็มจอ")

            self.fs_btn.setToolTip("เต็มจอ (F11)")

        else:

            self.showFullScreen()

            self.fs_btn.setText("ย่อจอ")

            self.fs_btn.setToolTip("ย่อจอ (F11)")



if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = MainWindow()

    window.show()

    sys.exit(app.exec())



    def closeEvent(self, event):

        try:

            if hasattr(self, 'sync_worker') and self.sync_worker and self.sync_worker.isRunning():

                self.sync_worker.is_running = False

                if hasattr(self.sync_worker, '_wake_event'):

                    self.sync_worker._wake_event.set()

                self.sync_worker.quit()

                self.sync_worker.wait(2000)

        except Exception:

            pass

        try:

            if hasattr(self, 'customer_display') and self.customer_display:

                self.customer_display.close()

        except Exception:

            pass

        event.accept()

