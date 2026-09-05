# 用量看板页：实时（live.json）+ 历史区间（audit 聚合 + 柱状图）
from __future__ import annotations

from datetime import date

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis,
)
from PySide6.QtCore import QMargins, QTimer, Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .metrics import aggregate, last_n_days, read_live

RANGES = {
    "今天": (1, "今天"),
    "近 3 天": (3, "近 3 天"),
    "近 7 天": (7, "近 7 天（默认留存）"),
    "近 30 天": (30, "近 30 天"),
}

TILE_COLORS = ["#38bdf8", "#818cf8", "#34d399", "#fbbf24"]


def _money(v: float) -> str:
    return f"${v:,.4f}" if abs(v) < 0.01 else f"${v:,.2f}"


class DashboardPage(QWidget):
    def __init__(self, data_dir_provider, parent=None):
        """data_dir_provider: () -> str 每次取最新 data_dir（配置可能变化）。"""
        super().__init__(parent)
        self.setObjectName("page")
        self._data_dir = data_dir_provider
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)              # 每 2 秒自动刷新实时区
        self._timer.timeout.connect(self._refresh_live)
        self._timer.start()

    # ---- UI ----
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # 今日数字瓷砖
        tiles = QHBoxLayout()
        self._tile_nums: list[QLabel] = []
        for cap, color in zip(
            ("今日请求", "今日输出 tokens", "今日花费", "今日节省"),
            TILE_COLORS,
        ):
            frame = QFrame()
            frame.setProperty("tile", "1")
            tv = QVBoxLayout(frame)
            tv.setContentsMargins(14, 10, 14, 10)
            tv.setSpacing(2)
            cap_lbl = QLabel(cap)
            cap_lbl.setProperty("tileCap", "1")
            num = QLabel("0")
            num.setProperty("tileNum", "1")
            num.setStyleSheet(f"color:{color};")
            tv.addWidget(cap_lbl)
            tv.addWidget(num)
            self._tile_nums.append(num)
            tiles.addWidget(frame, 1)
        root.addLayout(tiles)

        # 实时块（单行紧凑：数据 + 右侧刷新控制）
        g_live = QGroupBox("实时数据")
        lv = QHBoxLayout(g_live)
        lv.setContentsMargins(12, 6, 12, 6)
        lv.setSpacing(10)
        self.live_cur = QLabel("— 当前无请求 —")
        self.live_last = QLabel("最近完成：-")
        for lbl in (self.live_cur, self.live_last):
            lbl.setWordWrap(False)
        sep = QLabel("｜")
        sep.setStyleSheet("color:#3b4d75;")
        lv.addWidget(self.live_cur, 5)
        lv.addWidget(sep)
        lv.addWidget(self.live_last, 6)
        lv.addStretch(1)
        auto_hint = QLabel("每 2 秒自动刷新")
        auto_hint.setProperty("role", "hint")
        lv.addWidget(auto_hint)
        self.btn_refresh_live = QPushButton("刷新")
        self.btn_refresh_live.setProperty("btnType", "primary")
        self.btn_refresh_live.setFixedWidth(74)
        self.btn_refresh_live.clicked.connect(self._refresh_live)
        lv.addWidget(self.btn_refresh_live)
        root.addWidget(g_live)

        # 历史块
        g_hist = QGroupBox("历史用量（按审计记录）")
        hv = QVBoxLayout(g_hist)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("范围"))
        self.range_combo = QComboBox()
        for label, (days, _tip) in RANGES.items():
            self.range_combo.addItem(label, days)
        self.range_combo.setCurrentIndex(2)  # 近7天
        bar.addWidget(self.range_combo)
        self.btn_refresh = QPushButton("刷新")
        bar.addWidget(self.btn_refresh)
        bar.addStretch(1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        bar.addWidget(self.summary, 1)
        hv.addLayout(bar)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["模型", "请求", "输入 tokens", "输出 tokens", "平均 t/s", "平均首字(ms)", "花费", "节省"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hv.addWidget(self.table, 1)

        # 按天 tokens 柱状图（显式深色画布，融入面板）
        self.chart = QChart()
        self.chart.setTitle("每天 tokens（近区间）")
        self.chart.setTheme(QChart.ChartTheme.ChartThemeDark)
        self.chart.setBackgroundBrush(QColor("#0e1730"))      # 显式深色画布
        self.chart.setBackgroundVisible(True)
        self.chart.setPlotAreaBackgroundVisible(False)
        self.chart.setMargins(QMargins(6, 6, 6, 6))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setStyleSheet("background: transparent; border: 1px solid #27365c; border-radius: 10px;")
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(200)
        hv.addWidget(self.chart_view)

        root.addWidget(g_hist, 1)
        self.range_combo.currentIndexChanged.connect(self._refresh_history)
        self.btn_refresh.clicked.connect(self._refresh_history)

    # ---- 刷新 ----
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_live()
        self._refresh_history()

    def _refresh_today_tiles(self) -> None:
        from datetime import date as _date
        try:
            agg = aggregate(self._data_dir(), _date.today(), _date.today())
        except Exception:
            agg = {"totals": {"requests": 0, "completion_tokens": 0, "cost_usd": 0.0, "saving_usd": 0.0}}
        t = agg["totals"]
        vals = [
            f'{int(t["requests"]):,}',
            f'{int(t["completion_tokens"]):,}',
            _money(t["cost_usd"]),
            _money(t["saving_usd"]),
        ]
        for num, val in zip(self._tile_nums, vals):
            num.setText(val)

    def _refresh_live(self) -> None:
        self._refresh_today_tiles()
        data = read_live(self._data_dir())
        cur = data.get("current")
        last = data.get("last")
        if cur:
            self.live_cur.setText(
                f"● 正在调用: {cur.get('model_id')} [{cur.get('scenario')}]  "
                f"输入≈{cur.get('prompt_tokens_est', 0)} tokens  · 已开始 {cur.get('started_at', '')[:19]}"
            )
        else:
            self.live_cur.setText("— 当前无请求 —")
        if last:
            err = f"  (错误: {last.get('error')})" if last.get("error") else ""
            self.live_last.setText(
                f"最近完成: {last.get('model_id')} · 输出 {last.get('completion_tokens')} tokens · "
                f"{last.get('decode_tps')} t/s · 首字 {last.get('ttft_ms')}ms{err}"
            )
        else:
            self.live_last.setText("最近完成：-")

    def _refresh_history(self) -> None:
        days = self.range_combo.currentData()
        start, end = last_n_days(int(days))
        agg = aggregate(self._data_dir(), start, end)
        t = agg["totals"]
        self.summary.setText(
            f"范围 {start} ~ {end}：{t['requests']} 请求 · 输入 {t['prompt_tokens']:,} · "
            f"输出 {t['completion_tokens']:,} · 花费 {_money(t['cost_usd'])} · 节省 {_money(t['saving_usd'])}"
        )
        models = agg["models"]
        self.table.setRowCount(len(models))
        for i, (name, m) in enumerate(sorted(models.items(), key=lambda kv: -kv[1]["completion_tokens"])):
            vals = [
                name, str(int(m["requests"])), f'{int(m["prompt_tokens"]):,}',
                f'{int(m["completion_tokens"]):,}', str(m["avg_tps"]), str(m["avg_ttft_ms"]),
                _money(m["cost_usd"]), _money(m["saving_usd"]),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self._draw_chart(agg["per_day"])

    def _draw_chart(self, per_day: list[dict]) -> None:
        self.chart.removeAllSeries()
        try:
            for ax in list(self.chart.axes(Qt.Orientation.Horizontal)) + list(self.chart.axes(Qt.Orientation.Vertical)):
                self.chart.removeAxis(ax)
        except Exception:
            pass
        if not per_day:
            self.chart.setTitle("每天 tokens（暂无数据）")
            return
        days = [p["date"][5:] for p in per_day]
        series = QBarSeries()
        s_in = QBarSet("输入 tokens")
        s_out = QBarSet("输出 tokens")
        colors = [QColor("#38bdf8"), QColor("#818cf8")]
        for idx, s in enumerate((s_in, s_out)):
            s.setColor(colors[idx])
            for p in per_day:
                s.append(int(p["prompt_tokens"] if idx == 0 else p["completion_tokens"]))
            series.append(s)
        self.chart.addSeries(series)
        cat = QBarCategoryAxis()
        cat.append(days)
        cat.setLabelsColor(QColor("#9db4d9"))
        cat.setGridLineVisible(False)
        self.chart.addAxis(cat, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(cat)
        y = QValueAxis()
        y.setLabelsColor(QColor("#9db4d9"))
        y.setGridLineColor(QColor(255, 255, 255, 26))
        y.setLabelFormat("%d")
        self.chart.addAxis(y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(y)
        leg = self.chart.legend()
        leg.setLabelColor(QColor("#c7d6f2"))
        self.chart.setTitle(f"每天 tokens（近 {self.range_combo.currentText()}）")
