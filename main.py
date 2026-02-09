"""
Entry point for Custom Invoice Export App.
Run: python main.py
Build exe: pyinstaller invoice_export.spec
"""
from app.ui import run_app

if __name__ == "__main__":
    run_app()
