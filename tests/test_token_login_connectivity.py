import requests
from PySide6.QtWidgets import QMessageBox

import ui.token_dialog as token_dialog_module
from PySide6.QtWidgets import QInputDialog
from ui.token_dialog import PosTokenLoginDialog


def test_login_dialog_warns_when_api_url_targets_this_computer(qtbot):
    dialog = PosTokenLoginDialog(
        api_url="http://localhost:8000",
        default_token="device-token",
        default_username="cashier01",
    )
    qtbot.addWidget(dialog)

    assert "localhost (เครื่องนี้)" in dialog.status_lbl.text()


def test_login_dialog_can_update_and_save_erp_url_after_closing(qtbot, monkeypatch):
    dialog = PosTokenLoginDialog(
        api_url="http://localhost:8000",
        default_token="device-token",
        default_username="cashier01",
    )
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("https://erp.example.com", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    dialog.configure_server()

    assert dialog.api_url == "https://erp.example.com"
    assert "ERP Server: https://erp.example.com" == dialog.status_lbl.text()


def test_login_dialog_rejects_insecure_remote_erp_url(qtbot, monkeypatch):
    dialog = PosTokenLoginDialog(
        api_url="http://localhost:8000",
        default_token="device-token",
        default_username="cashier01",
    )
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("http://erp.example.com", True))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    dialog.configure_server()

    assert dialog.api_url == "http://localhost:8000"
    assert "https://" in warnings[0]


def test_login_uses_longer_server_timeout_and_reports_erp_timeout(qtbot, monkeypatch):
    dialog = PosTokenLoginDialog(
        api_url="https://erp.example",
        default_token="device-token",
        default_username="cashier01",
    )
    qtbot.addWidget(dialog)
    dialog.pin_input.setText("1234")

    class PingResponse:
        status_code = 200

        def json(self):
            return {
                "branch_id": 6,
                "branch_name": "Test",
                "device": {"id": 10},
            }

    monkeypatch.setattr(token_dialog_module.requests, "get", lambda *args, **kwargs: PingResponse())
    post_calls = []

    def timeout_post(*args, **kwargs):
        post_calls.append(kwargs)
        raise requests.Timeout("ERP response timed out")

    monkeypatch.setattr(token_dialog_module.requests, "post", timeout_post)
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args[2]),
    )

    dialog.do_verify_and_login()

    assert post_calls[0]["timeout"] == (5, 20)
    assert "ติดต่อ ERP ไม่สำเร็จ (Timeout)" in dialog.status_lbl.text()
    assert "ERP" in warnings[0]
    assert dialog.is_offline_login is False


def test_unexpected_response_error_does_not_enter_offline_login(qtbot, monkeypatch):
    dialog = PosTokenLoginDialog(
        api_url="https://erp.example",
        default_token="device-token",
        default_username="cashier01",
    )
    qtbot.addWidget(dialog)
    dialog.pin_input.setText("1234")

    class InvalidResponse:
        status_code = 200

        def json(self):
            raise ValueError("invalid response")

    monkeypatch.setattr(token_dialog_module.requests, "get", lambda *args, **kwargs: InvalidResponse())
    criticals = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: criticals.append(args[2]),
    )

    dialog.do_verify_and_login()

    assert "ValueError" in dialog.status_lbl.text()
    assert "ไม่ได้เปลี่ยนเป็นโหมดออฟไลน์" in criticals[0]
    assert dialog.is_offline_login is False
