from typing import Optional, Dict, Any
from sqlalchemy import or_
from database.models import ScaleProfile, Product, ProductBarcode


class ScaleBarcodeParser:
    """
    Parses weighted item barcodes (12 or 13 digits starting with 800, 801, 02, 20, etc.).
    Supports both POPSTAR 6-digit PLU + total-price-in-satang labels (800xxx/801xxx)
    and standard weight-in-grams ScaleProfile rules.
    """

    @staticmethod
    def parse(barcode: str, session) -> Optional[Dict[str, Any]]:
        if not barcode:
            return None

        barcode_str = str(barcode).strip()
        if not barcode_str.isdigit() or len(barcode_str) not in (12, 13):
            return None

        # 1. POPSTAR scale barcode rule (800xxx / 801xxx):
        #    6-digit PLU (including 800/801) + 6-digit (13-char) or 5-digit (12-char) total price in satang.
        if barcode_str.startswith(('800', '801')):
            plu6 = barcode_str[:6]
            val_str = barcode_str[6:12] if len(barcode_str) == 13 else barcode_str[6:11]
            if val_str.isdigit() and int(val_str) > 0:
                has_plu6 = (
                    session.query(ProductBarcode.id).filter(ProductBarcode.barcode == plu6).first() is not None
                    or session.query(Product.id).filter(or_(Product.barcode == plu6, Product.sku_code == plu6)).first() is not None
                )
                if has_plu6:
                    total_price = round(int(val_str) / 100.0, 2)
                    return {
                        'is_scale': True,
                        'profile_name': f"POPSTAR-{barcode_str[:3]}",
                        'prefix': barcode_str[:3],
                        'item_code': plu6,
                        'weight': 1.0,
                        'price': total_price,
                        'weight_from_price': True,
                        'raw_barcode': barcode_str,
                    }

        if len(barcode_str) != 13:
            return None

        # 2. Retrieve active scale profiles
        profiles = session.query(ScaleProfile).filter_by(is_active=True).all()
        for profile in profiles:
            prefix = str(profile.prefix).strip()
            if barcode_str.startswith(prefix):
                prefix_len = len(prefix)
                item_code_end = prefix_len + profile.item_code_len
                weight_end = item_code_end + profile.weight_len

                if len(barcode_str) >= weight_end:
                    item_code = barcode_str[prefix_len:item_code_end]
                    weight_raw_str = barcode_str[item_code_end:weight_end]

                    try:
                        weight_raw = int(weight_raw_str)
                        weight_kg = weight_raw / (profile.weight_divisor or 1000.0)
                    except ValueError:
                        continue

                    price = None
                    if profile.price_len and profile.price_len > 0:
                        price_end = weight_end + profile.price_len
                        if len(barcode_str) >= price_end:
                            try:
                                price_raw = int(barcode_str[weight_end:price_end])
                                price = price_raw / (profile.price_divisor or 100.0)
                            except ValueError:
                                price = None

                    # Static product barcodes like 2010740000008 have 00000 in the weight slot;
                    # a real weighed label never has 0 weight and 0 price.
                    if weight_raw <= 0 and not price:
                        continue

                    return {
                        'is_scale': True,
                        'profile_name': profile.name,
                        'prefix': prefix,
                        'item_code': item_code,
                        'weight': round(weight_kg, 3),
                        'price': price,
                        'raw_barcode': barcode_str,
                    }

        return None
