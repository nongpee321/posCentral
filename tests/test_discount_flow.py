import pytest
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt
from ui.discount_dialog import DiscountDialog
from ui.customer_display import CustomerDisplayWindow
from database.models import init_db, Sale, Outbox, Product

app = QApplication.instance() or QApplication([])

def test_discount_dialog_touch_keypad_and_presets(qtbot):
    dialog = DiscountDialog(subtotal=650.0, current_discount=0.0)
    qtbot.addWidget(dialog)

    # Test quick preset 50
    dialog.apply_preset("50")
    assert dialog.val_input.text() == "50"
    dialog.recalc()
    assert "-฿50.00" in dialog.preview_disc_lbl.text()
    assert "฿600.00" in dialog.preview_net_lbl.text()

    # Test touch keypad append
    dialog.clear_keypad()
    dialog.append_keypad("1")
    dialog.append_keypad("0")
    dialog.append_keypad("0")
    assert dialog.val_input.text() == "100"
    dialog.recalc()
    assert "-฿100.00" in dialog.preview_disc_lbl.text()
    assert "฿550.00" in dialog.preview_net_lbl.text()

    # Test backspace
    dialog.backspace_keypad()
    assert dialog.val_input.text() == "10"

    # Test percentage mode
    dialog.radio_pct.setChecked(True)
    dialog.on_mode_changed(2)
    dialog.apply_preset("10")
    dialog.recalc()
    assert "-฿65.00 (10%)" in dialog.preview_disc_lbl.text()
    assert "฿585.00" in dialog.preview_net_lbl.text()

    # Confirm
    dialog.on_confirm()
    assert dialog.discount_amount == 65.0
    assert dialog.discount_label == "10%"

def test_customer_display_discount_rendering(qtbot):
    cd = CustomerDisplayWindow()
    qtbot.addWidget(cd)

    # Mock table with 1 item
    tbl = QTableWidget(1, 4)
    tbl.setItem(0, 0, QTableWidgetItem("Cargill 10kg"))
    tbl.setItem(0, 1, QTableWidgetItem("1"))
    tbl.setItem(0, 2, QTableWidgetItem("650.00"))
    tbl.setItem(0, 3, QTableWidgetItem("650.00"))

    # When discount of 50 is applied, total is 600
    cd.update_cart(tbl, total_amount=600.0, subtotal=650.0, discount=50.0)

    assert cd.total_lbl.text() == "600.00"
    assert cd.disc_lbl.text() == "50.00 ฿"
    assert "560.75 ฿" in cd.subtotal_lbl.text()
    assert "39.25 ฿" in cd.vat_lbl.text()

    # Test show_payment accepts float directly
    cd.show_payment(600.0)
    assert not cd.qr_box.isHidden()
    assert cd.spacer_widget.isHidden() is True

    # Test show_success clears discount
    cd.show_success(change=0.0)
    assert cd.disc_lbl.text() == "0.00 ฿"
    assert cd.total_lbl.text() == "0.00"

def test_sale_model_persists_discount(tmp_path):
    db_path = str(tmp_path / "sale_disc.db")
    session = init_db(f"sqlite:///{db_path}")

    sale = Sale(
        local_sale_id="test-sale-1",
        doc_number="003401000001",
        branch_id=34,
        total_amount=600.0,
        received_amount=600.0,
        discount_amount=50.0,
        payment_method="transfer",
        idempotency_key="offline-receipt-test-sale-1"
    )
    session.add(sale)
    session.commit()

    loaded = session.query(Sale).filter_by(local_sale_id="test-sale-1").first()
    assert loaded is not None
    assert loaded.total_amount == 600.0
    assert loaded.discount_amount == 50.0
    session.close()

def test_payment_dialog_discount_support(qtbot):
    from ui.payment_dialog import PaymentDialog
    dlg = PaymentDialog(total_amount=650.0, total_items=1, total_qty=1.0, discount_amount=0.0)
    qtbot.addWidget(dlg)

    assert dlg.total_amount == 650.0
    assert dlg.subtotal == 650.0
    assert dlg.btn_discount_dialog is not None

    # Apply 50 baht discount directly
    dlg.discount_amount = 50.0
    dlg.total_amount = 600.0
    dlg.update_summary_card()

    assert dlg.total_amount == 600.0
    assert "600.00" in dlg.total_lbl.text()

def test_customer_display_show_payment_updates_discount_and_total(qtbot):
    cd = CustomerDisplayWindow()
    qtbot.addWidget(cd)

    cd.show_payment("QR", override_amount=595.0, discount=55.0)
    assert cd.total_lbl.text() == "595.00"
    assert cd.disc_lbl.text() == "55.00 ฿"
    assert "556.07 ฿" in cd.subtotal_lbl.text()
    assert "38.93 ฿" in cd.vat_lbl.text()
    assert not cd.qr_box.isHidden()

