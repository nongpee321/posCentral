import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QStackedWidget, QWidget,
    QScrollArea, QFrame
)

def get_asset_path(filename: str) -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "manual", filename)

class ManualDialog(QDialog):
    """
    Modern Red & White Enterprise User Manual Dialog
    for PopCentral POS Desktop Application.
    """
    def __init__(self, parent=None, initial_step=0):
        super().__init__(parent)
        self.setWindowTitle("คู่มือการใช้งานระบบ PopCentral POS")
        self.resize(920, 640)
        self.setMinimumSize(800, 560)
        self.setStyleSheet("background-color: #f8fafc;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header (Red Enterprise Theme)
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet("background-color: #dc2626; border-bottom: 2px solid #b91c1c;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)

        title_lbl = QLabel("คู่มือการใช้งานระบบ PopCentral POS")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #ffffff;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        sub_lbl = QLabel("ศูนย์รวมวิธีใช้งานและแก้ไขปัญหาเบื้องต้น")
        sub_lbl.setStyleSheet("font-size: 13px; color: #fee2e2;")
        header_layout.addWidget(sub_lbl)

        main_layout.addWidget(header)

        # Body Layout: Sidebar + Content
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar Navigation
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(240)
        self.nav_list.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: none;
                border-right: 1px solid #e2e8f0;
                padding: 10px 0;
            }
            QListWidget::item {
                padding: 14px 18px;
                font-size: 13px;
                font-weight: 600;
                color: #475569;
                border-left: 4px solid transparent;
            }
            QListWidget::item:hover {
                background-color: #fef2f2;
                color: #dc2626;
            }
            QListWidget::item:selected {
                background-color: #fee2e2;
                color: #b91c1c;
                font-weight: 800;
                border-left: 4px solid #dc2626;
            }
        """)

        # Add Steps to Sidebar
        steps = [
            "1. เข้าสู่ระบบ & ลงทะเบียนเครื่อง",
            "2. การเปิดกะขาย (Open Shift)",
            "3. ขายสินค้า & รับชำระเงิน",
            "4. การเปิดลิ้นชัก & ซิงค์ข้อมูล",
            "5. การปิดกะ & สรุปยอด (Z-Report)",
            "6. วิธีแก้ปัญหาที่พบบ่อย (FAQ)"
        ]
        for step in steps:
            self.nav_list.addItem(QListWidgetItem(step))

        body_layout.addWidget(self.nav_list)

        # Content Area (Stacked Widget)
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #f8fafc;")

        self.stack.addWidget(self._create_step1_page())
        self.stack.addWidget(self._create_step2_page())
        self.stack.addWidget(self._create_step3_page())
        self.stack.addWidget(self._create_step4_page())
        self.stack.addWidget(self._create_step5_page())
        self.stack.addWidget(self._create_faq_page())

        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout)

        # Footer with Close Button
        footer = QFrame()
        footer.setFixedHeight(56)
        footer.setStyleSheet("background-color: #ffffff; border-top: 1px solid #e2e8f0;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)

        version_tip = QLabel("เวอร์ชันโปรแกรม: 1.13.0 (Enterprise Edition)")
        version_tip.setStyleSheet("font-size: 12px; color: #94a3b8;")
        footer_layout.addWidget(version_tip)

        footer_layout.addStretch()

        close_btn = QPushButton("เข้าใจแล้ว / ปิดหน้าต่าง")
        close_btn.setFixedSize(140, 36)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(close_btn)

        main_layout.addWidget(footer)

        # Navigation connection
        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav_list.setCurrentRow(initial_step)

    def _create_scrollable_container(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        scroll.setWidget(container)
        return scroll, layout

    def _create_step1_page(self):
        scroll, layout = self._create_scrollable_container()

        title = QLabel("ขั้นตอนที่ 1: การลงทะเบียนเครื่อง และเข้าสู่ระบบ (Login)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title)

        desc = QLabel(
            "เมื่อเปิดโปรแกรมครั้งแรก คุณจะต้องระบุ **Device Token** เพื่อผูกเครื่องกับสาขา "
            "และกรอก **ชื่อผู้ใช้ & รหัสผ่าน** พนักงานแคชเชียร์เพื่อเข้าสู่ระบบ"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #475569; line-height: 1.6;")
        layout.addWidget(desc)

        # Instruction Card
        card = QFrame()
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        step_text = QLabel(
            "<b>วิธีรับ Device Token จากระบบเว็บ ERP:</b><br>"
            "1. เปิดเว็บเบราว์เซอร์ไปที่ระบบ ERP ของร้าน<br>"
            "2. ไปที่เมนู <b>ตั้งค่า (Settings)</b> &gt; เลือก <b>POS Device Token</b><br>"
            "3. เลือกสาขา แล้วกดปุ่ม <b>'สร้าง Token เครื่อง POS'</b><br>"
            "4. คัดลอกรหัส Token (เช่น <code>pos_b1_xxxxxx</code>) นำมาวางในช่อง <b>Device Token</b><br>"
            "5. ระบุ <b>ชื่อผู้ใช้งาน (Username)</b> และ <b>รหัสผ่าน (Password)</b> ของคุณ<br>"
            "6. กดปุ่ม <b>'เข้าสู่ระบบ'</b> เพื่อเริ่มการทำงาน"
        )
        step_text.setWordWrap(True)
        step_text.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        c_layout.addWidget(step_text)
        layout.addWidget(card)

        # Image if available
        img_path = get_asset_path("pos_step1.png")
        if os.path.exists(img_path):
            img_lbl = QLabel()
            pix = QPixmap(img_path).scaledToWidth(580, Qt.SmoothTransformation)
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: white;")
            layout.addWidget(img_lbl)

        layout.addStretch()
        return scroll

    def _create_step2_page(self):
        scroll, layout = self._create_scrollable_container()

        title = QLabel("ขั้นตอนที่ 2: การเปิดกะขายประจำวัน (Open Shift)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title)

        desc = QLabel(
            "ก่อนจะเริ่มขายสินค้า แคชเชียร์จะต้องทำการ <b>เปิดกะ</b> เพื่อบันทึกเงินสดยกมาเริ่มต้นในลิ้นชักเก็บเงิน"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #475569; line-height: 1.6;")
        layout.addWidget(desc)

        card = QFrame()
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        step_text = QLabel(
            "<b>ขั้นตอนการเปิดกะ:</b><br>"
            "1. ที่มุมขวาบน จะมีปุ่มสีส้มเขียนว่า <b>'เปิดกะ'</b><br>"
            "2. กดปุ่มเปิดกะ จะมีหน้าต่างขึ้นมาให้ระบุ <b>เงินทอนเริ่มต้นในลิ้นชัก (Opening Cash)</b> เช่น 1,000 หรือ 2,000 บาท<br>"
            "3. กดยืนยันเปิดกะ สถานะกะจะเปลี่ยนเป็น <b>'เปิดกะแล้ว' (สีเขียว)</b> พร้อมแสดงชื่อแคชเชียร์และเวลาเปิดกะ<br>"
            "4. ตอนนี้คุณสามารถยิงบาร์โค้ดขายสินค้าได้ทันที!"
        )
        step_text.setWordWrap(True)
        step_text.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        c_layout.addWidget(step_text)
        layout.addWidget(card)

        img_path = get_asset_path("pos_step2.png")
        if os.path.exists(img_path):
            img_lbl = QLabel()
            pix = QPixmap(img_path).scaledToWidth(580, Qt.SmoothTransformation)
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: white;")
            layout.addWidget(img_lbl)

        layout.addStretch()
        return scroll

    def _create_step3_page(self):
        scroll, layout = self._create_scrollable_container()

        title = QLabel("ขั้นตอนที่ 3: การขายสินค้าและการชำระเงิน (POS Checkout)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title)

        desc = QLabel(
            "ระบบรองรับทั้งการยิงบาร์โค้ด หรือกดเลือกหมวดหมู่สินค้าหน้าร้าน พร้อมวิธีชำระเงินทั้งเงินสดและ QR พร้อมเพย์"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #475569; line-height: 1.6;")
        layout.addWidget(desc)

        card = QFrame()
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        step_text = QLabel(
            "<b>ขั้นตอนการขาย:</b><br>"
            "• <b>สแกนบาร์โค้ด:</b> ใช้เครื่องสแกนยิงบาร์โค้ดบนแพ็คสินค้า ระบบจะเพิ่มรายการสินค้าเข้าตะกร้าทันที<br>"
            "• <b>เลือกสินค้าจากจอ:</b> คลิกแท็บหมวดหมู่ (หมู, ไก่, ทะเล, ลูกชิ้น ฯลฯ) แล้วกดเลือกสินค้า<br>"
            "• <b>ปรับจำนวน / ลบรายการ:</b> สามารถกดปุ่ม + หรือ - หรือปุ่มลบในตารางรายการสินค้าได้ตลอดเวลา<br>"
            "• <b>ชำระเงินสด (Cash):</b> กดปุ่ม 'เงินสด' หรือเลือกธนบัตรด่วน (100, 500, 1000) ระบบจะคำนวณเงินทอนและดีดลิ้นชักอัตโนมัติ<br>"
            "• <b>ชำระ QR พร้อมเพย์ (PromptPay):</b> กดปุ่ม 'QR พร้อมเพย์' สแกนจ่ายเงินได้ทันที พร้อมพิมพ์ใบเสร็จ"
        )
        step_text.setWordWrap(True)
        step_text.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        c_layout.addWidget(step_text)
        layout.addWidget(card)

        img_path = get_asset_path("pos.png")
        if os.path.exists(img_path):
            img_lbl = QLabel()
            pix = QPixmap(img_path).scaledToWidth(580, Qt.SmoothTransformation)
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: white;")
            layout.addWidget(img_lbl)

        layout.addStretch()
        return scroll

    def _create_step4_page(self):
        scroll, layout = self._create_scrollable_container()

        title = QLabel("ขั้นตอนที่ 4: การเปิดลิ้นชัก และการซิงค์ข้อมูล (Drawer & Sync)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title)

        desc = QLabel(
            "เมื่อต้องการเปิดลิ้นชักเก็บเงินโดยไม่ได้ขาย หรือต้องการบังคับส่งบิลที่ค้างไปยังเซิร์ฟเวอร์ ERP ส่วนกลาง"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #475569; line-height: 1.6;")
        layout.addWidget(desc)

        card = QFrame()
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        step_text = QLabel(
            "<b>ฟังก์ชันพิเศษในเมนู 3 ขีด (Hamburger Menu มุมซ้ายบน):</b><br><br>"
            "1. <b>ดูรายได้วันนี้:</b> ตรวจสอบยอดขายรวม เงินสด เงินโอน และจำนวนบิลที่ขายได้ในรอบวัน<br>"
            "2. <b>ซิงค์ข้อมูล (Sync Data):</b> กดเมื่ออินเทอร์เน็ตเพิ่งกลับมาใช้งานได้ ระบบจะนำส่งบิล Offline ทั้งหมดขึ้นคลาวด์ ERP ทันที<br>"
            "3. <b>เปิดลิ้นชัก (Open Drawer):</b> สั่งเตะลิ้นชักเก็บเงินทันที (ใช้สำหรับแลกเงินทอนหรือจัดเก็บเงินสดย่อย)<br>"
            "4. <b>ตั้งค่าระบบ (Settings):</b> ตรวจสอบและตั้งค่าเครื่องพิมพ์ใบเสร็จความร้อน (Thermal Printer 80mm/58mm)"
        )
        step_text.setWordWrap(True)
        step_text.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        c_layout.addWidget(step_text)
        layout.addWidget(card)

        img_path = get_asset_path("pos_step4.png")
        if os.path.exists(img_path):
            img_lbl = QLabel()
            pix = QPixmap(img_path).scaledToWidth(580, Qt.SmoothTransformation)
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: white;")
            layout.addWidget(img_lbl)

        layout.addStretch()
        return scroll

    def _create_step5_page(self):
        scroll, layout = self._create_scrollable_container()

        title = QLabel("ขั้นตอนที่ 5: การปิดกะ และพิมพ์รายงานสรุปยอด (Z-Report)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title)

        desc = QLabel(
            "เมื่อสิ้นสุดเวลาปฏิบัติงาน หรือเปลี่ยนเวรแคชเชียร์ จะต้องทำการ <b>ปิดกะ</b> เพื่อกระทบยอดเงินสดจริงกับยอดขายในระบบ"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #475569; line-height: 1.6;")
        layout.addWidget(desc)

        card = QFrame()
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        step_text = QLabel(
            "<b>ขั้นตอนการปิดกะ:</b><br>"
            "1. กดปุ่ม <b>'ปิดกะ' (สีแดง)</b> ที่มุมขวาบน<br>"
            "2. นับเงินสดจริงทั้งหมดที่อยู่ในลิ้นชัก (รวมเงินทอนเริ่มต้น)<br>"
            "3. ป้อนจำนวนเงินสดจริงที่นับได้ลงในช่องยอดเงินสด<br>"
            "4. ระบบจะคำนวณ <b>ผลต่างยอดเงิน (เงินขาด / เงินเกิน)</b> ให้ทันที<br>"
            "5. กดยืนยันปิดกะ ระบบจะพิมพ์ <b>ใบสรุปปิดกะ (Z-Report)</b> ออกทางเครื่องพิมพ์ใบเสร็จ และส่งข้อมูลสรุปเข้าสู่ระบบบัญชี ERP ส่วนกลางทันที"
        )
        step_text.setWordWrap(True)
        step_text.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        c_layout.addWidget(step_text)
        layout.addWidget(card)

        img_path = get_asset_path("pos_step5.png")
        if os.path.exists(img_path):
            img_lbl = QLabel()
            pix = QPixmap(img_path).scaledToWidth(580, Qt.SmoothTransformation)
            img_lbl.setPixmap(pix)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: white;")
            layout.addWidget(img_lbl)

        layout.addStretch()
        return scroll

    def _create_faq_page(self):
        scroll, layout = self._create_scrollable_container()

        title = QLabel("คำถามที่พบบ่อย & การแก้ไขปัญหาเบื้องต้น (FAQ)")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1e293b;")
        layout.addWidget(title)

        faq_items = [
            ("อินเทอร์เน็ตหลุด / ออฟไลน์ ยังขายได้ไหม?", 
             "<b>ขายได้ตามปกติ 100%!</b> ระบบมีระบบ Local Database ในตัว สามารถยิงบาร์โค้ด พิมพ์ใบเสร็จ และรับเงินสดได้ตามปกติ เมื่อเน็ตกลับมา ระบบจะซิงค์บิลขึ้นระบบคลาวด์ให้อัตโนมัติ"),
            ("เข้าสู่ระบบแจ้งเตือน 'PIN / รหัสผ่านไม่ถูกต้อง' ทำอย่างไร?",
             "ให้ตรวจสอบว่าคุณได้รับสิทธิ์แคชเชียร์ในสาขานี้แล้วหรือยัง โดยสามารถแจ้ง Admin ตรวจสอบได้ที่หน้าเว็บ ERP เมนูตั้งค่าผู้ใช้งาน"),
            ("ลิ้นชักเก็บเงินไม่เด้งเปิด ทำอย่างไร?",
             "ตรวจสอบสาย RJ11 ที่ต่อจากด้านหลังลิ้นชักเข้ากับเครื่องพิมพ์ใบเสร็จว่าเสียบแน่นหรือไม่ และตรวจสอบว่าเปิดสวิตช์เครื่องพิมพ์ใบเสร็จแล้วหรือยัง"),
            ("ต้องการเปลี่ยนเครื่อง POS ประจำสาขาใหม่ ต้องทำอย่างไร?",
             "ไปที่หน้าเว็บ ERP เมนู 'ตั้งค่า > POS Device Token' กดลบ Token เครื่องเดิมทิ้ง แล้วกดสร้าง Token เครื่องใหม่ จากนั้นนำรหัสใหม่มากรอกในโปรแกรม POS ได้ทันที")
        ]

        for q, a in faq_items:
            card = QFrame()
            card.setStyleSheet("background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px;")
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(6)

            q_lbl = QLabel(f"{q}")
            q_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #dc2626;")
            c_layout.addWidget(q_lbl)

            a_lbl = QLabel(a)
            a_lbl.setWordWrap(True)
            a_lbl.setStyleSheet("font-size: 13px; color: #475569; line-height: 1.5;")
            c_layout.addWidget(a_lbl)

            layout.addWidget(card)

        layout.addStretch()
        return scroll
