import os
import sys

from database.models import init_db, Product
db_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'PopCentralPOS', 'pos_offline.db')
session = init_db(f"sqlite:///{db_path}")
product = session.query(Product).first()
session.close()
try:
    print(product.name_th)
    print("Success!")
except Exception as e:
    print("Error:", type(e), e)
