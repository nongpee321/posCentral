import os
import sys
import unittest
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for GUI widgets
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from ui.cart_item_edit_dialog import CartItemEditDialog


class TestCartItemEditDialog(unittest.TestCase):
    def test_regular_item_edit(self):
        dlg = CartItemEditDialog(
            product_name="ANATOLI เส้นสปาเก็ตตี้ แพ็ค 500g.",
            current_qty=1.0,
            unit_price=39.0,
            is_scale=False
        )
        self.assertEqual(dlg.qty_spin.value(), 1.0)
        self.assertEqual(dlg.unit_price, 39.0)
        self.assertEqual(dlg.total_lbl.text(), "฿ 39.00")

        # Adjust qty +1
        dlg.adjust_qty(1.0)
        self.assertEqual(dlg.qty_spin.value(), 2.0)
        self.assertEqual(dlg.total_lbl.text(), "฿ 78.00")

        # Save
        dlg.on_save_clicked()
        self.assertEqual(dlg.result_qty, 2.0)
        self.assertFalse(dlg.was_deleted)

    def test_scale_item_edit(self):
        dlg = CartItemEditDialog(
            product_name="**หัวไหล่หมูสด ชั่ง กก [ชั่งน้ำหนัก]",
            current_qty=1.56,
            unit_price=179.0,
            is_scale=True
        )
        self.assertTrue(dlg.is_scale)
        self.assertEqual(dlg.qty_spin.value(), 1.56)
        self.assertEqual(dlg.total_lbl.text(), "฿ 279.24")

        # Adjust qty +0.1
        dlg.adjust_qty(0.1)
        self.assertAlmostEqual(dlg.qty_spin.value(), 1.66, places=3)
        self.assertEqual(dlg.total_lbl.text(), "฿ 297.14")

        # Save
        dlg.on_save_clicked()
        self.assertAlmostEqual(dlg.result_qty, 1.66, places=3)
        self.assertFalse(dlg.was_deleted)

    def test_delete_action(self):
        dlg = CartItemEditDialog(
            product_name="A88 เห็ดหิมะ(ดำ) 150g",
            current_qty=1.0,
            unit_price=20.0
        )
        dlg.on_delete_clicked()
        self.assertTrue(dlg.was_deleted)


if __name__ == '__main__':
    unittest.main()
