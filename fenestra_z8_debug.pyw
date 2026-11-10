"""Launch the Z8 desktop debugger. Camera access only when a visible workbench Connect operation is requested."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'host'))

if __name__ == '__main__':
    try:
        from z8_debug_gui import main
        main()
    except Exception:
        import traceback
        report = traceback.format_exc()
        destination = ROOT / 'build/debug-ui/startup-error.log'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(report, encoding='utf-8')
        import tkinter as tk
        from tkinter import messagebox
        window = tk.Tk()
        window.withdraw()
        messagebox.showerror('Z8 调试工作台启动失败', '详情已保存到：\n' + str(destination), parent=window)
        window.destroy()
