# GUI 离屏冒烟：构建主窗口 → 主页截图 → 用量看板页截图 → 退出（CI/无头验证用）
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from smartoken_gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    app = QApplication(sys.argv)
    win = MainWindow(config_path)
    win.show()

    def snap():
        ok1 = win.grab().save(os.path.join(out_dir, "gui-main.png"))
        tabs = win.centralWidget().findChild(QTabWidget)
        dash = tabs.widget(2)
        tabs.setCurrentIndex(2)
        ok2 = dash.grab().save(os.path.join(out_dir, "gui-dashboard.png"))
        print(f"main_shot={'OK' if ok1 else 'FAIL'} dash_shot={'OK' if ok2 else 'FAIL'}", flush=True)
        print(f"strategy={win.strategy_combo.currentData()} models={win.model_table.rowCount()} "
              f"base_url={win.api_base.text()}", flush=True)
        print(f"dashboard_alive={dash is not None}", flush=True)
        app.quit()

    QTimer.singleShot(1000, snap)
    code = app.exec()
    return 0 if code == 0 else code


if __name__ == "__main__":
    raise SystemExit(main())
