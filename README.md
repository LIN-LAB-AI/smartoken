# Smartoken — 面向终端的任务感知模型路由器（M1 脚手架）

设计文档见 [`v1-design.md`](v1-design.md)；竞品源码参考在 [`research/refs/`](research/refs/)。

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
