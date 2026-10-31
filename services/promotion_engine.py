from typing import List, Dict, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
from database.models import QtyPromotion


def _round_cur(val: float) -> float:
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def evaluate_promotions(
    session,
    cart_items: List[Dict[str, Any]],
    branch_id: int = None
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Evaluates active qty promotions (bundle prices, buy-N discounts, free items)
    against current cart items.

    cart_items: list of dicts with:
      - 'product_id': int
      - 'qty': float
      - 'unit_price': float
      - 'name': str (optional)

    Returns:
      (total_promo_discount, promo_details)
      where promo_details is a list of:
      {
          'promotion_id': int,
          'code': str,
          'name': str,
          'label': str,
          'promo_type': str,
          'product_id': int,
          'sets': int,
          'discount': float,
      }
    """
    if not cart_items:
        return 0.0, []

    # Aggregate quantities and base unit prices by product_id
    product_totals: Dict[int, Dict[str, Any]] = {}
    for item in cart_items:
        pid = item.get('product_id')
        if not pid:
            continue
        try:
            pid = int(pid)
        except (ValueError, TypeError):
            continue

        qty = float(item.get('qty', 0.0) or 0.0)
        price = float(item.get('unit_price', 0.0) or 0.0)
        name = str(item.get('name', '') or item.get('name_th', '') or '')

        if pid not in product_totals:
            product_totals[pid] = {
                'qty': 0.0,
                'unit_price': price,
                'name': name,
            }
        product_totals[pid]['qty'] += qty
        if price > 0:
            product_totals[pid]['unit_price'] = price

    if not product_totals:
        return 0.0, []

    # Query active promotions for these product_ids
    query = session.query(QtyPromotion).filter(
        QtyPromotion.is_active.is_(True),
        QtyPromotion.product_id.in_(list(product_totals.keys()))
    )
    if branch_id:
        query = query.filter(
            (QtyPromotion.branch_id.is_(None)) | (QtyPromotion.branch_id == branch_id)
        )
    promotions = query.all()

    total_discount = Decimal('0.00')
    promo_details: List[Dict[str, Any]] = []

    for promo in promotions:
        p_data = product_totals.get(promo.product_id)
        if not p_data:
            continue

        min_qty = float(promo.min_qty or 0.0)
        if min_qty <= 0:
            continue

        total_qty = float(p_data['qty'])
        sets = int(total_qty // min_qty)
        if sets <= 0:
            continue

        unit_price = float(p_data['unit_price'] or 0.0)
        promo_discount = Decimal('0.00')
        min_qty_int = int(min_qty) if min_qty.is_integer() else min_qty
        label = promo.name or promo.code or "โปรโมชั่น"

        if promo.promo_type == 'bundle_price':
            # Example: 3 packs for 100 Baht (normal: 3 * 35 = 105 -> discount = 5)
            bundle_price = float(promo.bundle_price or 0.0)
            normal_set_total = Decimal(str(sets)) * Decimal(str(min_qty)) * Decimal(str(unit_price))
            bundle_set_total = Decimal(str(sets)) * Decimal(str(bundle_price))
            diff = normal_set_total - bundle_set_total
            if diff > Decimal('0.00'):
                promo_discount = diff
            if not promo.name:
                label = f"ซื้อ {min_qty_int} ชิ้น {bundle_price:,.0f} บาท"

        elif promo.promo_type == 'discount':
            disc_val = Decimal(str(promo.discount_value or 0.0))
            if promo.discount_type == 'percent':
                normal_set_total = Decimal(str(sets)) * Decimal(str(min_qty)) * Decimal(str(unit_price))
                promo_discount = normal_set_total * (disc_val / Decimal('100.0'))
                if not promo.name:
                    label = f"ซื้อ {min_qty_int} ลด {disc_val:,.0f}%"
            else:
                promo_discount = Decimal(str(sets)) * disc_val
                if not promo.name:
                    label = f"ซื้อ {min_qty_int} ลด {disc_val:,.2f} บาท"

        elif promo.promo_type == 'free_item':
            # Buy min_qty get free_qty of free_product_id
            free_pid = promo.free_product_id or promo.product_id
            free_qty_per_set = float(promo.free_qty or 1.0)
            target_free_qty = float(sets * free_qty_per_set)

            gift_data = product_totals.get(free_pid)
            if gift_data:
                free_qty = min(float(gift_data['qty']), target_free_qty)
                promo_discount = Decimal(str(free_qty)) * Decimal(str(gift_data['unit_price'] or 0.0))
                free_qty_int = int(free_qty_per_set) if free_qty_per_set.is_integer() else free_qty_per_set
                if not promo.name:
                    label = f"ซื้อ {min_qty_int} แถม {free_qty_int}"

        promo_discount = promo_discount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if promo_discount > Decimal('0.00'):
            total_discount += promo_discount
            promo_details.append({
                'promotion_id': promo.id,
                'code': promo.code,
                'name': promo.name,
                'label': label,
                'promo_type': promo.promo_type,
                'product_id': promo.product_id,
                'sets': sets,
                'discount': float(promo_discount),
            })

    return float(total_discount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)), promo_details


def get_active_promotions_for_product(session, product_id: int, branch_id: int = None) -> List[Dict[str, Any]]:
    """Returns active promotion info for a single product to display promo tags/badges."""
    query = session.query(QtyPromotion).filter(
        QtyPromotion.is_active.is_(True),
        QtyPromotion.product_id == product_id
    )
    if branch_id:
        query = query.filter(
            (QtyPromotion.branch_id.is_(None)) | (QtyPromotion.branch_id == branch_id)
        )
    promotions = query.all()
    results = []
    for promo in promotions:
        min_qty_int = int(promo.min_qty) if float(promo.min_qty or 0).is_integer() else promo.min_qty
        if promo.promo_type == 'bundle_price':
            label = promo.name or f"ซื้อ {min_qty_int} ชิ้น {float(promo.bundle_price or 0):,.0f} บาท"
        elif promo.promo_type == 'discount':
            if promo.discount_type == 'percent':
                label = promo.name or f"ซื้อ {min_qty_int} ลด {float(promo.discount_value or 0):,.0f}%"
            else:
                label = promo.name or f"ซื้อ {min_qty_int} ลด {float(promo.discount_value or 0):,.2f} บาท"
        elif promo.promo_type == 'free_item':
            free_qty_int = int(promo.free_qty) if float(promo.free_qty or 0).is_integer() else promo.free_qty
            label = promo.name or f"ซื้อ {min_qty_int} แถม {free_qty_int}"
        else:
            label = promo.name or promo.code or "โปรโมชั่น"

        results.append({
            'id': promo.id,
            'code': promo.code,
            'name': promo.name,
            'label': label,
            'promo_type': promo.promo_type,
            'min_qty': promo.min_qty,
            'bundle_price': promo.bundle_price,
            'discount_value': promo.discount_value,
            'discount_type': promo.discount_type,
        })
    return results
