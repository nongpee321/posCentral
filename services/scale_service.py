import re
from typing import Optional, Dict, Any
from database.models import ScaleProfile

class ScaleBarcodeParser:
    """
    Parses weighted item barcodes, specifically 13-digit barcodes starting with 800, 801, 02, 20 etc.
    Ensures barcode is always handled strictly as a String to preserve leading zeros.
    """
    
    @staticmethod
    def parse(barcode: str, session) -> Optional[Dict[str, Any]]:
        if not barcode:
            return None
            
        barcode_str = str(barcode).strip()
        if len(barcode_str) != 13:
            return None
            
        # Retrieve active scale profiles
        profiles = session.query(ScaleProfile).filter_by(is_active=True).all()
        for profile in profiles:
            prefix = str(profile.prefix).strip()
            if barcode_str.startswith(prefix):
                # Matched profile
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
                        weight_kg = 1.0
                        
                    price = None
                    if profile.price_len and profile.price_len > 0:
                        price_end = weight_end + profile.price_len
                        if len(barcode_str) >= price_end:
                            try:
                                price_raw = int(barcode_str[weight_end:price_end])
                                price = price_raw / (profile.price_divisor or 100.0)
                            except ValueError:
                                price = None
                                
                    return {
                        'is_scale': True,
                        'profile_name': profile.name,
                        'prefix': prefix,
                        'item_code': item_code,
                        'weight': round(weight_kg, 3),
                        'price': price,
                        'raw_barcode': barcode_str
                    }
                    
        return None
