# Smartoken V1 设计文档 — 面向终端的模型智能选择中转平台

> 版本 v0.3 · 依据 routelabsai/lab + steemmandavid/OpenClawRouter **源码级调研**修订
> 核心价值主张：**任务感知的成本最优路由 + 可验证的省钱数据**。API 聚合只是最终落地路径，不是卖点。

---

## 一、定位与目标用户

- **一句话产品定义**：跑在用户终端上的 daemon；任意 OpenAI-compatible agent 只需把 base_url 指过来，之后所有 LLM 调用自动按「复杂度 × 类型 × 预算」落到最合适的本地 / 云端模型，面板上直接展示真实节省数字。
- **首要场景**：coding agent（Cline / Cursor / OpenWebUI / DSH 自身等 OpenAI-compatible 系）。多模态次之。
- **产品决策（2026-09）**：不接入 Anthropic 协议/品牌（Claude Code 等 Anthropic 原生 agent 不在支持名单）；**模型选择默认中国优先** —— 本地优先（Qwen/本地 uncensored 等，免费且隐私）→ 国产云端池（DeepSeek / 智谱 GLM / 通义 Qwen），海外厂商仅当用户显式配置时才出现。
- **对标痛点原句**（来自 OpenClaw Router README）："Self-hosted bots default to a single model. That's wasteful: a 'hi' gets the same 30B coding model as a stack-trace debug." —— 我们把它泛化到整个 agent 生态。

### 竞争格局速览（均经 API/README 实证）
| 项目 | 形态 | 关键事实 | 对我们的启示 |
|------|------|---------|-------------|
| LiteLLM | 库+网关 | 纯协议适配，无任务感知 | 接入层参考，勿在此内卷 |
| [routelabsai/laboratory](https://github.com/pyrolabslabai/laboratory) (v0.5, MIT, ~5600行 py) | pip install → router start 守护进程 | YAML+pydantic 配置深合并；关键词 complexity 分类器；隐私正则强制本地；HeuristicVerifier 弱响应升级云；cloud_budget_usd/max_cloud_cost_usd 双闸门(402)；DecisionTrace 嵌入每个响应；假流式（整包生成后按词回放）；provider if-elif 硬编码分支 | 抄其"决策即数据对象"+预算门控+验证再升级；避开 provider 闭集反模式 |
| [steemanndavid/open-claw-route](https://github.com/steammandavid/openclaw-labroute) (~943行单文件 FastAPI) | Docker 自托管 | classify = 截断500字符→本地小模型 few-shot(temp=0)+前置关键词覆盖；失败重试3次默认 MEDIUM；TIERS dict 常量映射 SIMPLE→Ollama qwen32b(cap 512 tokens)/MED-COMPLEX→z.ai claude；OpenAI⇄Anthropic 双向 SSE 逐行翻译（为适配智谱 z.ai 的 Anthropic 兼容口）；后端零健康检查(/health 恒 ok)、零缓存、无状态、日志打全量消息 | 抄其"独立分类通道+元数据剥离+安全档兜底"与 OpenAI-compatible 转发思路；其余几乎全是我们要补的缺口。注：其 OpenAI⇄Anthropic 翻译是为 z.ai 老接口而生，我们不做 Anthropic 协议，故不照搬该翻译层 |
| openmarkai fork | — | 自称 "Benchmark-driven… not keyword heuristics" | 印证社区公认升级方向 = 基于真实流量的学习，正是我们的轨道 B |

---

## 二、架构总览

```mermaid
graph TB
    subgraph CLIENT[客户端侧]
        A[各类 AGENT<br/>Cline / OpenWebUI / DSH / 自研 · OpenAI-compatible 系]
        CFG["agent 配置：base_url -> http://127.0.0.1:8787/v1"]
    end

    subgraph PLATFORM[平台 Daemon · 本机常驻进程]
        GW["① Gateway 统一接入<br/>chat/completions + 真SSE透传 · OpenAI-compatible 专用"]
        ID["② Task Classifier 任务识别器<br/>特征提取→规则打分→可选本地few-shot复核"]
        RT["③ Router Core 路由决策引擎<br/>策略链 identity>explicit>preference>difficulty>availability>budget"]
        REG["④ Model Registry 开放注册表<br/>能力标签+成本档案+实时健康+配额态"]
        ORCH["⑤ Orchestrator 编排器<br/>v1整单; v2预留 decompose()/merge() hook"]
        GOV["⑥ Governance 治理层<br/>双闸门预算·语义缓存·fallback树·审计落盘"]
        OBS["⑦ Observability 观测面板<br/>节省额·命中率·延迟分布·fallback次数"]
    end

    subgraph BACKENDS[推理后端池]
        LOCAL[本地 Ollama/vLLM/LM Studio]
        FREE[免费/低价云端 provider 池·热替换成员]
        FLAG[旗舰云端·仅 L2 复杂任务]
    end

    A --> CFG --> GW --> ID --> RT
    RT <--> REG
    RT --> ORCH --> GOV
    GOV --> LOCAL & FREE & FLAG
    GOV -.每次请求一条记录.-> AUD[(Audit Store)]
    AUD --> OBS
    OBS -.弱监督信号回流.-> ID
end
```

### 模块职责要点（含调研驱动的修订）

**① Gateway — 只做翻译，不做决策（OpenAI-compatible 专用）**
- 端点：`/v1/chat/completions`（M1 已实现，JSON+SSE 真流式）；`/v1/responses`（OpenAI Responses API，M2 透传）；`/v1/embeddings`（M2+）；另有 `/healthz`（真实探活）、`/v1/models`（合并 Registry 全量清单）。**不实现 `/v1/messages` 等 Anthropic 协议入口**（产品决策）。
- 出站只走 OpenAI-compatible 通道：本地 Ollama `/v1`、国产/兼容云端直接透传。**不引入 OpenAI⇄Anthropic 双向翻译层**（openclaw 的翻译是为智谱 z.ai Anthropic 兼容老口而生，我们无需照搬）。
- 流式必须真透传（routelabs 是假流式=首 token 延迟等于全延迟，明确反例）。
- model 字段语义：显式指定 → 直通并记账；值为 `auto`/缺省 → 进入完整决策链。**绝不破坏 agent 既有工作流**。

**② Task Classifier — 三级流水线，全程本地可跑**

| 级 | 机制 | 延迟目标 | 说明 |
|----|------|---------|------|
| T0 特征提取 | prompt tokens、轮次、代码块/工具 schema/文件路径信号、图片 base64、agent 系统提示词指纹 hash | <5ms | 全部从请求本身取，零额外调用 |
| T1 规则打分 | difficulty∈{L0,L1,L2} × category∈{coding,vision,general,agent-subtask} + confidence | <10ms | v1 主通道；参考 routelabs complexity 词表但改为多维加权而非单维关键词命中 |
| T2 few-shot 复核 | 低置信度时才调本地小模型(temp=0, 截断~500字符)三档判定 | ~1s 可选跳过 | 借鉴 OpenClaw classify()：**独立分类通道 + 前置关键词覆盖 + 3次重试失败默认安全档(MEDIUM)**；先剥客户端元数据包裹再分类 |

输出统一三元组 `{difficulty, category, confidence}`，接口稳定，T2 可整体摘除不影响链路。

**③ Router Core — 策略链（六优先级，自上而下短路）**
```
P0 identity    agent 指纹命中已知模板 → 套用该 agent 经验最优组合   ← 新增(routelabs agent-role-routing 思路)
P1 explicit    用户/agent 显式指定模型 → 尊重之，仅做预算检查
P2 preference  用户偏好表: category→首选列表(如 coding→[A,B], vision→C)
P3 difficulty  L0→本地池 / L1→免费中档云 / L2→旗舰
P4 availability 健康+容量剔除不可用端点
P5 budget      剩余预算不足 → 降级更便宜层并落告警事件
```
每条策略 = 独立组件 + YAML 声明 + pydantic 校验；配置采用 **DEFAULT_CONFIG 深合并**（抄 routelabs config.py），用户只写覆盖项。

**验证再升级（verification-aware escalation）— 本次调研最大收获**：
> 不是"复杂→贵模型"硬映射，而是「先用候选便宜模型答 → HeuristicVerifier 判弱响应(长度阈值/弱信号词/无实质内容) → 才升级到下一档」。对 L1/L2 边界任务尤其省钱省延迟。v1 内置基础版 verifier，权重进审计日志供轨道 B 学习。

**④ Model Registry — 开放注册表，反闭集设计**
- 每个后端一条记录：`{id, kind(local/cloud), capabilities[coding,vision,function-call,...], cost_profile(实时费率或固定估算标记), health(live probe结果), quota_state, latency_p95}`
- 本地发现：Ollama `GET /api/tags`、llama.cpp `/models` 周期心跳 + /healthz 即时探测(timeout≈1s)。
- 云端 provider 是池中成员而非代码分支——**禁止 if provider=="xxx" 链式判断**(routelabs service.py:892-937 的反模式)，新供应商=加 adapter 实现 Protocol + 注册一条 yaml。
- 免费额度只是 `cost=0/quota_limited=true` 的成员；停服限流只影响池子，路由逻辑零改动。**热替换是架构级保证**。

**⑤ Orchestrator — v1 克制**
- V1：**整单路由**一次决策一个目标，不拆解。（先验证留存与准确率）
- V2 预埋两个稳定接口位：`decompose(task)->subtasks[]`、`merge(subtask_results)`；届时挂 PyroDash 式 token 级协作不用重写主干。

**⑥ Governance — "省钱"必须是数据**
- **双闸门预算**（抄 routelabs 语义）：全局 `cloud_budget_usd`(日/月窗) + 每请求 `max_cloud_cost_usd`；超限返回清晰 402 结构体而非静默失败。成本记账区分「真实 usage」与「固定单价估算」两种来源标记。
- fallback 树：主选故障 → 同类次优 → 跨档降级(仅非隐私任务可上云)；隐私命中(routelabs privacy 正则思路：PII/密钥/代码片段信号)**强制锁死在本地层**，任何 fallback 不得越界。
- 缓存(v1.5+)：精确哈希去重先行，语义缓存放后面；OpenClaw 那种透传上游 cache_read 字段≠应用层缓存，别混淆。

**⑦ Observability & Audit — 一份数据喂三个用途**
每次请求落盘结构化记录：
```json
{"request_id","features(T0)","decision_path":["P0 hit: cline-template"],"chosen_model",
 "verifier":"weak→escalated|ok","actual_cost","est_flagship_cost","saving","latency_ms"}
```
消费方：Dashboard(四指标)、轨道 B 学习器、用户导出报告。日志中**禁止打全量 user message**(OpenClaw INFO 全文打印 = 隐私泄漏面反例)，默认脱敏摘要。

---

## 三、自研能力清单（两者共同缺失 = 我们的护城河所在）

| # | 能力 | 现状证据 | Smartoken 做法 |
|---|------|---------|---------------|
| 1 | 多维打分分类 | 两家都只有单维复杂度(关键词 or 3档LLM) | difficulty×category×budget 三维 + confidence 门控 T2 |
| 2 | 基于流量的在线校准(**轨道B·核心壁垒**) | openmarkai fork 才刚喊出 benchmark-driven 口号 | shadow mode：同请求并行发候选+选中模型，用弱监督信号(追问/重试/纠正)离线更新路由权重；纯事后、零额外在线开销 |
| 3 | 会话感知 | 两家均无状态、只看最后一条消息 | session 维度聚合：轮次累计难度漂移、上下文窗口预估算、会话级成本分摊 |
| 4 | 活的后端治理 | OpenClaw /health 恒 ok、模型写死内网IP import期取值 | Registry 实时健康+p95延迟+容量感知的 availability 策略 |
| 5 | 真流式+原生协议保真 | routelabs 假流式按词回放 | SSE 逐 chunk 直通，转换只发生在跨协议的边界 |
| 6 | 真实费率预算 | routelals 固定单价常量记账；openclaw 完全没有 | usage 优先回算，缺 usage 时标 estimated 并单独展示置信度 |

---

## 四、工程组织纪律（从两家的反模式里立规矩）

- **拒绝单文件堆砌**：OpenClaw 943行 router.py 承载一切 → 我们按七模块分目录，每模块 <800 行为重构触发线。
- **消灭魔法字符串**：模型名/IP/端口一律进 YAML registry，import 期 `os.getenv` 取默认值(routalabs/openclaw 通病)= 不可热更难测试注入，禁止。
- **配置即契约**：pydantic schema 对外暴露 JSON Schema，第三方 agent 可据此生成自己的接入片段。
- **隐私红线**：classifier/governance 全程本地或用户显信任节点执行——"卖点是本地省钱保隐私，识别层却把 prompt 发给云端"是自相矛盾，架构上封死这条路(T2 只能指向 local kind)。
- **免费 provider 脆弱性**：任何 cost=0 成员必须带 TTL 与失效探测，路由决策不得对其产生硬依赖路径。
- **中国优先、协议收敛**：内置模板只放国产厂商（本地优先 → DeepSeek/GLM/通义），出站只认 OpenAI-compatible 一种协议，杜绝为单一厂商接口引入第二种协议面（Anthropic 品牌协议整体不做）。

---

## 五、里程碑切分

| 阶段 | 周期 | 交付 | 验收标准 |
|------|------|------|---------|
| M1 | wk1–2 | Gateway + Registry(Ollama发现) + P1/P3/P4 基础策略链 + Audit v0 | 改一行 env，Cline/OpenWebUI 等 OpenAI-compatible agent 流量正确分流到 Ollama，每条日志可见 decision_path |
| M2 | wk3–4 | Classifier T0/T1 完整化 + identity/preference 表 + 双闸门预算 + Verifier 基础版 + Dashboard | 偏好声明生效；面板显示周节省额(estimated 口径标注清楚) |
| M3 | wk5–6 | shadow mode 轨道B灰度 + fallback树打磨 + 发布渠道(npm/brew/docker 三选一) | 连续一周 routing accuracy≥85%、崩溃率<1%、p95 附加延迟<80ms |
| V2预研 | — | Orchestrator decompose/merge hook、token级协作(PyroDash式)、多设备偏好同步 | — |

### 风险登记
| 风险 | 等级 | 缓解 |
|------|------|------|
| 复杂度误判导致旗舰任务掉到小模型→体验事故 | 高 | verifier 升级兜底 + L2 置信度阈值保守起步 + 审计可回放复盘 |
| 免费额度政策突变 | 中 | 池化+TTL，最坏情况只是少一个零成本选项 |
| LiteLLM/routelabs 以插件形式覆盖功能面 | 中 | 差异化锚定「终端侧+agent生态集成+可验证省钱数据」，不做纯开发者工具叙事 |
| 单机性能(分类器常驻内存) | 低 | T2 默认关闭按需启用；规则通道 <10ms 无压力 |

---

## 六、桌面外壳规格（最终产品形态 · 2026-09 用户确认）

### 6.1 形态与入口
| # | 需求 | 落地 |
|---|------|------|
| 1 | 封装成**可安装 EXE**，装完有桌面/开始菜单图标 | PyInstaller(onepath 目录模式)+ Inno Setup 安装器；含 uninstaller；图标随安装生成 |
| 2 | 双击图标进**图形化配置** | Qt 主窗口（见 6.3） |
| 3 | **token 用量看板**（实时 + 历史 7 天） | 读 daemon audit JSONL + live 事件；图表展示 |
| 4 | 关窗 → **托盘常驻** | QSystemTrayIcon（菜单：打开面板/悬浮球开关/退出） |
| 5 | **透明桌面气泡**实时显示"正在调哪个模型 / token" | 无边框置顶半透明 Widget，右键菜单可关 |

### 6.2 进程模型（内核复用，不改架构）
```
Smartoken.exe (PySide6 GUI，单实例)
 ├─ 管理 daemon 子进程(uvicorn, 同一 venv 内嵌) ── 启动/停止按钮 = 子进程生命周期
 ├─ 配置文件目录: %APPDATA%\Smartoken\ (router.yaml + secrets)
 │    secrets 用 Windows DPAPI 加密落盘；密钥不再平铺 .env
 ├─ 实时数据: 轮询 data\live.json(0.5s) + 读 audit\*.ndjson
 └─ 托盘 + 悬浮气泡(Qt)
```
- GUI 与 daemon 同机同语（Python），**不引入跨语言桥**；EXE 内嵌解释器与依赖。
- 单实例锁：重复双击唤起已有窗口。

### 6.3 主窗口功能区
| 区 | 内容 |
|----|------|
| 状态区 | 服务开/关按钮 + 当前监听地址 + 健康状态（各后端灯） |
| API 信息区 | **一键生成 Smartoken 接入 key**（随机、可复制、落 secrets），展示给 agent 填的 base_url/key/模型(auto) |
| 模型接入管理 | 厂商列表（Ollama/本地自定义/DeepSeek/GLM/通义/免费档…）增删改；key 录入进 secrets；启停开关 |
| 策略设置 | 模式：**auto（默认智能）** 或 场景预设（**coding / talking / general…**）；场景= 难度映射+偏好顺序 的命名套餐，可编辑；高级= 直接编辑 yaml |
| 用量看板 | 实时：本次/本日各模型 tokens、decode tokens/s、花费、节省；历史：按天/模型聚合折线+表格（默认留 7 天，可调） |

### 6.4 内核侧需要的配套增强（GUI 独立，先落内核）
1. 审计记录补字段：`ttft_ms`、`decode_tps`（流式请求测量）、`scenario`；
2. `data/live.json` 实时快照：当前进行中的 `{model, prompt_tokens, completion_tokens, tps}`；
3. **7 天留存**：daemon 启动时清理过期审计文件（天数可配）；
4. 场景套餐预设进配置：`policy.scenarios.{auto,coding,talking,general}` → 生成 difficulty_map + preference（coding 例：L0/L1 本地 → L2 云 coding 强者）。
5. 配置/密钥从"项目目录 .env"平滑迁移到 `%APPDATA%\Smartoken\`（dev 模式仍兼容现有 .env）。

### 6.5 里程碑（外壳线，与内核 M 线并行）
| 阶段 | 内容 | 验收 |
|------|------|------|
| S1 | 内核配套增强（6.4 全部）+ scenario 预设 | CLI 可查 live.json；审计含 tps/ttft；旧审计自动清 |
| S2 | PySide6 骨架：主窗（状态/API key 生成/模型管理/策略场景）+ daemon 子进程启停 | 双击→配置→一键启动 daemon→agent 可连 |
| S3 | 用量看板（实时+历史7天，图+表）+ 数据迁移到 %APPDATA% | 看板数字与审计一致 |
| S4 | 托盘 + 透明悬浮气泡（右键关闭）+ 单实例 | 关窗驻留托盘；气泡实时跟 model/token |
| S5 | PyInstaller + Inno Setup 打包，桌面图标/卸载 | 干净机器(装 Python 运行时也可)安装→运行全流程 |

### 6.6 技术选型说明（默认建议，可改）
- GUI：**PySide6(Qt6)** —— 与内核同语言，托盘/无边框透明气泡/图表都是原生能力；Exe 体积 ~80–150MB（可接受性待确认）。
- 图表：QtCharts 或轻量自绘；安装器：Inno Setup（免费、中文好）。
- 风险提示：Windows Defender 对 PyInstaller 产物可能误报（需代码签名或加白处理）；首启/托盘自启策略默认不注册开机自启，用户可手动加。

