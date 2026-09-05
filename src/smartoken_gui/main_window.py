# 主窗口：服务启停 / API 信息与 key 生成 / 模型与策略（合并页，含行级启用·测试·灯）/ 用量看板
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from smartoken.config import load_config

from . import configfile
from .api_tokens import KEY_ENV, get_current_key, rotate_key
from .backend_test import probe_backend
from .daemon import DaemonThread
from .paths import DEV_ENV_PATH, default_config_path, get_env_value, set_env_value

ROLES = ["auto", "coding", "talking", "general", "vision"]

GREEN = "#34d399"
YELLOW = "#fbbf24"
RED = "#f87171"
GRAY = "#64748b"


class ProbeWorker(QThread):
    """后台批量探测，避免阻塞 UI。"""
    done = Signal(dict)

    def __init__(self, config_path: str, parent=None):
        super().__init__(parent)
        self.config_path = config_path

    def run(self) -> None:
        from smartoken.config import load_config
        out: dict[str, tuple[bool, int]] = {}
        try:
            cfg = load_config(self.config_path)
            for b in cfg.backends:
                out[b.id] = probe_backend(b)
        except Exception:
            pass
        self.done.emit(out)


class MainWindow(QMainWindow):
    def __init__(self, config_path: str | None = None):
        super().__init__()
        self.config_path = config_path or default_config_path()
        self.daemon: DaemonThread | None = None
        self._restart_pending = False
        self._model_rows: list[dict] = []
        self._probe_results: dict[str, tuple[bool, int]] = {}
        self.setWindowTitle("Smartoken 控制台 · v0.1")
        self.resize(1040, 700)
        self._build_ui()
        self._refresh_all()

    # ================= UI =================
    def _mk_btn(self, text: str, kind: str | None = None) -> QPushButton:
        b = QPushButton(text)
        if kind:
            b.setProperty("btnType", kind)
            b.style().unpolish(b)
            b.style().polish(b)
        return b

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        # 头部：应用名 + 状态胶囊 + 服务按钮
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        app_title = QLabel("Smartoken")
        app_title.setObjectName("appTitle")
        app_sub = QLabel("本地任务感知 · 模型智能路由 · 省钱引擎 · v0.1")
        app_sub.setObjectName("appSub")
        title_col.addWidget(app_title)
        title_col.addWidget(app_sub)
        header.addLayout(title_col)
        header.addStretch(1)

        chip = QFrame()
        chip.setObjectName("statusChip")
        ch = QHBoxLayout(chip)
        ch.setContentsMargins(12, 4, 12, 4)
        ch.setSpacing(8)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setProperty("darkDot", True)
        self.status_label = QLabel("未运行")
        ch.addWidget(self.status_dot)
        ch.addWidget(self.status_label)
        header.addWidget(chip)
        header.addSpacing(12)
        self.btn_start = self._mk_btn("启动服务", "primary")
        self.btn_stop = self._mk_btn("停止服务", "danger")
        self.btn_stop.setEnabled(False)
        self.btn_restart = QPushButton("重启")
        self.btn_restart.setEnabled(False)
        header.addWidget(self.btn_start)
        header.addWidget(self.btn_stop)
        header.addWidget(self.btn_restart)
        root.addLayout(header)

        self.base_url_label = QLabel("base_url: -")          # 随状态刷新显示的地址行
        self.base_url_label.setObjectName("appSub")
        root.addWidget(self.base_url_label)

        tabs = QTabWidget()
        tabs.addTab(self._tab_service(), "① 服务 / API 接入")
        tabs.addTab(self._tab_models(), "② 模型与策略")
        tabs.addTab(self._tab_dashboard(), "③ 用量看板")
        root.addWidget(tabs, 1)
        self.setCentralWidget(central)

        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_restart.clicked.connect(self._restart)

    def _set_dot(self, color: str) -> None:
        glow = QColor(color)
        glow.setAlpha(90)
        self.status_dot.setStyleSheet(
            f"background:{color};border-radius:5px;border:1px solid rgba({glow.red()},{glow.green()},{glow.blue()},0.8);"
        )

    # ---------- ① 服务 / API ----------
    def _tab_service(self) -> QWidget:
        w = QWidget()
        w.setObjectName("page")
        v = QVBoxLayout(w)

        g = QGroupBox("给 agent 填的接入信息")
        f = QFormLayout(g)
        self.api_base = QLineEdit("-")
        self.api_base.setReadOnly(True)
        f.addRow("base_url", self.api_base)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setReadOnly(True)
        f.addRow("API Key", self.api_key)
        h = QHBoxLayout()
        btn_copy = QPushButton("复制 Key")
        btn_gen = QPushButton("生成/轮换 Key")
        h.addWidget(btn_copy)
        h.addWidget(btn_gen)
        f.addRow("", h)
        self.key_tip = QLabel("")
        self.key_tip.setWordWrap(True)
        f.addRow("", self.key_tip)
        v.addWidget(g)

        h2 = QGroupBox("agent 使用说明")
        lbl = QLabel(
            "任意 OpenAI 兼容 agent：\n"
            "  base_url = 上方地址\n"
            "  API Key  = 上方 Key（未设置=本机直开）\n"
            "  模型     = smartoken-auto（虚拟路由模型）或直接选真实模型名则直通"
        )
        lbl.setWordWrap(True)
        v2 = QVBoxLayout(h2)
        v2.addWidget(lbl)
        v.addWidget(h2)
        v.addStretch(1)

        btn_copy.clicked.connect(self._copy_key)
        btn_gen.clicked.connect(self._gen_key)
        return w

    # ---------- ② 模型与策略（合并页） ----------
    def _tab_models(self) -> QWidget:
        w = QWidget()
        w.setObjectName("page")
        v = QVBoxLayout(w)

        # 顶部：策略选择
        bar = QHBoxLayout()
        bar.addWidget(QLabel("策略选择"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem("auto：全自动智能路由", "auto")
        self.strategy_combo.addItem("自定义：按每行角色分派", "custom")
        bar.addWidget(self.strategy_combo)
        self.strategy_hint = QLabel("")
        self.strategy_hint.setWordWrap(True)
        bar.addWidget(self.strategy_hint, 1)
        btn_apply = QPushButton("应用策略")
        bar.addWidget(btn_apply)
        v.addLayout(bar)

        self.model_table = QTableWidget(0, 8)
        self.model_table.setHorizontalHeaderLabels(
            ["启用", "模型", "档位 kind", "默认模型", "能力", "策略角色", "状态", "操作"])
        self.model_table.horizontalHeader().setStretchLastSection(True)
        self.model_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.model_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.model_table.setAlternatingRowColors(True)
        self.model_table.verticalHeader().setVisible(False)
        self.model_table.verticalHeader().setDefaultSectionSize(34)
        v.addWidget(self.model_table, 1)

        act = QHBoxLayout()
        btn_add = self._mk_btn("＋ 新建模型", "primary")
        btn_del = self._mk_btn("－ 删除选中", "danger")
        btn_refresh = QPushButton("刷新列表")
        btn_probe_all = QPushButton("探测全部状态")
        act.addWidget(btn_add)
        act.addWidget(btn_del)
        act.addWidget(btn_refresh)
        act.addWidget(btn_probe_all)
        act.addStretch(1)
        v.addLayout(act)

        # 选中行的密钥编辑（compact）
        g = QGroupBox("选中行：密钥")
        gf = QFormLayout(g)
        self.k_id = QLabel("-")
        gf.addRow("模型", self.k_id)
        self.k_env = QLabel("-")
        gf.addRow("Key 变量", self.k_env)
        self.k_val = QLineEdit()
        self.k_val.setEchoMode(QLineEdit.EchoMode.Password)
        gf.addRow("Key 值", self.k_val)
        b_save = QPushButton("保存密钥")
        gf.addRow("", b_save)
        v.addWidget(g)

        self.strategy_combo.currentIndexChanged.connect(self._render_role_column)
        btn_apply.clicked.connect(self._apply_strategy)
        self.model_table.itemSelectionChanged.connect(self._on_model_selected)
        b_save.clicked.connect(self._save_row_key)
        btn_add.clicked.connect(self._add_model)
        btn_del.clicked.connect(self._del_model)
        btn_refresh.clicked.connect(self._refresh_models)
        btn_probe_all.clicked.connect(self._probe_all)
        return w

    def _role_options(self) -> list[str]:
        return ROLES

    # ---------- ③ 用量看板 ----------
    def _tab_dashboard(self) -> QWidget:
        from .dashboard import DashboardPage
        return DashboardPage(self._data_dir)

    def _data_dir(self) -> str:
        try:
            return load_config(self.config_path).data_dir
        except Exception:
            return os.path.abspath(os.path.join(os.path.dirname(self.config_path), "data"))

    # ================= 数据 =================
    def _refresh_all(self) -> None:
        self._refresh_api_info()
        self._refresh_models()
        self._refresh_strategy()

    def _refresh_api_info(self) -> None:
        try:
            cfg = load_config(self.config_path)
            host = cfg.server_host
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            url = f"http://{host}:{cfg.server_port}/v1"
        except Exception:
            url = "-"
        self.api_base.setText(url)
        key = get_current_key(DEV_ENV_PATH)
        self.api_key.setText(key or "")
        if key:
            self.key_tip.setText(f"Key 已设置: {key[:12]}…（.env 的 {KEY_ENV}；轮换后重启服务生效）")
        else:
            self.key_tip.setText("未设置 Key = 本机直开。点『生成/轮换 Key』后重启服务生效。")

    # ---- 模型与策略 ----
    def _refresh_strategy(self) -> None:
        mode = configfile.get_strategy_mode(self.config_path)
        idx = self.strategy_combo.findData(mode)
        if idx >= 0:
            self.strategy_combo.setCurrentIndex(idx)
        self._strategy_hint()

    def _strategy_hint(self) -> None:
        mode = self.strategy_combo.currentData()
        if mode == "auto":
            self.strategy_hint.setText("auto：忽略每行角色，按 难度×场景 全局智能路由。")
        else:
            self.strategy_hint.setText("自定义：每行『策略角色』决定该模型参与哪类任务（auto=全场景）。")

    def _render_role_column(self) -> None:
        mode = self.strategy_combo.currentData()
        self._strategy_hint()
        table = self.model_table
        for i, b in enumerate(self._model_rows):
            cell = QComboBox()
            for role in self._role_options():
                cell.addItem(role, role)
            role = str(b.get("role") or "auto").lower()
            if role not in ROLES:
                role = "auto"
            cell.setCurrentText(role)
            cell.setEnabled(mode == "custom")
            cell.currentIndexChanged.connect(lambda _ix, idx=i: self._on_role_changed(idx))
            table.setCellWidget(i, 5, cell)

    def _on_role_changed(self, row: int) -> None:
        b = self._model_rows[row]
        cb = self.model_table.cellWidget(row, 5)
        configfile.set_backend_role(self.config_path, b["id"], cb.currentData())
        self._tip_status(f"角色已写入 {b['id']}；服务运行中需重启生效")

    def _apply_strategy(self) -> None:
        configfile.set_strategy_mode(self.config_path, self.strategy_combo.currentData())
        self._render_role_column()
        self._tip_status(f"策略模式已设为 {self.strategy_combo.currentData()}；服务运行中需重启生效")

    def _tip_status(self, msg: str) -> None:
        self.base_url_label.setText(msg)

    def _refresh_models(self) -> None:
        self._model_rows = configfile.list_backends(self.config_path)
        table = self.model_table
        table.setRowCount(len(self._model_rows))
        for i, b in enumerate(self._model_rows):
            # 列0：启用勾选（前一版行为保留）
            chk = QCheckBox()
            chk.setChecked(bool(b.get("enabled", False)))
            chk.stateChanged.connect(lambda _st, idx=i: self._on_enable_check(idx))
            table.setCellWidget(i, 0, chk)
            # 列1-4：基础信息
            for j, key in enumerate(["id", "kind", "default_model", "capabilities"], start=1):
                val = b.get(key)
                if isinstance(val, list):
                    val = ",".join(val)
                item = QTableWidgetItem(str(val or "-"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(i, j, item)
            self._set_light(i, b, force_gray=True)
            self._set_action_buttons(i, b)
        self._render_role_column()
        table.resizeColumnsToContents()
        table.setColumnWidth(0, 46)
        table.setColumnWidth(1, 150)
        table.setColumnWidth(5, 110)
        table.setColumnWidth(6, 74)
        table.setColumnWidth(7, 210)

    def _on_enable_check(self, row: int) -> None:
        """左侧勾选 = 启用/停用（与行内按钮联动）。"""
        b = self._model_rows[row]
        chk = self.model_table.cellWidget(row, 0)
        enabled = bool(chk.isChecked())
        b["enabled"] = enabled
        configfile.set_backend_enabled(self.config_path, b["id"], enabled)
        self._tip_status(f"{b['id']} 已{'启用' if enabled else '停用'}；服务运行中需重启生效")
        self._probe_results.pop(b["id"], None)
        self._sync_row_state(row, enabled)

    def _sync_row_state(self, row: int, enabled: bool) -> None:
        """勾选框/灯/按钮三方同步。"""
        b = self._model_rows[row]
        chk = self.model_table.cellWidget(row, 0)
        if chk and chk.isChecked() != enabled:
            chk.blockSignals(True)
            chk.setChecked(enabled)
            chk.blockSignals(False)
        self._set_light(row, b)
        self._set_action_buttons(row, b)

    def _set_light(self, row: int, b: dict, force_gray: bool = False) -> None:
        color = GRAY
        tip = "未探测"
        enabled = bool(b.get("enabled", False))
        if not enabled:
            color, tip = RED, "停用"
        else:
            res = self._probe_results.get(b["id"])
            if res is not None:
                ok, ms = res
                if ok:
                    color, tip = GREEN, f"启用·正常 ({ms}ms)"
                else:
                    color, tip = YELLOW, "启用·异常"
            elif force_gray:
                color, tip = GRAY, "启用·未测(点 测试)"
            else:
                color, tip = GRAY, "启用·未测"
        light = QLabel("●")
        light.setStyleSheet(f"color:{color}; font-size:15px;")
        light.setToolTip(tip)
        self.model_table.setCellWidget(row, 6, light)

    def _set_action_buttons(self, row: int, b: dict) -> None:
        cell = QWidget()
        h = QHBoxLayout(cell)
        h.setContentsMargins(2, 0, 2, 0)
        enabled = bool(b.get("enabled", False))
        b_on = QPushButton("启用")
        b_off = QPushButton("停用")
        b_t = QPushButton("测试")
        b_on.setEnabled(not enabled)
        b_off.setEnabled(enabled)
        for bb in (b_on, b_off, b_t):
            bb.setFixedWidth(52)
        b_on.clicked.connect(lambda _=False, idx=row: self._set_row_enabled(idx, True))
        b_off.clicked.connect(lambda _=False, idx=row: self._set_row_enabled(idx, False))
        b_t.clicked.connect(lambda _=False, idx=row: self._test_row(idx))
        h.addWidget(b_on)
        h.addWidget(b_off)
        h.addWidget(b_t)
        h.addStretch(1)
        self.model_table.setCellWidget(row, 7, cell)

    def _set_row_enabled(self, row: int, enabled: bool) -> None:
        b = self._model_rows[row]
        b["enabled"] = enabled
        configfile.set_backend_enabled(self.config_path, b["id"], enabled)
        self._tip_status(f"{b['id']} 已{'启用' if enabled else '停用'}；服务运行中需重启生效")
        self._probe_results.pop(b["id"], None)
        self._sync_row_state(row, enabled)

    def _test_row(self, row: int) -> None:
        b = self._model_rows[row]
        from smartoken.config import Backend, load_config
        cfg = load_config(self.config_path)
        backend = cfg.backend(b["id"])
        if backend is None:
            return
        ok, ms = probe_backend(backend)
        self._probe_results[b["id"]] = (ok, ms)
        self._set_light(row, b)
        self._tip_status(f"{b['id']} 探测: {'正常' if ok else '不可达'} ({ms}ms)")

    def _probe_all(self) -> None:
        self._tip_status("正在探测全部后端…")
        self._probe_worker = ProbeWorker(self.config_path)
        self._probe_worker.done.connect(self._on_probe_all_done)
        self._probe_worker.start()

    def _on_probe_all_done(self, results: dict) -> None:
        self._probe_results = results or {}
        self._refresh_models()
        self._tip_status("探测完成")

    def _on_model_selected(self) -> None:
        row = self.model_table.currentRow()
        if row < 0 or row >= len(self._model_rows):
            return
        b = self._model_rows[row]
        env = b.get("api_key_env") or ""
        self.k_id.setText(b.get("id", "-"))
        self.k_env.setText(env or "（无密钥字段）")
        self.k_val.setEnabled(bool(env))
        if env:
            self.k_val.setText(get_env_value(DEV_ENV_PATH, env) or "")
        else:
            self.k_val.setText("")
        self._k_env = env

    def _save_row_key(self) -> None:
        env = getattr(self, "_k_env", "")
        if not env:
            QMessageBox.information(self, "提示", "该模型没有 API Key 字段")
            return
        set_env_value(DEV_ENV_PATH, env, self.k_val.text().strip())
        self._tip_status(f"密钥已写入 .env（{env}）；服务运行中需重启生效")

    # ---- 新建 / 删除 ----
    def _add_model(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("新建模型接入")
        f = QFormLayout(dlg)
        e_id = QLineEdit(); e_kind = QComboBox(); e_type = QComboBox()
        e_url = QLineEdit(); e_model = QLineEdit(); e_env = QLineEdit()
        for k, name in (("local", "local(本地/免费)"), ("cloud-free", "cloud-free(低价/订阅)"),
                        ("cloud", "cloud(付费云端)")):
            e_kind.addItem(name, k)
        e_type.addItem("openai_compatible（OpenAI 兼容）", "openai_compatible")
        e_type.addItem("ollama（Ollama）", "ollama")
        e_url.setPlaceholderText("如 http://127.0.0.1:11434 或 https://api.deepseek.com/v1")
        e_model.setPlaceholderText("如 deepseek-chat（留空=按类别启发式）")
        e_env.setPlaceholderText("如 SMARTOKEN_DEEPSEEK_KEY（云端必填）")
        f.addRow("ID", e_id)
        f.addRow("档位", e_kind)
        f.addRow("类型", e_type)
        f.addRow("base_url", e_url)
        f.addRow("默认模型", e_model)
        f.addRow("Key 环境变量", e_env)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        f.addRow(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        bid = e_id.text().strip()
        if not bid or not e_url.text().strip():
            QMessageBox.warning(self, "缺字段", "ID 与 base_url 必填")
            return
        try:
            configfile.add_backend(self.config_path, {
                "id": bid, "kind": e_kind.currentData(), "type": e_type.currentData(),
                "base_url": e_url.text().strip(), "default_model": e_model.text().strip(),
                "api_key_env": e_env.text().strip() or None,
            })
        except ValueError as exc:
            QMessageBox.warning(self, "无法新增", str(exc))
            return
        self._refresh_models()
        self._tip_status(f"已新增 {bid}；服务运行中需重启生效")

    def _del_model(self) -> None:
        row = self.model_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "先选中要删除的行")
            return
        b = self._model_rows[row]
        ret = QMessageBox.question(self, "删除模型", f"确定删除 {b['id']}？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        configfile.remove_backend(self.config_path, b["id"])
        self._refresh_models()

    # ================= 服务启停 =================
    def _start(self) -> None:
        if self.daemon and self.daemon.isRunning():
            return
        self.status_label.setText("启动中…")
        self.btn_start.setEnabled(False)
        thread = DaemonThread(self.config_path)
        thread.started.connect(self._on_started)
        thread.failed.connect(self._on_failed)
        thread.stopped.connect(self._on_stopped)
        self.daemon = thread
        thread.start()

    def _on_started(self, addr: str) -> None:
        self._set_dot(GREEN)
        self.status_label.setStyleSheet(f"color:{GREEN}; font-weight:600;")
        self.status_label.setText("运行中")
        self.base_url_label.setText(f"监听: {addr}/v1 · 模型 auto / uncensored-27b / deepseek-chat / glm-4.5")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_restart.setEnabled(True)
        self._refresh_api_info()

    def _on_failed(self, msg: str) -> None:
        self._set_dot(RED)
        self.status_label.setStyleSheet(f"color:{RED}; font-weight:600;")
        self.status_label.setText("启动失败")
        QMessageBox.critical(self, "启动失败", str(msg))
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_restart.setEnabled(False)

    def _on_stopped(self, _why: str) -> None:
        self._set_dot(GRAY)
        self.status_label.setStyleSheet("color:#8fa5cc;")
        self.status_label.setText("未运行")
        self.base_url_label.setText("base_url: -")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_restart.setEnabled(False)
        if self._restart_pending:
            self._restart_pending = False
            self._start()

    def _stop(self) -> None:
        if self.daemon and self.daemon.isRunning():
            self.daemon.stop_server()

    def _restart(self) -> None:
        if self.daemon and self.daemon.isRunning():
            self._restart_pending = True
            self.daemon.stop_server()
        else:
            self._start()

    # ================= misc =================
    def _copy_key(self) -> None:
        key = self.api_key.text()
        if key:
            QGuiApplication.clipboard().setText(key)
            self.key_tip.setText("Key 已复制到剪贴板")

    def _gen_key(self) -> None:
        ret = QMessageBox.question(
            self, "轮换接入 Key",
            "将生成新 Key 并写入 .env。正在连接的 agent 需更新；请重启服务。继续？",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        token = rotate_key(DEV_ENV_PATH)
        self.api_key.setText(token)
        self.key_tip.setText(f"新 Key 已生成（仅本次明文展示）: {token}")
        QGuiApplication.clipboard().setText(token)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.daemon and self.daemon.isRunning():
            ret = QMessageBox.question(
                self, "服务仍在运行",
                "daemon 仍在运行，退出后它将停止。确定退出？",
            )
            if ret != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.daemon.stop_server()
        event.accept()
