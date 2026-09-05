# Smartoken — 面向终端的任务感知模型路由器（v0.1）

设计文档见 [`v1-design.md`](v1-design.md)；竞品源码参考在 [`research/refs/`](research/refs/)。

---

## 🧪 给测试者（v0.1 Developer Preview）

> Smartoken 是 **BYO-模型** 产品：它自己不内置大模型，而是把**你本机的模型/你自己的云端 key** 接入一个智能路由器 —— 简单任务走便宜/本地模型，复杂任务才调旗舰。请自备模型源（下文第 4 步）。

### 1. 获取源码
```bash
git clone https://github.com/LIN-LAB-AI/smartoken.git
cd smartoken
```
（不会 git 就直接在仓库页 **Code → Download ZIP** 解压。）

### 2. 安装（需 Python 3.11+）
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[gui]"
```
网络慢可加国内源：`pip install -e ".[gui]" -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 3. 启动图形界面
```bash
smartoken-gui        # 若命令不可用：python -m smartoken_gui.app
```
窗口三页：**①服务/API 接入**（启动/停止、生成你的接入 Key）→ **②模型与策略**（增删/启停/测试你的模型源、策略 auto/自定义）→ **③用量看板**（实时 + 历史 token/花费/节省，深色图表）。

### 4. 接入模型源（三选一，或都用）
| 方式 | 做法 |
|------|------|
| **A. 本地 Ollama（最省事）** | 安装 Ollama → `ollama pull qwen2.5:7b` → GUI ②页确认 `ollama-local` 启用/点"测试"变绿 |
| **B. 本地 OpenAI 兼容**（llama.cpp/LM Studio…） | GUI ②页「＋新建模型」：档位 local → base_url 填 `http://127.0.0.1:端口/v1`、默认模型名 |
| **C. 国产云端（自带 key）** | GUI ②页「＋新建」或编辑现有模板：DeepSeek=`https://api.deepseek.com/v1`(deepseek-chat) / 智谱 GLM=`https://open.bigmodel.cn/api/paas/v4`(glm-4.5) / 通义=`https://dashscope.aliyuncs.com/compatible-mode/v1`；Key 在行内"选中行：密钥"里保存（只存本机 `.env`，不入库） |

保存后点「探测全部状态」：灯 🟢=可路由、🟡=启用但连不上、🔴=停用。然后 ①页「启动服务」，模型栏填 `smartoken-auto`（虚拟路由模型）或真实模型名，即可用任意 OpenAI 兼容客户端（Cline / Cherry Studio / OpenWebUI…）或 curl 连 `http://127.0.0.1:8787/v1` 体验。

### 5. 常见问题
- **所有请求都报 no_route / 黄灯**：你的模型源没就绪——本地 Ollama 没装/没拉模型，或云端 key 没填对。先按第 4 步任一方式配好一个再试。
- **想先只看 UI**：不配模型也能开 GUI，启动服务后空跑会看到 no_route 提示（审计照记）。
- **8787 被占用**：改 `config/router.yaml` 的 `server.port`。
- **关窗口服务就停**：托盘驻留功能尚未上线（v0.2），先用别关或点 ①「停止」。
- **看不懂某条审计**：把 `data-dev/audit/<日期>.ndjson` 里对应行贴到 Issues（去掉业务内容，它只含模型/决策元数据，无对话原文）。

### 6. 隐私与使用须知
- 请求只发给你配置的模型后端；识别与决策全程本地；审计只存本机、**不含对话原文**。
- 你的 `.env`（真实密钥）已在 `.gitignore` 排除——**不要把它提交或发给任何人**。
- 本项目当前**未附开源许可**：仅供评估测试，请勿再分发/商用。
- 测试中发现 bug 或想提需求 → 仓库 **Issues** 反馈，注明：操作系统、Python 版本、报错文本、审计行。

---

## M1 范围（本仓库当前代码）

- **Gateway**：`/v1/chat/completions`（JSON + SSE 真流式透传）、`/v1/models`、`/healthz`
- **Registry**：Ollama `/api/tags` 自动发现 + TTL 健康探测；provider 池化（无 if-provider 分支）
- **Classifier**：T0 特征提取 + T1 规则打分（`{difficulty, category, confidence}`），纯本地 <10ms
- **RouterCore**：策略链 explicit → identity → preference → difficulty（availability 内建于候选过滤）
- **Audit**：每次请求一条 JSONL（含 `decision_path` / 命中模型 / 实际花费 / 旗舰参照估算 / 节省）
- **Budget**：P5 双闸门（全局日额度 + 每请求上限，可开关）

M1 只做 OpenAI-compatible 出站（覆盖 Ollama `/v1` 与国产/兼容云端端点）。

**产品决策（2026-09）**：不接入 Anthropic 协议/品牌（Claude Code 等 Anthropic 原生 agent 不在支持名单）；**模型选择默认中国优先** —— 本地优先（Qwen/本地 uncensored 等，免费且隐私）→ 国产云端池（DeepSeek / 智谱 GLM / 通义 Qwen，均在 `config/router.yaml` 中以 `enabled: false` 提供模板，填 key 并打开即可）。

## 快速开始

```bash
cd D:\DSH\smartoken
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 1) 配置 config/router.yaml（默认已含 ollama-local；按需打开/添加云端成员）
# 2) 启动（自动发现 Ollama 本地模型并探测健康）
smartoken start

# 3) 让任意 OpenAI 兼容 agent 指过来
#    base_url = http://127.0.0.1:8787/v1
#    例如 Cline / OpenWebUI 等；模型名写 auto 或不填即走智能路由，
#    显式指定（如 qwen:7b）则直通该模型（P1 explicit，绝不静默改道）。

# 4) 看路由决策与省钱数字
#    data/audit/<yyyy-mm-dd>.ndjson
```

### 接入 WorkBuddy / 任意带 Key 的桌面 agent

1. 在 `.env` 设一把门禁 key（不设 = 本机直开，不建议外露时使用）：
   `SMARTOKEN_API_KEY=sk-smartoken-xxxx`
2. `smartoken start --config config/dev-china.yaml` 重启。
3. 在 WorkBuddy（或 Cline/Cherry/OpenWebUI 等）里新增 **OpenAI 兼容 / 自定义模型服务**：
   - base_url：`http://127.0.0.1:8787/v1`
   - API Key：`.env` 里那把 `SMARTOKEN_API_KEY`
   - 模型：**`smartoken-auto`**（虚拟路由模型，每请求自动走策略链：
     简单/本地档 → uncensored/Qwen 免费本地；复杂 → DeepSeek/GLM 云端）
4. 让 WorkBuddy 发一句话，然后在 `data*/audit/<date>.ndjson` 里看该请求的
   `decision_path / backend_id / model_id` 即可确认已接入。

### 图形化控制台（S2，开发运行）

```bash
pip install -e ".[gui]"
smartoken-gui                      # 或 smartoken-gui-w（无黑窗）
# 主窗口：①服务启停/API key 生成 ②模型接入管理 ③策略场景(auto/coding/talking/general) ④用量看板(S3)
# daemon 以子线程内嵌，关窗即停；S4 再引入托盘/悬浮球
```

### 验证（不依赖 Ollama 也能跑通单测）

```bash
pytest -q          # config / classifier / router / budget / GUI 纯逻辑
```

## 目录结构

```
config/router.yaml          # 默认配置（深合并，用户只写覆盖项）
src/smartoken/
  models.py                 # 请求子集校验 + 运行时对象（Decision/Audit）
  config.py                 # 内嵌默认 + 文件深合并 + env 密钥注入
  classifier.py             # T0 特征 / T1 规则（T2 few-shot 复核留 M2 挂点）
  registry.py               # 后端池 + Ollama 发现 + TTL 健康
  router_core.py            # 策略链 + budget 闸门
  adapters.py               # OpenAI-compatible 出站（JSON/SSE 直通）
  service.py                # 编排：分类→决策→出站→审计；同 kind fallback
  gateway.py                # FastAPI 层（无业务逻辑）
  cli.py                    # smartoken start
tests/                      # pytest（不联网可跑）
```

## 设计红线（来自竞品源码调研 + 产品决策）

1. 绝不写 `if provider=="xxx"` 路由分支 —— provider 是带能力标签的池成员。
2. 流式必须真透传，禁止整包生成后回放（假流式反例见 routelabs）。
3. 审计日志禁止落 user message 原文，只落特征与决策元数据。
4. 免费 provider 永不构成硬依赖（enabled=false 时零影响）。
5. 隐私：识别与决策全程本地；云端仅被选中的推理请求可达。
6. **不做 Anthropic 协议/品牌接入**；默认路由与模板配置**中国模型优先**，
   海外厂商仅当用户显式添加配置时才可能出现。
