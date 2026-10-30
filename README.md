# PopCentral POS (v1.2.9)

ระบบจุดขายหน้าร้านระดับพาณิชย์ (Commercial Desktop POS) พัฒนาด้วย **Python (PySide6 / Qt6)** และ **SQLAlchemy (SQLite)** ออกแบบตามสถาปัตยกรรม **Local-First & Offline-First** สามารถเปิดบิล ขายสินค้า ชั่งน้ำหนัก พิมพ์ใบเสร็จ และรับชำระเงินได้ตลอดเวลาแม้ไม่มีสัญญาณอินเทอร์เน็ต พร้อมระบบ Background Sync อัตโนมัติที่เชื่อมต่อกับ **PopStar ERP Backend**

---

## จุดเด่นของระบบ (Key Features)

- **Local-First Architecture**: ฐานข้อมูล SQLite ในเครื่อง (`%LOCALAPPDATA%\PopCentralPOS\data\pos.db`) ทุกรายการขายจะถูกบันทึกลงเครื่องอย่างสมบูรณ์ก่อนเสมอ ป้องกันข้อมูลสูญหาย 100%
- **Auto Background Synchronization**: ระบบ Worker คอยตรวจสอบสัญญาณอินเทอร์เน็ตและส่งข้อมูลบิลขาย (Outbox Queue) เข้า ERP เซิร์ฟเวอร์แบบ Real-time พร้อมระบบป้องกันบิลซ้ำ (Idempotency Key)
- **เครื่องชั่งน้ำหนักและบาร์โค้ดสินค้าสด (Scale Integration)**: รองรับการอ่านบาร์โค้ดเครื่องชั่งทั้งแบบ Prefix ในร้าน (`800`, `801`, `02`, `20`) และ EAN-13 มาตรฐาน พร้อมระบบแปลงน้ำหนักและราคาอัตโนมัติ
- **ระบบรับชำระเงินครบวงจร (Multi-payment)**:
  - รับเงินสด (Cash) พร้อมปุ่มคีย์ลัด และคำนวณเงินทอนอัตโนมัติ
  - สแกน QR PromptPay พร้อมระบบสร้าง QR Code ตามยอดเงินจริง
  - บัตรเครดิต และการชำระเงินแบบผสม (Split Payment)
- **การจัดการกะและรายงาน (Shift & Cash Management)**:
  - บันทึกเงินทอนเริ่มต้นกะ (Opening Cash)
  - รายงานสรุปยอดขายประจำวันและสรุปกะ (Z-Report)
  - ปิดกะพร้อมนับเงินสดจริงและคำนวณยอดเงิน ขาด/เกิน
- **พิมพ์ใบเสร็จและลิ้นชักเก็บเงิน (Thermal Receipt Printer)**:
  - รองรับเครื่องพิมพ์ความร้อน 80mm และ 58mm (ESC/POS, Windows Driver)
  - หน้าต่างตั้งค่าเครื่องพิมพ์พร้อมระบบแสดงตัวอย่างใบเสร็จสด (Live Preview)
  - ปรับขนาดตัวอักษรใบเสร็จได้ (มาตรฐาน / ตัวใหญ่ ชัดเจน)
- **ปลอดภัยและเสถียร (Enterprise Stability)**:
  - ไม่มี Emoji กวนสายตาบนหน้าต่างหลักและป๊อปอัพ
  - ระบบสำรองฐานข้อมูลอัตโนมัติทุกวันเมื่อเริ่มโปรแกรม

---

## ความต้องการของระบบ (System Requirements)

| รายการ | ความต้องการขั้นต่ำ | แนะนำ |
|---|---|---|
| **ระบบปฏิบัติการ (OS)** | Windows 10 (64-bit) | Windows 11 (64-bit) |
| **หน่วยประมวลผล (CPU)** | Intel Core i3 / AMD Ryzen 3 | Intel Core i5 หรือเทียบเท่า |
| **หน่วยความจำ (RAM)** | 4 GB | 8 GB ขึ้นไป |
| **พื้นที่ว่างบนฮาร์ดดิสก์** | 500 MB | 2 GB ขึ้นไป (SSD) |
| **Python** | Python 3.10 ขึ้นไป | Python 3.12 / 3.14 (64-bit) |
| **เครื่องพิมพ์ใบเสร็จ** | Thermal Printer 58mm / 80mm | Xprinter, Epson, POS-80 |

---

## ขั้นตอนการติดตั้งและใช้งาน (Installation Guide)

### วิธีที่ 1: ติดตั้งจาก Source Code (สำหรับ Developer / Admin)

#### 1. ติดตั้ง Python และ Git
ดาวน์โหลดและติดตั้ง:
- [Python 3.12+ (Windows 64-bit)](https://www.python.org/downloads/) *(ต้องติ๊กเลือก "Add Python to PATH" ตอนติดตั้ง)*
- [Git for Windows](https://git-scm.com/)

#### 2. Clone Repository
เปิด **PowerShell** หรือ **Command Prompt** แล้วรันคำสั่ง:
```bash
git clone https://github.com/nongpee321/posCentral.git
cd posCentral
```

#### 3. สร้าง Virtual Environment
```bash
python -m venv venv
```

#### 4. เปิดใช้งาน Virtual Environment
- **Command Prompt (cmd)**:
  ```cmd
  venv\Scripts\activate.bat
  ```
- **PowerShell**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  *(หากติดสิทธิ์ Execution Policy ให้รัน `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` ก่อน)*

#### 5. ติดตั้ง Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
*(หากต้องการรัน Unit Test หรือ Build ให้ติดตั้ง: `pip install -r requirements-dev.txt`)*

#### 6. เริ่มต้นใช้งานโปรแกรม
รันคำสั่ง:
```bash
python main.py
```
หรือดับเบิลคลิกไฟล์ `run.bat` ได้ทันที

---

### วิธีที่ 2: ติดตั้งผ่านไฟล์ Installer (.exe) สำหรับใช้งานหน้าร้าน

1. รันไฟล์ติดตั้ง `PopCentral-POS-UAT-1.2.9-setup.exe`
2. เลือกโฟลเดอร์ปลายทางที่ต้องการติดตั้ง (เช่น `C:\PopCentral POS`)
3. ตัวติดตั้งจะทำการแยกไฟล์และสร้าง Shortcut บนเดสก์ท็อปให้อัตโนมัติ
4. ดับเบิลคลิกที่ไอคอน `PopCentral POS` เพื่อเริ่มใช้งาน

---

## การตั้งค่าเริ่มต้นเชื่อมต่อ ERP (Initial Configuration)

เมื่อเปิดโปรแกรมครั้งแรก ระบบจะแสดงหน้าต่าง **เข้าสู่ระบบจุดขาย (POS Terminal Authentication)**:

1. **ERP URL**: ใส่ที่อยู่ URL ของเซิร์ฟเวอร์ ERP เช่น:
   ```
   https://erp.popstarcenter.com
   ```
2. **POS Token**: ใส่ Token ที่ได้รับจากระบบ ERP สำหรับเครื่อง POS ประจำสาขา
3. **Username**: ใส่ชื่อผู้ใช้งานแคชเชียร์
4. กดปุ่ม **"เข้าสู่ระบบ (บันทึกข้อมูล)"**
   - ระบบจะตรวจสอบการเชื่อมต่อไปยัง ERP ดึงข้อมูลสาขา (Branch) และรายการสินค้าล่าสุดลงฐานข้อมูลในเครื่องอัตโนมัติ

---

## การทดสอบระบบ (Running Automated Tests)

โปรเจกต์มีชุดทดสอบครอบคลุมทั้ง Flow การขาย, ออฟไลน์เช็คเอาต์, การคำนวณใบเสร็จ และการซิงค์:

```powershell
$env:PYTHONPATH = "."
python -m pytest tests -W ignore
```
หรือรันผ่านสคริปต์:
```cmd
run_tests.bat
```

---

## วิธี Build เป็นไฟล์ติดตั้ง (.exe)

โปรเจกต์มีสคริปต์ PowerShell สำหรับคอมไพล์ด้วย **PyInstaller** และแพ็กเกจเป็นไฟล์ติดตั้ง Self-Extracting ด้วย **7-Zip**:

### สิ่งที่ต้องมีเพิ่มเติม:
- ติดตั้งโปรแกรม [7-Zip (64-bit)](https://www.7-zip.org/) ไว้ที่ `C:\Program Files\7-Zip`

### คำสั่ง Build:
```powershell
powershell -ExecutionPolicy Bypass -File .\build_pos.ps1 -Version "1.2.9"
```
ไฟล์ติดตั้งสำเร็จรูปจะถูกสร้างไว้ที่โฟลเดอร์ `dist\PopCentral-POS-UAT-1.2.9-setup.exe`

---

## โครงสร้างโปรเจกต์ (Project Structure)

```text
posCentral/
├── assets/                  # ไอคอน โลโก้ รูปภาพ และคู่มือ
├── database/
│   ├── __init__.py
│   └── models.py            # SQLAlchemy Database Models & Migration
├── services/
│   ├── __init__.py
│   ├── offline_auth.py      # ระบบยืนยันตัวตนแคชเชียร์แบบออฟไลน์
│   └── scale_service.py     # ตัวแปลงบาร์โค้ดเครื่องชั่งน้ำหนัก
├── ui/
│   ├── main_window.py       # หน้าต่างขายหลัก (POS Main Window)
│   ├── token_dialog.py      # หน้าต่างตั้งค่าและ Token เข้าสู่ระบบ
│   ├── login_dialog.py      # หน้าต่างสลับแคชเชียร์
│   ├── payment_dialog.py    # หน้าต่างรับชำระเงิน (Cash/QR)
│   ├── receipt_dialog.py    # ออกแบบและพิมพ์ใบเสร็จ
│   ├── shift_dialog.py      # เปิด/ปิดกะขาย
│   ├── pending_sync_dialog.py # ตรวจสอบรายการบิลค้างส่ง
│   ├── discount_dialog.py   # จัดการส่วนลดสินค้า/ท้ายบิล
│   ├── held_bills_dialog.py # บิลพักชั่วคราว
│   ├── scale_weight_dialog.py # หน้าต่างกรอก/ยืนยันน้ำหนัก
│   └── customer_display.py  # จอแสดงผลฝั่งลูกค้า (Customer Display)
├── tests/                   # ชุดทดสอบ Automated Pytest (19 Tests)
├── build_pos.ps1            # สคริปต์ Build ตัวติดตั้ง (.exe)
├── main.py                  # จุดเริ่มต้นการทำงานหลัก (App Entry Point)
├── sync_worker.py           # Background Sync Engine (Real-time Outbox)
├── pos.db                   # Template SQLite Database พร้อม Seed แคตตาล็อก
├── requirements.txt         # Production Dependencies
├── requirements-dev.txt     # Development & Build Dependencies
├── run.bat                  # สคริปต์รันโปรแกรมด่วน
├── run_tests.bat            # สคริปต์รัน Flake8 และ Pytest
└── README.md                # เอกสารคู่มือการติดตั้งและใช้งาน
```

---

## License

Proprietary Software - สงวนลิขสิทธิ์ บริษัท ป๊อปสตาร์ฟู้ดส์ เทรดดิ้ง จำกัด (Pop Star Food Trading Co., Ltd.)
