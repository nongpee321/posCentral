import sys
from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": ["os", "sys", "pathlib", "sqlite3", "uuid", "json", "datetime", "PySide6", "sqlalchemy", "requests", "dotenv"],
    "excludes": ["tkinter", "unittest"],
    "include_files": ["assets/"],
    "include_msvcr": True
}

# base="gui" should be used only for Windows GUI app
# Temporarily using console for debugging
base = None

setup(
    name="PopCentralPOS",
    version="1.0",
    description="PopCentral POS Offline Mode",
    options={"build_exe": build_exe_options},
    executables=[Executable("main.py", base=base, target_name="PopCentralPOS.exe", icon="assets/icon.ico")]
)
