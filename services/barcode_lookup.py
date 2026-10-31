"""Barcode / code lookup used by the POS scan box.

Why this module exists
----------------------
Cashiers reported "scan cannot find the product, it looks like the scanner reads
fewer digits, but the same code is found in the ERP". The real causes were:

1. Labels and scanners frequently drop leading zeros (ERP stores 0000001010077,
   the scanner sends 1010077) or the EAN check digit, or encode a 6-digit SKU
   with leading/trailing zeros (0000001043747, 2010740000008) or a 299xxxxxxxxx
   internal EAN-13. The ERP web search uses a LIKE match so it still finds the
   product; the POS used an exact match on products.barcode only.
2. The POS replica kept only the FIRST barcode of each product (usually the
   6-digit SKU), while the ERP stores 4,600+ barcodes in product_barcodes.
3. A 13-digit code that happens to start with a scale prefix (800/801/02/20) was
   decoded as a scale label BEFORE checking registered barcodes, and POPSTAR
   800/801 scale labels embed a 6-digit PLU + 6-digit total price in satang.
4. When Windows is switched to the Thai keyboard layout the scanner "types" Thai
   characters instead of digits (1 -> U+0E45, 4 -> U+0E20, ...), and some of them
   are combining marks that visually disappear, so the code looks incomplete.

All lookups here are tolerant to those cases while still preferring exact matches.
"""

import re
import unicodedata

from sqlalchemy import func, or_

from database.models import Product, ProductBarcode

# Thai Kedmanee layout: key on the number row -> digit it would be on an EN layout
_THAI_LAYOUT_DIGITS = {
    # unshifted number row
    '\u0e45': '1', '/': '2', '-': '3', '\u0e20': '4', '\u0e16': '5',
    '\u0e38': '6', '\u0e36': '7', '\u0e04': '8', '\u0e15': '9', '\u0e08': '0',
    # shifted number row
    '+': '1', '\u0e51': '2', '\u0e52': '3', '\u0e53': '4', '\u0e54': '5',
    '\u0e39': '6', '\u0e3f': '7', '\u0e55': '8', '\u0e56': '9', '\u0e57': '0',
}
# Thai numerals ๐-๙
_THAI_NUMERALS = {chr(0x0E50 + i): str(i) for i in range(10)}

_MIN_FUZZY_LEN = 5


def strip_leading_zeros(code):
    code = str(code or '').strip()
    stripped = code.lstrip('0')
    return stripped if stripped else ('0' if code else '')


def ean_checksum_valid(code):
    """True when the last digit is a valid EAN-8/UPC-A/EAN-13/GTIN-14 check digit."""
    code = str(code or '')
    if not code.isdigit() or len(code) < 8 or len(code) > 14:
        return False
    body, check = code[:-1], int(code[-1])
    total = 0
    for idx, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if idx % 2 == 0 else 1)
    return (10 - (total % 10)) % 10 == check


def normalize_scan_text(raw):
    """Return (cleaned_text, digits_version_or_None).

    cleaned_text  : input without control chars / surrounding spaces.
    digits_version: the same code converted to plain ASCII digits when the input
                    was typed with a Thai keyboard layout or Thai numerals.
    """
    text = unicodedata.normalize('NFC', str(raw or ''))
    text = ''.join(ch for ch in text if unicodedata.category(ch)[0] != 'C').strip()
    if not text:
        return '', None

    compact = re.sub(r'\s+', '', text)
    converted = []
    for ch in compact:
        if ch.isascii() and ch.isdigit():
            converted.append(ch)
        elif ch in _THAI_NUMERALS:
            converted.append(_THAI_NUMERALS[ch])
        elif ch in _THAI_LAYOUT_DIGITS:
            converted.append(_THAI_LAYOUT_DIGITS[ch])
        else:
            converted = None
            break

    digits = ''.join(converted) if converted else None
    return text, digits


def _active(query):
    return query.filter(or_(Product.is_active.is_(True), Product.is_active.is_(None)))


def _products_by_ids(session, ids):
    ids = [i for i in dict.fromkeys(ids) if i is not None]
    if not ids:
        return []
    rows = _active(session.query(Product).filter(Product.id.in_(ids))).all()
    order = {pid: n for n, pid in enumerate(ids)}
    return sorted(rows, key=lambda p: order.get(p.id, 0))


def find_exact(session, codes):
    """Exact match on any registered barcode, sku_code or product name."""
    codes = [c for c in dict.fromkeys(codes) if c]
    if not codes:
        return []
    ids = [row[0] for row in session.query(ProductBarcode.product_id)
           .filter(ProductBarcode.barcode.in_(codes)).all()]
    products = _active(session.query(Product).filter(
        or_(Product.barcode.in_(codes), Product.sku_code.in_(codes), Product.name_th.in_(codes))
    )).all()
    found = {p.id: p for p in products}
    for p in _products_by_ids(session, ids):
        found.setdefault(p.id, p)
    return list(found.values())


def find_tolerant(session, digits):
    """Match ignoring leading/trailing zeros, 299 internal EAN-13, and EAN check digits."""
    if not digits or not digits.isdigit():
        return []
    norm = strip_leading_zeros(digits)
    if len(norm) < _MIN_FUZZY_LEN:
        return []

    targets = {norm}
    # 1. Scanner sent code WITH check digit while DB stores without check digit
    if ean_checksum_valid(digits) and len(norm) > _MIN_FUZZY_LEN:
        targets.add(strip_leading_zeros(digits[:-1]))
    # 2. ERP 13-digit leading-zero padded SKU (e.g. 0000001043747 -> 104374, or scanner stripped zeros -> 1043747 -> 104374)
    if (len(digits) in (12, 13) and digits.startswith('00000')) or len(norm) == 7:
        cand = strip_leading_zeros(digits[:-1])
        if len(cand) >= _MIN_FUZZY_LEN:
            targets.add(cand)
    # 3. ERP 13-digit trailing-zero padded SKU (e.g. 2010740000008 or 1021910000002 -> 201074 / 102191)
    if len(digits) in (12, 13) and digits[6:12] == '000000':
        targets.add(digits[:6])
        targets.add(strip_leading_zeros(digits[:6]))

    found = {}

    # a) leading-zero-insensitive equality on every stored code
    target_list = [t for t in targets if len(t) >= _MIN_FUZZY_LEN]
    if target_list:
        pb_ids = [row[0] for row in session.query(ProductBarcode.product_id).filter(or_(
            ProductBarcode.barcode_norm.in_(target_list),
            func.ltrim(ProductBarcode.barcode, '0').in_(target_list),
        )).all()]
        for p in _products_by_ids(session, pb_ids):
            found.setdefault(p.id, p)
        for p in _active(session.query(Product).filter(or_(
            func.ltrim(Product.barcode, '0').in_(target_list),
            func.ltrim(Product.sku_code, '0').in_(target_list),
        ))).all():
            found.setdefault(p.id, p)
    if found:
        return list(found.values())

    # b) 299 + 9-digit zero-padded product.id + check digit (from UpdateAllBarcodesTo13Digits.php)
    if len(digits) == 13 and digits.startswith('299'):
        try:
            pid = int(digits[3:12])
            for p in _products_by_ids(session, [pid]):
                found.setdefault(p.id, p)
            if found:
                return list(found.values())
        except ValueError:
            pass

    # c) scanner dropped the check digit, or 6-digit SKU matched against XXXXXX000000Y / 000000XXXXXXY
    likes = [f"{norm}_"]
    if len(norm) == 6:
        likes.append(f"{norm}000000_")
    pb_conds = [ProductBarcode.barcode_norm.like(lk) for lk in likes] + [
        func.ltrim(ProductBarcode.barcode, '0').like(lk) for lk in likes
    ]
    pb_rows = session.query(ProductBarcode.product_id, ProductBarcode.barcode).filter(or_(*pb_conds)).all()
    for pid, _ in pb_rows:
        for p in _products_by_ids(session, [pid]):
            found.setdefault(p.id, p)

    prod_conds = [func.ltrim(Product.barcode, '0').like(lk) for lk in likes]
    for p in _active(session.query(Product).filter(or_(*prod_conds))).all():
        found.setdefault(p.id, p)
    return list(found.values())


def find_partial(session, digits):
    """Last resort: the scanned digits are a unique contiguous part of one code.

    Mirrors the ERP web search (LIKE %code%), but only accepted when exactly one
    product matches so a short/partial read can never add the wrong item.
    """
    if not digits or not digits.isdigit():
        return []
    norm = strip_leading_zeros(digits)
    if len(norm) < 6:
        return []
    like = f"%{norm}%"
    ids = [row[0] for row in session.query(ProductBarcode.product_id)
           .filter(ProductBarcode.barcode.like(like)).limit(5).all()]
    found = {p.id: p for p in _products_by_ids(session, ids)}
    for p in _active(session.query(Product).filter(or_(
        Product.barcode.like(like), Product.sku_code.like(like)
    ))).limit(5).all():
        found.setdefault(p.id, p)
    return list(found.values()) if len(found) == 1 else []


def matched_unit_factor(session, product_id, raw):
    """Units per scan for the barcode that was scanned (pack/carton barcodes > 1)."""
    text, digits = normalize_scan_text(raw)
    codes = [c for c in dict.fromkeys([text, digits]) if c]
    if not codes or product_id is None:
        return 1.0
    norms = [strip_leading_zeros(c) for c in codes if c.isdigit()]
    query = session.query(ProductBarcode).filter(ProductBarcode.product_id == product_id)
    row = query.filter(ProductBarcode.barcode.in_(codes)).first()
    if row is None and norms:
        row = query.filter(or_(
            ProductBarcode.barcode_norm.in_(norms),
            func.ltrim(ProductBarcode.barcode, '0').in_(norms),
        )).first()
    try:
        factor = float(row.unit_factor) if row is not None and row.unit_factor else 1.0
    except (TypeError, ValueError):
        factor = 1.0
    return factor if factor > 0 else 1.0


def _resolve_scale_product(session, item_code):
    item_code = str(item_code or '').strip()
    if not item_code:
        return None
    item_norm = strip_leading_zeros(item_code)
    pb = session.query(ProductBarcode).filter(or_(
        ProductBarcode.barcode == item_code,
        ProductBarcode.barcode_norm == item_norm,
        func.ltrim(ProductBarcode.barcode, '0') == item_norm,
    )).first()
    if pb is not None:
        prod = next(iter(_products_by_ids(session, [pb.product_id])), None)
        if prod is not None:
            return prod
    return _active(session.query(Product).filter(or_(
        Product.sku_code == item_code,
        Product.barcode == item_code,
        func.ltrim(Product.sku_code, '0') == item_norm,
        func.ltrim(Product.barcode, '0') == item_norm,
        Product.sku_code.endswith(item_code),
        Product.barcode.endswith(item_code),
    ))).first()


def lookup_product(session, raw, scale_parser=None):
    """Resolve a scanned/typed code.

    Returns a dict:
      {'status': 'found', 'product': Product, 'code': str}
      {'status': 'scale', 'scale': dict, 'product': Product|None, 'code': str}
      {'status': 'ambiguous', 'products': [Product, ...], 'code': str}
      {'status': 'not_found', 'code': str}
    """
    text, digits = normalize_scan_text(raw)
    code = digits or text
    if not text:
        return {'status': 'not_found', 'code': ''}

    def _result(products):
        if len(products) == 1:
            return {'status': 'found', 'product': products[0], 'code': code}
        return {'status': 'ambiguous', 'products': products, 'code': code}

    # 1. Exact registered codes always win (ERP does the same before decoding scale labels)
    exact = find_exact(session, [text, digits])
    if exact:
        return _result(exact)

    # 2. Scale label (POPSTAR 800/801 price-embedded or ScaleProfile weight-embedded)
    if scale_parser is not None and digits:
        # For non-800/801 codes (e.g. starting with 20), check tolerant regular product match first
        # so 6-digit SKUs like 201074 with trailing zeros (2010740000008) are never hijacked as scale labels.
        if not digits.startswith(('800', '801')):
            tolerant_first = find_tolerant(session, digits)
            if tolerant_first:
                return _result(tolerant_first)

        scale = scale_parser.parse(digits, session)
        if scale:
            product = _resolve_scale_product(session, scale.get('item_code'))
            if product is not None:
                scale_info = dict(scale)
                if scale_info.get('weight_from_price') and scale_info.get('price'):
                    unit_price = float(product.pos_price if product.pos_price is not None else (product.default_price or 0.0))
                    if unit_price > 0:
                        scale_info['weight'] = round(float(scale_info['price']) / unit_price, 4)
                return {'status': 'scale', 'scale': scale_info, 'product': product, 'code': code}

    # 3. Leading/trailing zeros, 299 internal EAN-13, or check-digit tolerant
    tolerant = find_tolerant(session, digits)
    if tolerant:
        return _result(tolerant)

    # 4. Unique partial match (same idea as the ERP web LIKE search)
    partial = find_partial(session, digits)
    if partial:
        return _result(partial)

    return {'status': 'not_found', 'code': code}
