<p align="center">
  <h1 align="center">MySQL Error Log Analyzer</h1>
  <p align="center">MySQL 错误日志自动分析工具</p>
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python">
    <img src="https://img.shields.io/badge/LangGraph-0.0.30+-green" alt="LangGraph">
    <img src="https://img.shields.io/badge/FastAPI-0.104+-teal" alt="FastAPI">
    <img src="https://img.shields.io/badge/Vue3-3.x-brightgreen" alt="Vue3">
    <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
  </p>
</p>

---

## 项目简介

**MySQL Error Log Analyzer** 是一个即插即用的 MySQL 错误日志自动分析工具。放入任何有 MySQL 的环境中，它能主动找到错误日志并进行分析，提供 CLI 对话和 Web 可视化两种交互方式。

### 核心特性

- 🔍 **自动发现** — 自动检测本机 MySQL 实例及错误日志路径，支持多实例同时监控
- 🤖 **AI 分析** — 基于 LangGraph 多节点工作流，支持 OpenAI / Ollama / 自定义端点
- 💬 **智能对话** — CLI 自然语言对话，RAG 增强检索相关日志上下文
- 📊 **可视化** — Web 界面提供饼图、柱状图、折线图、知识图谱等多种图表
- 🔎 **语义搜索** — 集成 turbovec 向量索引，支持语义相似度搜索（可选）
- ⏱️ **自定义时段** — 支持任意整时时间段（3h、5d 等），智能读取间隔
- 🚨 **主动推送** — 关键错误实时检测，LLM 自动生成修复建议
- 🔒 **安全** — 默认本地监听，外部访问需 JWT 认证
- 🐳 **灵活部署** — Python 直接运行 / Docker / systemd 常驻

---

## 架构设计

```
┌──────────────────────────────────────────────────────────┐
│                     Web 可视化层                          │
│          Vue3 + ECharts（仪表盘/图谱/对话/日志查询）       │
├──────────────────────────────────────────────────────────┤
│                     API 服务层                            │
│     FastAPI（REST API + WebSocket + JWT 认证）            │
├──────────────────────────────────────────────────────────┤
│                   LangGraph 分析引擎                      │
│  解析 → 分类 → 关联分析 → 摘要生成 → 对话（RAG 增强）     │
├──────────────┬───────────────────────┬───────────────────┤
│  日志采集层   │    向量搜索层（可选）   │    通知层          │
│ 发现/读取/   │  Embedding + turbovec │  关键错误检测      │
│ 解析/监控    │  语义搜索 + RAG       │  LLM 建议 + 推送   │
├──────────────┴───────────────────────┴───────────────────┤
│                     数据存储层                            │
│              SQLite（日志/分析/告警）                      │
└──────────────────────────────────────────────────────────┘
```

### 模块说明

| 模块 | 路径 | 功能 |
|------|------|------|
| 配置管理 | `src/config.py` | YAML 配置加载，环境变量覆盖，默认值合并 |
| 日志采集 | `src/collector/` | 自动发现 MySQL 实例，日志解析，流式读取，watchdog 监控 |
| 分析引擎 | `src/analyzer/` | LangGraph 工作流（5 节点），LLM 接口（多提供商） |
| 向量搜索 | `src/vector/` | Embedding 管理，turbovec 索引，语义搜索，RAG |
| 数据存储 | `src/storage/` | SQLite 异步操作，4 张表，12 个查询方法 |
| 状态追踪 | `src/status.py` | 运行时长、CPU/内存、实例状态、处理进度 |
| 通知推送 | `src/notifier/` | 关键错误检测，LLM 建议，WebSocket/CLI 双推送 |
| CLI 界面 | `src/cli/` | prompt_toolkit 交互，rich 美化，自然语言对话 |
| Web 后端 | `src/web/` | FastAPI + 5 组 REST API + WebSocket + JWT |
| Web 前端 | `frontend/` | Vue3 + ECharts 深色主题，7 个可视化组件 |

### LangGraph 分析工作流

```
原始日志 → ParseNode（结构化解析）
         → ClassifyNode（智能分类，10 个类别）
         → CorrelateNode（关联分析，时序模式 + 异常频率）
         → SummarizeNode（LLM 生成摘要与修复建议）
```

### RAG 对话流程

```
用户提问 → Embedding 生成向量
         → turbovec 语义检索相关日志
         → 相关日志 + 用户问题 → LLM 生成回答
```

---

## 功能展示

### 时间段分析

支持预设和自定义时间段：

| 预设时段 | 自定义时段 |
|---------|-----------|
| 1 小时 | `3h`（3 小时） |
| 24 小时 | `5h`（5 小时） |
| 7 天 | `12h`（12 小时） |
| 全部 | `3d`（3 天） |

**智能读取间隔**：<= 24h 的时段按时段本身间隔读取，> 24h 的时段每 24 小时自动读取。

### 可视化图表

| 图表类型 | 用途 |
|---------|------|
| 饼图 | 错误级别分布 |
| 柱状图 | 错误类别分布 |
| 折线图 | 错误趋势（按小时/天） |
| 知识图谱 | 错误码 → 类别 → 根因 → 建议 |
| 热力图 | 错误时间分布 |

### 错误分类体系

| 类别 | 说明 |
|------|------|
| connection | 连接类错误（超时、拒绝、中断） |
| permission | 权限类错误（认证失败、访问拒绝） |
| innodb | InnoDB 引擎错误（损坏、死锁、回滚） |
| replication | 复制类错误（主从断开、延迟） |
| crash | 崩溃类错误（异常退出、中止） |
| deadlock | 死锁错误 |
| memory | 内存类错误（OOM、缓冲池不足） |
| configuration | 配置类错误 |
| performance | 性能类错误 |
| other | 其他错误 |

---

## 快速开始

### 环境要求

- Python 3.10+
- MySQL（本机运行）
- Node.js 18+（前端开发，可选）

### 安装

```bash
# 克隆仓库
git clone https://github.com/yumeng001yu/mysql-error-log-analyzer.git
cd mysql-error-log-analyzer

# 安装 Python 依赖
pip install -r requirements.txt

# 复制配置文件
cp config/config.yaml.example config/config.yaml

# 编辑配置（至少配置 LLM）
vim config/config.yaml
```

### 配置

编辑 `config/config.yaml`：

```yaml
# LLM 配置（必填）
llm:
  provider: "ollama"          # openai / ollama / custom
  model: "qwen2.5:7b"        # 模型名称
  api_base: "http://localhost:11434"  # API 端点
  api_key: ""                 # API Key（Ollama 不需要）

# Embedding 配置（可选，启用后支持语义搜索）
embedding:
  enabled: false
  provider: "ollama"
  model: "nomic-embed-text"
  api_base: "http://localhost:11434"
  dim: 768
```

### 启动

```bash
# CLI 模式（默认）
python -m src.main

# Web 模式
python -m src.main --web

# CLI + Web 同时运行
python -m src.main --web --cli

# 指定配置和端口
python -m src.main --web --port 9090 --config /path/to/config.yaml

# 守护进程模式（仅 Web）
python -m src.main --daemon
```

### Docker 部署

```bash
cd docker
docker-compose up -d
```

### systemd 常驻运行

```bash
# 参见 systemd/mysql-log-analyzer.service
sudo cp systemd/mysql-log-analyzer.service /etc/systemd/system/
sudo systemctl enable mysql-log-analyzer
sudo systemctl start mysql-log-analyzer
```

---

## CLI 命令

| 命令 | 说明 |
|------|------|
| `analyze [time_range]` | 运行分析（all/3h/5d 等，默认 all） |
| `semantic <query>` | 语义搜索日志（需配置 embedding） |
| `recent [n]` | 查看最近 N 条错误日志 |
| `search <keyword>` | 关键词搜索日志 |
| `status` | 查看程序运行状态 |
| `instances` | 查看监控的 MySQL 实例 |
| `alerts` | 查看未读关键错误告警 |
| `help` | 显示帮助 |
| `quit` | 退出 |

非命令输入自动进入 AI 对话模式。

---

## Web API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs` | 查询日志列表 |
| GET | `/api/logs/stats` | 日志统计 |
| GET | `/api/logs/distribution` | 错误分布 |
| GET | `/api/logs/trend` | 错误趋势 |
| GET | `/api/logs/semantic` | 语义搜索 |
| POST | `/api/analysis/run` | 触发分析 |
| GET | `/api/analysis/results` | 获取分析结果 |
| POST | `/api/chat` | AI 对话 |
| GET | `/api/status` | 程序状态 |
| GET | `/api/instances` | 实例列表 |
| GET | `/api/alerts` | 告警列表 |
| PUT | `/api/alerts/{id}/read` | 标记告警已读 |
| POST | `/api/auth/login` | 登录认证 |
| WS | `/ws/alerts` | 实时告警推送 |
| WS | `/ws/status` | 实时状态推送 |

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | 异步、自带 API 文档、WebSocket |
| AI 编排 | LangGraph | 有状态多步骤工作流 |
| LLM 接口 | LangChain | 统一多模型接口 |
| 向量索引 | turbovec | 4bit 量化，内存节省 8 倍 |
| 数据存储 | SQLite | 零配置、单文件部署 |
| 前端 | Vue3 + ECharts | 深色主题、响应式布局 |
| 日志监控 | watchdog | Python 文件监控库 |
| 部署 | Docker / systemd | 灵活部署方式 |

---

## 项目结构

```
mysql-error-log-analyzer/
├── config/
│   └── config.yaml.example      # 配置模板
├── docker/
│   ├── Dockerfile                # Docker 镜像
│   └── docker-compose.yaml       # 编排配置
├── frontend/
│   └── src/
│       ├── components/           # Vue3 组件
│       │   ├── Dashboard.vue     # 仪表盘
│       │   ├── LogQuery.vue      # 日志查询
│       │   ├── AnalysisReport.vue # 分析报告
│       │   ├── KnowledgeGraph.vue # 知识图谱
│       │   ├── ChatPanel.vue     # AI 对话
│       │   ├── StatusPanel.vue   # 系统状态
│       │   └── LoginPage.vue     # 登录页
│       ├── api.js                # API 封装
│       ├── router.js             # 路由配置
│       └── main.js               # 入口
├── src/
│   ├── analyzer/                 # 分析引擎
│   │   ├── graph.py              # LangGraph 工作流
│   │   ├── llm.py                # LLM 接口
│   │   └── nodes/                # 工作流节点
│   ├── cli/                      # CLI 界面
│   ├── collector/                # 日志采集
│   │   ├── discover.py           # 实例发现
│   │   ├── parser.py             # 日志解析
│   │   ├── reader.py             # 流式读取
│   │   └── watcher.py            # 文件监控
│   ├── notifier/                 # 通知推送
│   ├── storage/                  # 数据存储
│   ├── vector/                   # 向量搜索
│   │   ├── embedding.py          # Embedding 管理
│   │   ├── index.py              # turbovec 索引
│   │   └── manager.py            # 搜索管理
│   ├── web/                      # Web 后端
│   │   ├── app.py                # FastAPI 应用
│   │   ├── api/                  # API 路由
│   │   └── websocket.py          # WebSocket
│   ├── config.py                 # 配置管理
│   ├── status.py                 # 状态追踪
│   ├── utils.py                  # 工具函数
│   └── main.py                   # 主入口
├── systemd/
│   └── mysql-log-analyzer.service
├── requirements.txt
└── setup.py
```

---

## License

MIT
