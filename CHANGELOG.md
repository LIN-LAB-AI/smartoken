# Changelog

## v0.1.0（2026-09-05）· 首个定稿版

### 定位
面向终端的**任务感知模型路由平台**：任意 OpenAI-compatible agent 改一行 base_url 接入，
简单任务走本地免费模型、复杂任务才调云端旗舰；每次调用可审计、可算省钱。
产品取向：中国模型优先、不做 Anthropic 协议/品牌接入。

### 内核（smartoken daemon）
- Gateway：`/v1/chat/completions`（JSON + SSE 真流式透传）、`/v1/models`、`/healthz`；可选静态鉴权（`SMARTOKEN_API_KEY`）
- 虚拟路由模型 `smartoken-auto`：模型清单首条，agent 选它即每请求走完整策略链
- 分类器：T0 特征（含 CJK 感知 token 估算）+ T1 规则 → `{difficulty, category, confidence}`
- 策略链：explicit → identity → preference → difficulty（availability 内建），P5 双闸门预算
- 策略模式：auto（全局智能） / custom（按后端 role×任务类别过滤），场景 difficulty_map 可配
- Registry：后端开放池化（零 if-provider 分支），Ollama 自动发现 + TTL 健康探测，同 kind fallback
- 治理：审计 JSONL（含 ttft/decode_tps/scenario/花费与节省）、7 天留存自动清理、`live.json` 实时快照
- 已接入模板：本地 uncensored-27b(:88)、Ollama、DeepSeek、智谱 GLM、通义（模板）

### 桌面壳（smartoken-gui，PySide6）
- ① 服务/API：启停/重启（daemon 内嵌 QThread）、base_url/API Key 展示与一键轮换
- ② 模型与策略：行级勾选启用、新建/删除、测试与红黄绿灯、策略角色列、自定义/auto 切换
- ③ 用量看板：今日四数字瓷砖 + 实时数据行（2s 自动刷新/手动刷新）+ 历史聚合表 + 深色霓虹柱状图
- 视觉：深空渐变深色科技风主题、状态胶囊、发光圆点、程序化应用图标

### 工程
- 测试：36 项（内核 + GUI 纯逻辑 + 聚合），全部通过
- 目录：`src/smartoken`（内核）、`src/smartoken_gui`（壳）、`config/`（模板）、`scripts/`（mock 上游、离屏冒烟）、`research/refs/`（竞品源码）
- 运行：`smartoken start --config config/dev-china.yaml` / `smartoken-gui --config …`

### 后续（v0.2 规划）
- S4：系统托盘常驻 + 透明桌面悬浮气泡（实时模型/token）
- S5：PyInstaller 打包 EXE + Inno Setup 安装器（桌面图标/卸载）
- 数据/密钥迁移 `%APPDATA%`、新增后端表单化、Dashboards 历史导入导出
