# GUI 入口：smartoken-gui（PyInstaller 打包入口点也在此）
from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile, QDir
from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow
from .paths import default_config_path
from .style import app_icon, apply_theme


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    app = QApplication(sys.argv[:1] + argv)
    app.setApplicationName("Smartoken")
    apply_theme(app)
    icon = app_icon()
    app.setWindowIcon(icon)

    # 单实例锁
    lock = QLockFile(QDir.tempPath() + "/smartoken-gui.lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, "Smartoken", "控制台已在运行。")
        return 1

    config_path = default_config_path()
    if argv:
        if "--config" in argv:
            i = argv.index("--config")
            if i + 1 < len(argv):
                config_path = argv[i + 1]
        elif not argv[0].startswith("-"):
            config_path = argv[0]

    win = MainWindow(config_path)
    win.setWindowIcon(icon)
    win.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
