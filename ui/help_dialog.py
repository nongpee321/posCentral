import os
import sys
from PySide6.QtWidgets import QFrame, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("คู่มือการใช้งานระบบขายหน้าร้าน (JET POS)")
        self.resize(900, 650)
        self.setStyleSheet("background-color: white;")
        
        self.current_step = 1
        self.total_steps = 5
        
        if getattr(sys, 'frozen', False):
            self.base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            self.base_path = os.path.dirname(os.path.dirname(__file__))
            
        self.image_files = {
            1: 'pos_step1.png',
            2: 'pos_step2.png',
            3: 'pos.png',
            4: 'pos_step4.png',
            5: 'pos_step5.png',
        }
        
        self.setup_ui()
        self.update_view()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QFrame()
        header.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b91c1c, stop:1 #7f1d1d);")
        header.setFixedHeight(50)
        header_layout = QHBoxLayout(header)
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        layout.addWidget(header)
        
        # Image
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("background-color: #f8fafc;")
        layout.addWidget(self.img_label, 1) # stretch=1
        

        # Description
        self.desc_label = QLabel()
        self.desc_label.setStyleSheet("background-color: #fef2f2; border: 2px solid #b91c1c; border-radius: 12px; padding: 15px; font-size: 14px; color: #334155; margin: 10px 15px;")
        self.desc_label.setWordWrap(True)
        self.desc_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.desc_label)

        # Footer
        footer = QFrame()
        footer.setStyleSheet("background-color: #f1f5f9; border-top: 1px solid #cbd5e1;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 10, 15, 10)
        
        self.btn_prev = QPushButton("◀ กลับ")
        self.btn_prev.setFixedSize(120, 40)
        self.btn_prev.setStyleSheet("""
            QPushButton { background-color: white; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 14px; font-weight: bold; color: #475569; }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.btn_prev.clicked.connect(self.prev_step)
        
        self.btn_next = QPushButton("ถัดไป ▶")
        self.btn_next.setFixedSize(120, 40)
        self.btn_next.setStyleSheet("""
            QPushButton { background-color: #3b82f6; border: none; border-radius: 6px; font-size: 14px; font-weight: bold; color: white; }
            QPushButton:hover { background-color: #2563eb; }
        """)
        self.btn_next.clicked.connect(self.next_step)
        
        self.btn_finish = QPushButton("เริ่มใช้งานเลย")
        self.btn_finish.setFixedSize(140, 40)
        self.btn_finish.setStyleSheet("""
            QPushButton { background-color: #10b981; border: none; border-radius: 6px; font-size: 14px; font-weight: bold; color: white; }
            QPushButton:hover { background-color: #059669; }
        """)
        self.btn_finish.clicked.connect(self.accept)
        
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        footer_layout.addWidget(self.btn_prev)
        footer_layout.addItem(spacer)
        footer_layout.addWidget(self.btn_next)
        footer_layout.addWidget(self.btn_finish)
        layout.addWidget(footer)
        
    def update_view(self):

        descriptions = {
            1: """<html><body style='font-family: Arial; font-size: 15px; color: #1e293b;'>
<b style='font-size: 18px; color: #b91c1c;'>1. เปิดกะการขาย (Shift)</b><br>
เมื่อเริ่มงาน ให้กดปุ่ม <b>"ยังไม่เปิดกะ"</b> หรือ <b>"เปิดกะ"</b> ที่แถบเมนูด้านบน<br><br>
<b>ความหมายของตัวเลขในภาพ:</b><br>
<span style='color: #dc2626;'><b>หมายเลข 1:</b></span> ใส่ยอดเงินทอนตั้งต้น (ยอดเงินสดที่มีในลิ้นชักก่อนเริ่มขาย)<br>
<span style='color: #dc2626;'><b>หมายเลข 2:</b></span> ใส่หมายเหตุการเปิดกะ (เช่น ชื่อกะเช้า หรือปล่อยว่างไว้ก็ได้)<br>
<span style='color: #dc2626;'><b>หมายเลข 3:</b></span> กดปุ่ม <b>"เปิดกะ"</b> สีเขียว เพื่อเริ่มต้นรอบการขาย
</body></html>""",

            2: """<html><body style='font-family: Arial; font-size: 15px; color: #1e293b;'>
<b style='font-size: 18px; color: #b91c1c;'>2. เลือกสินค้า / ยิงบาร์โค้ด / ชั่งน้ำหนัก</b><br>
การนำสินค้าเข้าตะกร้าเพื่อเตรียมชำระเงิน<br><br>
<b>ความหมายของตัวเลขในภาพ:</b><br>
<span style='color: #dc2626;'><b>หมายเลข 1:</b></span> ใช้เครื่องสแกน ยิงบาร์โค้ดสินค้าได้เลย (สินค้าจะลงตะกร้าทันที)<br>
<span style='color: #dc2626;'><b>หมายเลข 2:</b></span> หรือคลิกเลือกหมวดหมู่สินค้าที่ต้องการด้านบน<br>
<span style='color: #dc2626;'><b>หมายเลข 3:</b></span> คลิกที่รูปสินค้าเพื่อเพิ่มลงตะกร้าฝั่งซ้าย (ราคาจะคำนวณอัตโนมัติ)
</body></html>""",

            3: """<html><body style='font-family: Arial; font-size: 14px; color: #1e293b;'>
<b style='font-size: 17px; color: #b91c1c;'>3. จัดการตะกร้า, ใส่ส่วนลด & พักบิล</b><br>
การปรับแต่งรายการสินค้าและจัดการบิลก่อนคิดเงิน<br><br>
<b>ฟังก์ชันหลักในหน้านี้:</b><br>
<span style='color: #dc2626;'><b>ใส่ส่วนลด:</b></span> กดปุ่มเพื่อระบุส่วนลดเป็นเงินบาท (฿) หรือเปอร์เซ็นต์ (%) ระบบจะหักลบและคำนวณยอดสุทธิให้อัตโนมัติ<br>
<span style='color: #d97706;'><b>พักบิล:</b></span> พักบิลปัจจุบันเพื่อรับลูกค้าท่านอื่นก่อน โดยระบุชื่อ/เลขอ้างอิง บิลจะถูกบันทึกขึ้นระบบฐานข้อมูลทันที<br>
<span style='color: #4f46e5;'><b>บิลพัก:</b></span> ดูรายการบิลที่พักไว้ และกดดึงกลับมาลงตะกร้าเพื่อคิดเงินต่อได้ทันที<br>
<span style='color: #16a34a;'><b>+ / - / ลบ:</b></span> ปรับเพิ่ม-ลดจำนวนสินค้า หรือกดถังขยะเพื่อลบรายการออกจากตะกร้า
</body></html>""",

            4: """<html><body style='font-family: Arial; font-size: 15px; color: #1e293b;'>
<b style='font-size: 18px; color: #b91c1c;'>4. ชำระเงิน & พิมพ์ใบเสร็จ</b><br>
ขั้นตอนการรับเงินจากลูกค้า<br><br>
<b>ความหมายของตัวเลขในภาพ:</b><br>
<span style='color: #dc2626;'><b>หมายเลข 1:</b></span> กดปุ่ม <b>"ชำระเงิน"</b> สีแดงด้านล่างสุดของตะกร้า<br>
<span style='color: #dc2626;'><b>หมายเลข 2:</b></span> เลือกช่องทางการรับเงิน (เงินสด หรือ สแกน QR Code PromptPay)<br>
<span style='color: #dc2626;'><b>หมายเลข 3:</b></span> ระบบจะทอนเงิน ตัดสต็อกสินค้า และพิมพ์ใบเสร็จออกมาทันที
</body></html>""",

            5: """<html><body style='font-family: Arial; font-size: 15px; color: #1e293b;'>
<b style='font-size: 18px; color: #b91c1c;'>5. ปิดกะประจำวัน (Z-Report)</b><br>
ขั้นตอนเมื่อสิ้นสุดวัน หรือเปลี่ยนกะพนักงาน<br><br>
<b>ความหมายของตัวเลขในภาพ:</b><br>
<span style='color: #dc2626;'><b>หมายเลข 1:</b></span> กดที่ปุ่มสถานะกะ ด้านบนขวาของหน้าจอ<br>
<span style='color: #dc2626;'><b>หมายเลข 2:</b></span> เลือกเมนู <b>"ปิดกะการขาย"</b><br>
<span style='color: #dc2626;'><b>หมายเลข 3:</b></span> ระบบจะสรุปยอดขายทั้งหมด ให้พนักงานนับเงินสดจริงกรอกลงไป แล้วกดปิดกะ (เครื่องจะพิมพ์สลิป Z-Report ออกมา)
</body></html>"""
        }
        self.desc_label.setText(descriptions.get(self.current_step, ''))

        self.title_label.setText(f" วิธีใช้งานระบบขายหน้าร้าน (JET POS) - ขั้นตอนที่ {self.current_step}/{self.total_steps}")
        
        img_filename = self.image_files.get(self.current_step)
        img_path = os.path.join(self.base_path, 'assets', 'manual', img_filename)
        
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            # scale to fit label (which expands to fill dialog)
            scaled = pixmap.scaled(880, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(scaled)
        else:
            self.img_label.setText("ไม่พบรูปภาพประกอบ")
            self.img_label.setPixmap(QPixmap())
            
        self.btn_prev.setVisible(self.current_step > 1)
        
        if self.current_step < self.total_steps:
            self.btn_next.show()
            self.btn_finish.hide()
        else:
            self.btn_next.hide()
            self.btn_finish.show()
            
    def next_step(self):
        if self.current_step < self.total_steps:
            self.current_step += 1
            self.update_view()
            
    def prev_step(self):
        if self.current_step > 1:
            self.current_step -= 1
            self.update_view()
