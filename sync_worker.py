import os

import time

import requests

import json

import uuid

from datetime import datetime

from PySide6.QtCore import QThread, Signal

import threading

from database.models import (

    init_db, Product, ProductBarcode, Category, Sale, SaleItem, Payment, Outbox, SyncLog, PosShift

)

from sqlalchemy.orm import Session

class SyncWorker(QThread):

    # Signals to communicate with the main GUI thread

    sync_started = Signal()

    sync_finished = Signal(bool, str) # success, message

    products_updated = Signal()

    pending_count_updated = Signal(int) # emits number of unsynced bills for UI badge

    manual_sync_finished = Signal(bool, str)

    def __init__(self, db_path, api_url, pos_token, config=None):

        super().__init__()

        self.db_path = db_path

        self.api_url = api_url.rstrip('/') if api_url else 'http://localhost:8000'

        self.pos_token = pos_token

        self.config = config or {}

        self.is_running = True

        self.force_sync_flag = False

        self.manual_sync_requested = False

        self.retry_failed_requested = False

        self._wake_event = threading.Event()

        self._consecutive_offline_count = 0

    def _resolve_branch_and_cashier(self, session):

        branch_id = None

        cashier_id = None

        if self.config:

            branch_id = self.config.get('branch_id')

            cashier_id = self.config.get('cashier_id')

        if not branch_id or not cashier_id:

            import os, json

            candidates = [

                os.path.expanduser(r'~\AppData\Local\PopCentralPOS\config.json'),

                os.path.join(os.path.dirname(os.path.abspath(self.db_path)), 'config.json'),

                os.path.join(os.getcwd(), 'config.json'),

                'config.json'

            ]

            for cfg_path in candidates:

                if os.path.exists(cfg_path):

                    try:

                        with open(cfg_path, 'r', encoding='utf-8') as f:

                            data = json.load(f)

                            branch_id = branch_id or data.get('branch_id')

                            cashier_id = cashier_id or data.get('cashier_id')

                            if branch_id and cashier_id:

                                break

                    except Exception:

                        pass

        if not branch_id or not cashier_id:

            last_shift = session.query(PosShift).order_by(PosShift.id.desc()).first()

            if last_shift:

                branch_id = branch_id or getattr(last_shift, 'branch_id', None)

                cashier_id = cashier_id or getattr(last_shift, 'cashier_id', None)

        if not branch_id or not cashier_id:

            last_sale = session.query(Sale).filter(Sale.branch_id.isnot(None)).order_by(Sale.id.desc()).first()

            if last_sale:

                branch_id = branch_id or getattr(last_sale, 'branch_id', None)

                cashier_id = cashier_id or getattr(last_sale, 'cashier_salesman_id', None)

        return branch_id, cashier_id

    def force_sync(self, retry_failed=False):

        self.force_sync_flag = True

        self.manual_sync_requested = True

        self.retry_failed_requested = self.retry_failed_requested or retry_failed

        self._wake_event.set()

    def _check_internet(self):

        # 1. First check if ERP API is reachable with auth and reasonable timeout

        headers = {

            'Authorization': f'Bearer {self.pos_token}',

            'Accept': 'application/json'

        }

        try:

            r = requests.get(f"{self.api_url}/api/pos/ping", headers=headers, timeout=6)

            if r.status_code in (200, 401, 403):

                self._consecutive_offline_count = 0

                return True

        except Exception:

            pass

        # 2. Check general external internet

        import socket

        try:

            socket.create_connection(("1.1.1.1", 53), timeout=3)

            self._consecutive_offline_count = 0

            return True

        except OSError:

            try:

                socket.create_connection(("8.8.8.8", 53), timeout=3)

                self._consecutive_offline_count = 0

                return True

            except OSError:

                pass

        # Tolerate a single transient timeout before reporting offline

        self._consecutive_offline_count += 1

        if self._consecutive_offline_count < 2:

            return True

        return False

    def get_pending_count(self):

        session = init_db(f'sqlite:///{self.db_path}')

        try:

            sales_count = session.query(Sale).filter(Sale.status.in_(['pending', 'failed'])).count()
            shifts_count = session.query(PosShift).filter(
                PosShift.status == 'closed', PosShift.sync_status.in_(['pending', 'failed'])
            ).count()
            outbox_shifts = session.query(Outbox).filter(
                Outbox.event_type == 'shift_close', Outbox.status.in_(['pending', 'failed'])
            ).count()
            return sales_count + max(shifts_count, outbox_shifts)

        except Exception:

            return 0

        finally:

            session.close()

    def _check_catalog_version(self):

        """

        ตรวจสอบเลขเวอร์ชันแคตตาล็อกราคา/โปรโมชั่นผ่าน /api/pos/ping

        ถ้ามีการแก้ไขราคา โปรโมชั่น หรือนาทีทองบน ERP ตัวเลขเวอร์ชันจะเปลี่ยนทันที

        """

        headers = {

            'Authorization': f'Bearer {self.pos_token}',

            'Accept': 'application/json'

        }

        try:

            resp = requests.get(f'{self.api_url}/api/pos/ping', headers=headers, timeout=6)

            if resp.status_code == 200:

                data = resp.json()

                server_ver = data.get('catalog_version', 0)

                last_ver = getattr(self, '_last_catalog_version', None)

                if last_ver is not None and server_ver != last_ver:

                    self._last_catalog_version = server_ver

                    return True

                self._last_catalog_version = server_ver

        except Exception:

            pass

        return False

    def run(self):

        loop_count = 0

        while self.is_running:

            manual_sync = self.manual_sync_requested

            retry_failed = self.retry_failed_requested

            self.manual_sync_requested = False

            self.retry_failed_requested = False

            try:

                # Update pending count badge on every loop

                pending_count = self.get_pending_count()

                self.pending_count_updated.emit(pending_count)

                if not self._check_internet():

                    if self.is_running:

                        self.sync_finished.emit(False, "No Internet Connection (ระบบออฟไลน์)")

                        if manual_sync:

                            self.manual_sync_finished.emit(False, "ไม่สามารถเชื่อมต่ออินเทอร์เน็ตได้")

                    if not self.is_running:

                        break

                    # Back off 15 seconds when offline to prevent disk write spam and CPU thrashing

                    self._wake_event.wait(15)

                    self._wake_event.clear()

                    continue

                if manual_sync or pending_count > 0:

                    self.sync_started.emit()

                if self.is_running:

                    changed = False

                    if retry_failed:

                        session = init_db(f'sqlite:///{self.db_path}')

                        try:

                            session.query(Outbox).filter(Outbox.status == 'failed').update(

                                {'status': 'pending', 'retry_count': 0}, synchronize_session=False

                            )

                            session.query(Sale).filter(Sale.status == 'failed').update(

                                {'status': 'pending'}, synchronize_session=False

                            )

                            session.query(PosShift).filter(PosShift.sync_status == 'failed').update(

                                {'sync_status': 'pending'}, synchronize_session=False

                            )

                            session.commit()

                        finally:

                            session.close()

                    # Prioritize committed sales before network checks for catalog refresh.

                    sync_result = self._sync_outbox_sales()

                    # เช็ค Real-time: มีการอัปเดตราคาหรือโปรโมชั่นบน ERP หรือไม่

                    version_changed = self._check_catalog_version()

                    # Sync products ทันทีถ้าเวอร์ชันเปลี่ยน หรือกด sync หรือทุก ~10 นาที

                    is_initial_run = getattr(self, '_last_catalog_version', None) is None

                    if is_initial_run or version_changed or manual_sync or (loop_count % 60 == 0):

                        changed = self._sync_products()

                    if changed:

                        self.products_updated.emit()

                    self.sync_finished.emit(True, "Sync successful")

                    if manual_sync:

                        self.manual_sync_finished.emit(*sync_result)

            except Exception as e:

                import traceback

                error_msg = str(e)

                log_dir = os.path.dirname(self.db_path)

                try:

                    with open(os.path.join(log_dir, "sync_error.log"), "a", encoding="utf-8") as f:

                        f.write(f"[{datetime.now().isoformat()}] {traceback.format_exc()}\n")

                except Exception:

                    pass

                if self.is_running:

                    self.sync_finished.emit(False, error_msg)

                    if manual_sync:

                        self.manual_sync_finished.emit(False, error_msg)

            loop_count += 1

            # รอบรอ 10 วินาที เพื่อความเสถียรและประหยัดเน็ต/CPU

            self._wake_event.wait(10)

            self._wake_event.clear()

            if self.force_sync_flag:

                self.force_sync_flag = False

                loop_count = -1

    def _sync_products(self):

        headers = {

            'Authorization': f'Bearer {self.pos_token}',

            'Accept': 'application/json'

        }

        session = init_db(f'sqlite:///{self.db_path}')

        changed = False

        try:

            # 1. PUSH OFFLINE PRODUCTS FIRST

            offline_products = session.query(Product).filter(Product.id < 0).all()

            for prod in offline_products:

                prod_payload = {

                    'name_th': prod.name_th,

                    'default_price': prod.default_price,

                    'barcode': str(prod.barcode or prod.sku_code)

                }

                try:

                    resp = requests.post(f'{self.api_url}/api/pos/products', json=prod_payload, headers=headers, timeout=30)

                    if resp.status_code == 200:

                        new_id = resp.json().get('product_id')

                        if new_id:

                            old_id = prod.id

                            session.query(SaleItem).filter(SaleItem.product_id == old_id).update({"product_id": new_id}, synchronize_session=False)

                            session.query(Product).filter(Product.id == old_id).update({"id": new_id}, synchronize_session=False)

                            session.commit()

                            changed = True

                except Exception:

                    pass

            # 2. FETCH FROM SERVER

            response = requests.get(f'{self.api_url}/api/pos/products?all=1', headers=headers, timeout=45)

            response.raise_for_status()

            products_data = response.json()

            import hashlib

            products_json_str = json.dumps(products_data, sort_keys=True)

            current_hash = hashlib.md5(products_json_str.encode('utf-8')).hexdigest()

            if getattr(self, '_last_products_hash', None) == current_hash and not changed:

                return False

            self._last_products_hash = current_hash

            changed = True

            # 3. REPLACE LOCAL REPLICA

            session.query(Product).filter(Product.id > 0).delete(synchronize_session=False)

            session.query(ProductBarcode).filter(ProductBarcode.product_id > 0).delete(synchronize_session=False)

            for prod_data in products_data:

                barcode_val = ''

                all_codes = []

                for bc in (prod_data.get('barcodes') or []):

                    code = str((bc or {}).get('barcode') or '').strip()

                    if code and code not in [c['code'] for c in all_codes]:

                        unit_obj = (bc or {}).get('unit') or {}

                        all_codes.append({
                            'code': code,
                            'barcode_type': (bc or {}).get('barcode_type'),
                            'unit_id': (bc or {}).get('unit_id'),
                            'unit_name': (bc or {}).get('unit_name') or (unit_obj.get('name') if isinstance(unit_obj, dict) else None),
                            'unit_factor': (bc or {}).get('unit_factor'),
                            'price': (bc or {}).get('price'),
                        })

                sku_str = str(prod_data.get('sku_code', '') or '').strip()

                if all_codes:

                    barcode_val = all_codes[0]['code']

                else:

                    barcode_val = sku_str

                if sku_str and sku_str not in [c['code'] for c in all_codes]:

                    all_codes.append({
                        'code': sku_str,
                        'barcode_type': 'CUSTOM',
                        'unit_id': None,
                        'unit_name': None,
                        'unit_factor': 1.0,
                        'price': None,
                    })

                has_scale_plu = any(
                    (c.get('barcode_type') == 'SCALE_PLU')
                    or (len(c['code']) == 6 and c['code'].isdigit() and c['code'].startswith(('800', '801')))
                    for c in all_codes
                )

                for bc_item in all_codes:

                    code = bc_item['code']
                    try:
                        unit_factor = float(bc_item['unit_factor']) if bc_item.get('unit_factor') is not None else 1.0
                    except (TypeError, ValueError):
                        unit_factor = 1.0
                    try:
                        bc_price = float(bc_item['price']) if bc_item.get('price') is not None else None
                    except (TypeError, ValueError):
                        bc_price = None

                    session.add(ProductBarcode(
                        product_id=prod_data['id'],
                        barcode=code,
                        barcode_norm=(code.lstrip('0') or '0'),
                        barcode_type=bc_item.get('barcode_type'),
                        unit_id=bc_item.get('unit_id'),
                        unit_name=bc_item.get('unit_name'),
                        unit_factor=unit_factor,
                        price=bc_price,
                    ))

                prod = Product(

                    id=prod_data['id'],

                    sku_code=str(prod_data['sku_code']),

                    name_th=prod_data['name_th'],

                    name_en=prod_data.get('name_en', ''),

                    default_price=prod_data['default_price'],

                    pos_price=prod_data.get('pos_price', prod_data['default_price']),

                    category_id=prod_data.get('product_category_id'),

                    image_url=prod_data.get('image_url'),

                    is_active=prod_data.get('is_active', True),

                    barcode=barcode_val,

                    stock_qty=prod_data.get('stock_qty'),

                    is_scale_item=bool(prod_data.get('is_scale') or prod_data.get('is_scale_item') or prod_data.get('is_weight') or has_scale_plu or ('ชั่ง' in str(prod_data.get('name_th') or '')) or ('(กก' in str(prod_data.get('name_th') or '')) or str(prod_data.get('sku_code') or '').startswith(('800', '801')) or False),

                    is_promotion=bool(prod_data.get('is_promotion') or prod_data.get('is_flash_sale') or (prod_data.get('price_source') in ['promotion', 'flash_sale']))

                )

                session.add(prod)

            session.commit()

            # Record in sync_logs

            log = SyncLog(

                direction='pull',

                sync_type='products',

                record_count=len(products_data),

                status='success',

                message=f'Synced {len(products_data)} products successfully'

            )

            session.add(log)

            session.commit()

            return changed

        except Exception as e:

            session.rollback()

            try:

                log = SyncLog(

                    direction='pull',

                    sync_type='products',

                    record_count=0,

                    status='failed',

                    message=str(e)

                )

                session.add(log)

                session.commit()

            except Exception:

                pass

            raise e

        finally:

            session.close()

    def _sync_outbox_sales(self):

        headers = {

            'Authorization': f'Bearer {self.pos_token}',

            'Accept': 'application/json'

        }

        session = init_db(f'sqlite:///{self.db_path}')

        # ตรวจสอบว่ามีบิลที่ค้างส่งหรือไม่ หากไม่มีเลยให้ผ่านทันที

        pending_count = session.query(Sale).filter(Sale.status.in_(['pending', 'failed'])).count()

        pending_outbox_count = session.query(Outbox).filter(
            Outbox.event_type == 'sale_checkout', Outbox.status.in_(['pending', 'failed'])
        ).count()

        pending_shifts_count = session.query(PosShift).filter(
            PosShift.status == 'closed', PosShift.sync_status.in_(['pending', 'failed'])
        ).count()

        pending_shift_outbox = session.query(Outbox).filter(
            Outbox.event_type == 'shift_close', Outbox.status.in_(['pending', 'failed'])
        ).count()

        if pending_count == 0 and pending_outbox_count == 0 and pending_shifts_count == 0 and pending_shift_outbox == 0:

            session.close()

            return True, "ไม่มีบิลหรือกะค้างส่ง"

        # หากไม่มีบิลขายค้าง แต่มีกะที่ปิดออฟไลน์ค้าง ให้ซิงค์ปิดกะทันที
        if pending_count == 0 and pending_outbox_count == 0:

            shift_ok = self._sync_pending_closed_shifts(session, headers)

            updated_pending = self.get_pending_count()

            self.pending_count_updated.emit(updated_pending)

            session.close()

            if shift_ok:
                return True, "ซิงค์ปิดกะขึ้น ERP สำเร็จเรียบร้อย"
            return False, "ซิงค์ปิดกะขึ้น ERP ไม่สำเร็จ" 

        # ตรวจสอบกะที่เปิดอยู่บนเซิร์ฟเวอร์ ERP

        branch_id, cashier_id = self._resolve_branch_and_cashier(session)

        shift_params = {}

        if branch_id:

            shift_params['branch_id'] = branch_id

        if cashier_id:

            shift_params['cashier_id'] = cashier_id

        shift_data = None

        try:

            shift_response = requests.get(

                f'{self.api_url}/api/pos/shift',

                headers=headers,

                params=shift_params,

                timeout=20

            )

            if shift_response.status_code == 200:

                shift_data = shift_response.json().get('shift')

        except Exception as exc:

            session.close()

            return False, f"ตรวจสอบกะขายไม่สำเร็จ: {exc}"

        # หากเซิร์ฟเวอร์ยังไม่มีกะเปิดอยู่ แต่ในเครื่องมีบิลออฟไลน์หรือกะออฟไลน์ค้าง ให้เปิด/ซิงค์กะขึ้น ERP อัตโนมัติ

        if not shift_data:

            pending_local_shift = session.query(PosShift).filter(

                PosShift.sync_status == 'pending'

            ).order_by(PosShift.id.desc()).first()

            if not pending_local_shift:

                pending_local_shift = session.query(PosShift).filter(

                    PosShift.status == 'open'

                ).order_by(PosShift.id.desc()).first()

            opening_cash = float(pending_local_shift.opening_cash) if (pending_local_shift and pending_local_shift.opening_cash is not None) else 500.0

            open_body = {

                'opening_cash': opening_cash,

                'opening_note': f"ซิงค์กะออฟไลน์อัตโนมัติ (Shift #{pending_local_shift.id if pending_local_shift else 'Offline'})"

            }

            if branch_id:

                open_body['branch_id'] = branch_id

            if cashier_id:

                open_body['cashier_id'] = cashier_id

            try:

                open_res = requests.post(

                    f'{self.api_url}/api/pos/shift/open',

                    headers=headers,

                    json=open_body,

                    timeout=20

                )

                if open_res.status_code == 200:

                    shift_data = open_res.json().get('shift')

                    if shift_data and pending_local_shift:

                        pending_local_shift.server_id = shift_data['id']

                        pending_local_shift.sync_status = 'synced'

                        session.commit()

            except Exception as e:

                pass

        if not shift_data:

            session.close()

            return False, "ยังไม่มีกะขายที่เปิดอยู่ใน ERP กรุณาเปิดกะแล้วลองส่งอีกครั้ง"

        shift_id = shift_data['id']

        branch_id = shift_data.get('branch_id') or branch_id

        cashier_id = shift_data.get('cashier_id') or cashier_id

        try:

            # 1. First ensure all pending sales have an Outbox entry

            pending_sales = session.query(Sale).filter(Sale.status.in_(['pending', 'failed'])).all()

            for sale in pending_sales:

                existing_outbox = session.query(Outbox).filter_by(aggregate_id=sale.local_sale_id).first()

                if not existing_outbox:

                    items = session.query(SaleItem).filter_by(sale_id=sale.local_sale_id).all()

                    method = sale.payment_method or 'cash'

                    payload = {

                        "local_sale_id": sale.local_sale_id,

                        "branch_id": branch_id,

                        "shift_id": shift_id,

                        "cashier_id": cashier_id,

                        "method": method,

                        "payment_confirmed": True,

                        "cash_received": sale.received_amount,

                        "cash_amount": sale.cash_amount or (sale.total_amount if method == 'cash' else 0),

                        "transfer_amount": sale.transfer_amount or (sale.total_amount if method == 'transfer' else 0),

                        "change_amount": max(0, sale.received_amount - (sale.cash_amount or sale.total_amount)) if method in ('cash', 'mixed') else 0,

                        "is_full_tax": sale.is_full_tax,

                        "customer_name": sale.customer_name,

                        "customer_tax_id": sale.customer_tax_id,

                        "customer_address": sale.customer_address,

                        "discount_amount": float(getattr(sale, 'discount_amount', 0.0) or 0.0),

                        "manual_discount_amount": float(getattr(sale, 'discount_amount', 0.0) or 0.0),

                        "is_offline_sync": True,

                        "items": [

                            {

                                "product_id": it.product_id,

                                "qty": it.qty,

                                "unit_price": it.unit_price

                            } for it in items

                        ]

                    }

                    if method in ('transfer', 'mixed'):

                        payload['payment_confirmed'] = True

                        payload['transfer_account_last4'] = '0000'

                        payload['payment_ref'] = '0000' 

                    outbox_entry = Outbox(

                        event_type='sale_checkout',

                        aggregate_id=sale.local_sale_id,

                        payload_json=json.dumps(payload),

                        idempotency_key=sale.idempotency_key or f"offline-sale-{sale.local_sale_id}",

                        status='pending'

                    )

                    session.add(outbox_entry)

            session.commit()

            # Legacy versions used different keys for immediate checkout and retry.

            # Reuse the immediate request key so an ambiguous timeout cannot duplicate a sale.

            legacy_entries = session.query(Outbox).filter(

                Outbox.event_type == 'sale_checkout',

                Outbox.status.in_(['pending', 'failed'])

            ).all()

            for entry in legacy_entries:

                legacy_key = f"pos-sale-{entry.aggregate_id}"

                if entry.idempotency_key != legacy_key:

                    continue

                entry.idempotency_key = f"pos-direct-{entry.aggregate_id}"

                sale = session.query(Sale).filter_by(local_sale_id=entry.aggregate_id).first()

                if sale and sale.idempotency_key == legacy_key:

                    sale.idempotency_key = entry.idempotency_key

            session.commit()

            # 2. Process outbox queue

            pending_outbox = session.query(Outbox).filter(Outbox.event_type == 'sale_checkout', Outbox.status.in_(['pending', 'failed'])).all()

            failed_count = 0

            for entry in pending_outbox:

                sale = session.query(Sale).filter_by(local_sale_id=entry.aggregate_id).first()

                payload = json.loads(entry.payload_json)

                if not entry.payload_prepared:
                    # Freeze server IDs before the first request so retries use the same payload.
                    if branch_id:
                        payload['branch_id'] = branch_id
                    if shift_id:
                        payload['shift_id'] = shift_id
                    if cashier_id:
                        payload['cashier_id'] = cashier_id
                    if payload.get('method') in ('transfer', 'mixed'):
                        payload['payment_confirmed'] = True
                        last4 = payload.get('transfer_account_last4') or payload.get('payment_ref') or '0000'
                        if not (isinstance(last4, str) and last4.isdigit() and len(last4) == 4):
                            last4 = '0000'
                        payload['transfer_account_last4'] = last4
                        payload['payment_ref'] = payload.get('payment_ref') or last4
                    entry.payload_prepared = True
                else:
                    # Auto-heal branch_id or shift_id if they don't match active terminal branch or if previous error was branch/shift invalid
                    current_branch_id = branch_id
                    current_shift_id = shift_id
                    needs_healing = (
                        (current_branch_id and payload.get('branch_id') != current_branch_id)
                        or (current_shift_id and payload.get('shift_id') != current_shift_id and entry.status == 'failed')
                        or (entry.last_error and ('branch id is invalid' in entry.last_error.lower() or 'shift' in entry.last_error.lower()))
                        or (sale and sale.sync_error and ('branch id is invalid' in sale.sync_error.lower() or 'shift' in sale.sync_error.lower()))
                    )
                    if needs_healing and current_branch_id:
                        payload['branch_id'] = current_branch_id
                        if current_shift_id:
                            payload['shift_id'] = current_shift_id
                        if cashier_id:
                            payload['cashier_id'] = cashier_id
                        if sale:
                            sale.branch_id = current_branch_id
                            if current_shift_id:
                                sale.shift_id = current_shift_id
                            if cashier_id:
                                sale.cashier_salesman_id = cashier_id

                # Ensure offline sync flag is present
                payload['is_offline_sync'] = True

                # Auto-heal discount and items if bill had discount or was rejected by manager approval / pricing / shortfall
                sale_total = float(sale.total_amount if sale else (payload.get('cash_received') or 0.0))
                payload_items = payload.get('items') or []
                gross_sum_raw = sum(float(i.get('qty', 0) or 0) * float(i.get('unit_price', 0) or 0) for i in payload_items)
                has_price_reduction = (sale_total > 0 and gross_sum_raw > sale_total + 0.01)
                needs_discount_healing = (
                    payload_items
                    and (
                        has_price_reduction
                        or payload.get('manual_discount_amount', 0) > 0
                        or payload.get('discount_amount', 0) > 0
                        or (sale and getattr(sale, 'discount_amount', 0.0) and float(sale.discount_amount) > 0)
                        or (entry.last_error and any(err in entry.last_error for err in ('ส่วนลดพิเศษ', 'สิทธิ์อนุมัติ', 'ไม่ครบ', 'ราคาหรือส่วนลดเปลี่ยน')))
                        or (sale and sale.sync_error and any(err in sale.sync_error for err in ('ส่วนลดพิเศษ', 'สิทธิ์อนุมัติ', 'ไม่ครบ', 'ราคาหรือส่วนลดเปลี่ยน')))
                    )
                )

                if needs_discount_healing:
                    # Ensure items have standard catalog prices so PosPricingGuard passes with 0 discrepancy
                    for it in payload_items:
                        prod_id = it.get('product_id')
                        if prod_id:
                            prod_record = session.query(Product).filter_by(id=prod_id).first()
                            if prod_record:
                                cat_price = float(prod_record.pos_price or prod_record.default_price or it.get('unit_price', 0.0))
                                if cat_price > 0 and abs(float(it.get('unit_price', 0.0)) - cat_price) > 0.01:
                                    it['unit_price'] = cat_price

                    gross_sum = sum(float(i.get('qty', 0) or 0) * float(i.get('unit_price', 0) or 0) for i in payload_items)
                    discount_val = max(0.0, round(gross_sum - sale_total, 2)) if (sale_total > 0 and gross_sum > sale_total) else float(payload.get('discount_amount') or (getattr(sale, 'discount_amount', 0.0) if sale else 0.0) or 0.0)

                    # Update discount fields: manual_discount_amount must be 0 so manager permission is never required
                    payload['discount_amount'] = discount_val
                    payload['manual_discount_amount'] = 0.0

                    # Fix cash payments: PosPaymentValidator requires cash_received >= gross sum
                    if payload.get('method') == 'cash':
                        orig_received = float(payload.get('cash_received') or 0.0)
                        if orig_received < gross_sum:
                            payload['cash_received'] = gross_sum
                            payload['change_amount'] = max(0.0, round(gross_sum - sale_total, 2))

                    # Fix mixed payments: cash_amount + transfer_amount == gross_sum
                    if payload.get('method') == 'mixed' and gross_sum > 0:
                        cur_mix_sum = float(payload.get('cash_amount') or 0.0) + float(payload.get('transfer_amount') or 0.0)
                        diff = round(gross_sum - cur_mix_sum, 2)
                        if abs(diff) > 0.01:
                            payload['cash_amount'] = round(float(payload.get('cash_amount') or 0.0) + diff, 2)

                # If transfer or mixed, ensure transfer validation fields are present
                if payload.get('method') in ('transfer', 'mixed'):
                    payload['payment_confirmed'] = True
                    last4 = payload.get('transfer_account_last4') or payload.get('payment_ref') or '0000'
                    if not (isinstance(last4, str) and last4.isdigit() and len(last4) == 4):
                        last4 = '0000'
                    payload['transfer_account_last4'] = last4
                    payload['payment_ref'] = payload.get('payment_ref') or last4

                entry.payload_json = json.dumps(payload)
                session.commit()
                req_headers = dict(headers)

                req_headers['Idempotency-Key'] = entry.idempotency_key
                req_headers['X-Idempotency-Key'] = entry.idempotency_key

                try:

                    checkout_response = requests.post(f'{self.api_url}/api/pos/checkout', json=payload, headers=req_headers, timeout=45)

                    if checkout_response.status_code in (200, 201):

                        entry.status = 'synced'

                        entry.synced_at = datetime.utcnow()

                        if sale:

                            sale.status = 'synced'

                            sale.synced_at = datetime.utcnow()

                            sale.sync_error = None

                            resp_data = checkout_response.json()

                            if 'receipt_no' in resp_data:

                                sale.doc_number = resp_data['receipt_no']

                                sale.server_receipt_id = resp_data.get('receipt_id') or resp_data['receipt_no']

                        log = SyncLog(

                            direction='push',

                            sync_type='sale_checkout',

                            record_count=1,

                            status='success',

                            message=f"Sale {entry.aggregate_id} synced"

                        )

                        session.add(log)

                    elif 400 <= checkout_response.status_code < 500:

                        entry.status = 'failed'

                        entry.retry_count += 1

                        entry.last_error = checkout_response.text

                        if sale:

                            sale.status = 'failed'

                            sale.sync_error = checkout_response.text

                        failed_count += 1

                    else:

                        entry.retry_count += 1

                        entry.last_error = f"Server returned HTTP {checkout_response.status_code}"

                        failed_count += 1

                except Exception as ex:

                    entry.retry_count += 1

                    entry.last_error = str(ex)

                    if sale:

                        sale.sync_error = str(ex)

                    failed_count += 1

                session.commit()

            # 3. Process pending closed shifts after sales are synced
            self._sync_pending_closed_shifts(session, headers)

            # Emit updated pending count to update badge

            updated_pending = self.get_pending_count()

            self.pending_count_updated.emit(updated_pending)

            if failed_count:

                return False, f"ส่งบิลไม่สำเร็จ {failed_count} บิล กรุณาตรวจสอบสาเหตุในรายการบิลค้าง"

            if updated_pending:

                return False, f"ยังมีบิลค้าง {updated_pending} บิล ระบบยังส่งไม่ครบ"

            return True, "ส่งบิลขึ้น ERP และได้รับการยืนยันครบแล้ว"

        except Exception as e:

            session.rollback()

            return False, str(e)

        finally:

            session.close()

    def _sync_pending_closed_shifts(self, session, headers):
        """
        ซิงค์กะที่ปิดแบบออฟไลน์ขึ้นระบบ ERP หลังจากส่งบิลขายของกะนั้นเสร็จสิ้นแล้ว
        """
        try:
            pending_close_outbox = session.query(Outbox).filter(
                Outbox.event_type == 'shift_close',
                Outbox.status.in_(['pending', 'failed'])
            ).all()

            pending_closed_shifts = session.query(PosShift).filter(
                PosShift.status == 'closed',
                PosShift.sync_status.in_(['pending', 'failed'])
            ).all()

            if not pending_close_outbox and not pending_closed_shifts:
                return True

            for shift in pending_closed_shifts:
                target_server_id = shift.server_id
                counted_cash = float(shift.counted_cash) if shift.counted_cash is not None else 0.0
                closing_note = "ปิดกะออฟไลน์ (Auto-sync by SyncWorker)"

                matching_ob = next(
                    (ob for ob in pending_close_outbox if ob.aggregate_id in (str(shift.id), str(shift.server_id))),
                    None
                )
                if matching_ob:
                    try:
                        p = json.loads(matching_ob.payload_json)
                        if not target_server_id and p.get('shift_id'):
                            target_server_id = p.get('shift_id')
                        if 'counted_cash' in p:
                            counted_cash = float(p.get('counted_cash'))
                        if p.get('closing_note'):
                            closing_note = p.get('closing_note')
                    except Exception:
                        pass

                if not target_server_id:
                    try:
                        branch_id, cashier_id = self._resolve_branch_and_cashier(session)
                        shift_params = {}
                        if branch_id: shift_params['branch_id'] = branch_id
                        if cashier_id: shift_params['cashier_id'] = cashier_id
                        s_res = requests.get(
                            f"{self.api_url}/api/pos/shift",
                            headers=headers,
                            params=shift_params,
                            timeout=15
                        )
                        if s_res.status_code == 200:
                            s_data = s_res.json().get('shift')
                            if s_data and s_data.get('id'):
                                target_server_id = s_data['id']
                                shift.server_id = target_server_id
                                session.commit()
                    except Exception:
                        pass

                if not target_server_id:
                    continue

                close_body = {
                    'shift_id': target_server_id,
                    'counted_cash': counted_cash,
                    'closing_note': closing_note
                }

                try:
                    close_res = requests.post(
                        f"{self.api_url}/api/pos/shift/close",
                        headers=headers,
                        json=close_body,
                        timeout=25
                    )
                    if close_res.status_code == 200:
                        shift.sync_status = 'synced'
                        if matching_ob:
                            matching_ob.status = 'synced'
                            matching_ob.synced_at = datetime.utcnow()
                        log = SyncLog(
                            direction='push',
                            sync_type='shift_close',
                            record_count=1,
                            status='success',
                            message=f"Shift {target_server_id} successfully closed on ERP (counted: {counted_cash})"
                        )
                        session.add(log)
                        session.commit()
                    elif close_res.status_code == 422:
                        res_json = close_res.json() if close_res.text else {}
                        err_msg = str(res_json.get('message', close_res.text))
                        if "ไม่พบกะที่เปิดอยู่" in err_msg or "ปิดไปแล้ว" in err_msg:
                            shift.sync_status = 'synced'
                            if matching_ob:
                                matching_ob.status = 'synced'
                                matching_ob.synced_at = datetime.utcnow()
                            session.commit()
                        else:
                            shift.sync_status = 'failed'
                            if matching_ob:
                                matching_ob.status = 'failed'
                                matching_ob.last_error = err_msg
                            session.commit()
                    else:
                        shift.sync_status = 'failed'
                        if matching_ob:
                            matching_ob.status = 'failed'
                            matching_ob.last_error = f"HTTP {close_res.status_code}"
                        session.commit()
                except Exception as ex:
                    if matching_ob:
                        matching_ob.last_error = str(ex)
                    pass

            for ob in pending_close_outbox:
                if ob.status == 'pending':
                    try:
                        p = json.loads(ob.payload_json)
                        sid = p.get('shift_id')
                        cc = float(p.get('counted_cash', 0.0))
                        cn = p.get('closing_note', "ปิดกะออฟไลน์")
                        if sid:
                            c_res = requests.post(
                                f"{self.api_url}/api/pos/shift/close",
                                headers=headers,
                                json={'shift_id': sid, 'counted_cash': cc, 'closing_note': cn},
                                timeout=20
                            )
                            if c_res.status_code in (200, 422):
                                ob.status = 'synced'
                                ob.synced_at = datetime.utcnow()
                                session.commit()
                    except Exception:
                        pass

            return True
        except Exception as e:
            return False

