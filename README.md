<p align="center">
  <h1 align="center">DB Ops Analyzer</h1>
  <p align="center">数据库运维自动分析平台 — MySQL + Redis</p>
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.104+-teal" alt="FastAPI">
    <img src="https://img.shields.io/badge/Vue3-3.x-brightgreen" alt="Vue3">
    <img src="https://img.shields.io/badge/MySQL-8.0+-orange" alt="MySQL">
    <img src="https://img.shields.io/badge/Redis-6.0+-red" alt="Redis">
    <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
  </p>
</p>

---

## 项目简介

**DB Ops Analyzer** 是一个功能完整的数据库运维自动分析平台，支持 **MySQL** 和 **Redis** 两种数据库。放入任何有 MySQL/Redis 的环境中，它能主动发现实例并进行深度分析，提供 CLI 对话和 Web 可视化两种交互方式。已在真实 MySQL 8.0 和 Redis 7.0 环境下通过端到端验证。

### 核心特性

- 🔍 **自动发现** — 自动检测本机 MySQL/Redis 实例，支持多实例同时监控
- 🤖 **AI 分析** — 基于 LangGraph 多节点工作流，支持 OpenAI / Ollama / 自定义端点
- 💬 **智能对话** — CLI 自然语言对话，RAG 增强检索相关日志上下文
- 📊 **可视化** — Web 界面提供 SVG 力导向知识图谱、仪表盘、监控面板等多种可视化
- 🔎 **全文本搜索** — 支持简单/正则/模糊搜索，高亮显示、评分排序、上下文查看
- 🚨 **智能告警** — 规则引擎 + 5 种通知渠道（Webhook/Email/钉钉/飞书/Slack）
- 🔗 **死锁分析** — InnoDB 死锁日志解析、锁等待链有向图、DFS 环检测、根因分析
- 📈 **性能基线** — 自动构建 hourly/daily/weekly 基线，标准差偏离异常检测
- 🏢 **多实例管理** — 实例 CRUD、连接测试、分组管理、统一概览（MySQL + Redis）
- 📋 **运维报表** — 日报/周报/月报自动生成，健康评分算法
- 🔍 **模式识别** — 日志模板聚类、异常检测（突增/新模式/递增趋势）
- ⏱️ **实时监控** — MySQL: QPS/TPS/连接数/Buffer Pool；Redis: QPS/内存/命中率/淘汰
- 💾 **Redis 内存分析** — 碎片率、淘汰策略、内存组成、峰值追踪
- 🔑 **Redis Key 分析** — 大 Key 扫描、Key 空间分布、过期分析（手动触发）
- 💿 **Redis 持久化** — RDB/AOF 状态监控、fork 耗时、重写进度
- 🌐 **Redis 集群/哨兵** — Cluster 节点状态、槽分配、Sentinel 主从监控
- 🔒 **安全** — 默认本地监听，JWT 认证
- 🐳 **灵活部署** — Python 直接运行 / Docker / systemd 常驻

---

## 架构设计

```
┌──────────────────────────────────────────────────────────────────┐
│                        Web 可视化层                               │
│   Vue3 + SVG 力导向图谱（仪表盘/图谱/对话/监控/告警/搜索/报表）    │
├──────────────────────────────────────────────────────────────────┤
│                        API 服务层                                 │
│        FastAPI（15 组 REST API + WebSocket + JWT 认证）           │
├──────────────────────────────────────────────────────────────────┤
│                      LangGraph 分析引擎                           │
│   解析 → 分类 → 关联分析 → 摘要生成 → 对话（RAG 增强）            │
├───────────┬──────────┬──────────┬──────────┬─────────────────────┤
│  日志采集  │ 实时监控  │ 死锁分析  │ 告警引擎  │  向量搜索（可选）   │
│ 发现/读取  │ SHOW      │ 锁等待链  │ 规则评估  │  Embedding +       │
│ 解析/监控  │ STATUS    │ DFS 环检  │ 多通道    │  turbovec 语义搜索 │
│           │ PROCESSLIST│ 根因分析  │ 通知推送  │  RAG 增强          │
├───────────┴──────────┴──────────┴──────────┴─────────────────────┤
│                        数据存储层                                  │
│              SQLite（日志/分析/告警/监控/基线/死锁/报表）           │
└──────────────────────────────────────────────────────────────────┘
```

### 模块说明

| 模块 | 路径 | 功能 |
|------|------|------|
| 配置管理 | `src/config.py` | YAML 配置加载，环境变量覆盖，默认值合并 |
| 日志采集 | `src/collector/` | 自动发现 MySQL 实例，日志解析，流式读取，watchdog 监控 |
| MySQL 连接 | `src/collector/mysql_connector.py` | pymysql 连接器，SHOW STATUS/PROCESSLIST/SLAVE STATUS |
| Redis 连接 | `src/collector/redis_connector.py` | redis-py 异步连接器，INFO/SLOWLOG/CLIENT/LATENCY/MEMORY/CLUSTER |
| 慢查询解析 | `src/collector/slow_query_parser.py` | 旧格式 + MySQL 5.6+ 新格式慢查询日志解析 |
| 分析引擎 | `src/analyzer/` | LangGraph 工作流（5 节点），LLM 接口（多提供商） |
| 死锁分析 | `src/analyzer/deadlock_analyzer.py` | InnoDB 死锁日志解析、锁等待链有向图、DFS 环检测、根因分析 |
| 模式识别 | `src/analyzer/pattern_recognizer.py` | 日志模板聚类、变量替换、异常检测 |
| 性能基线 | `src/analyzer/baseline.py` | hourly/daily/weekly 基线构建、标准差偏离检测 |
| 报表生成 | `src/analyzer/report_generator.py` | 日报/周报/月报、健康评分算法（100 分扣减制） |
| 向量搜索 | `src/vector/` | Embedding 管理，turbovec 索引，语义搜索，RAG |
| 数据存储 | `src/storage/` | SQLite 异步操作，多张表，丰富查询方法 |
| 告警引擎 | `src/web/api/alert_engine.py` | 规则 CRUD、7 种条件、5 种通知渠道、SMTP 邮件 |
| Redis 监控 | `src/web/api/redis_monitor.py` | Redis 实时指标、客户端、复制、持久化、延迟 |
| Redis 慢查询 | `src/web/api/redis_slowlog.py` | SLOWLOG 解析、统计、配置 |
| Redis 分析 | `src/web/api/redis_analysis.py` | 内存分析、Key 扫描、Key 空间、持久化详情 |
| Redis 集群 | `src/web/api/redis_cluster.py` | Cluster 节点/槽信息、Sentinel 主从监控 |
| Web 后端 | `src/web/` | FastAPI + 15 组 REST API + WebSocket + JWT |
| Web 前端 | `frontend/` | Vue3 + SVG 力导向图谱，22 个可视化组件 |

---

## 功能详情

### P0 核心功能

#### 1. 智能告警引擎

- **规则管理**：创建/更新/删除/启停告警规则
- **7 种条件**：gt / gte / lt / lte / eq / ne / increase_rate
- **5 种通知渠道**：Webhook / Email（SMTP）/ 钉钉 / 飞书 / Slack
- **SMTP 邮件**：支持 SSL/STARTTLS，HTML 格式告警邮件
- **指标采集**：按时间窗口查询 log_entries / slow_queries / monitor_metrics

#### 2. 日志模式识别

- **模板聚类**：将变量部分（IP/数字/路径/UUID/时间戳等）替换为通配符 `*`
- **异常检测**：
  - 突增检测（> 3x 平均值）
  - 新模式检测（首次出现的模式）
  - 递增趋势检测

#### 3. 全文本搜索

- **3 种搜索模式**：简单搜索 / 正则搜索 / 模糊搜索
- **高亮显示**：搜索关键词在结果中高亮标记
- **评分排序**：基于匹配度评分排序
- **上下文查看**：查看某条日志的前后上下文
- **搜索建议**：输入时自动补全建议

### P1 高级功能

#### 4. InnoDB 死锁深度分析

- **日志解析**：从 MySQL 错误日志中提取完整死锁块（多行）
- **锁等待链**：构建有向图，提取事务间等待关系
- **DFS 环检测**：检测锁等待链中的循环依赖
- **根因分析**：
  - GAP 锁竞争
  - 跨表依赖死锁
  - 索引设计问题
  - 行级竞争死锁
- **索引建议**：分析 WHERE 条件列，建议添加复合索引
- **严重程度评估**：low / medium / high / critical

#### 5. 性能基线与异常检测

- **3 种基线周期**：hourly / daily / weekly
- **标准差偏离检测**：> 2σ / 2.5σ / 3σ 三级异常
- **指标预测**：基于小时基线预测未来值
- **概览视图**：所有指标的基线状态总览

#### 6. 多实例统一管理

- **实例 CRUD**：注册/更新/删除 MySQL 实例
- **连接测试**：验证实例连接，自动更新状态
- **凭据管理**：安全存储连接凭据（密码脱敏显示）
- **分组管理**：按组管理实例，配置分组告警
- **统一概览**：所有实例的健康状态、错误/警告计数
- **手动采集**：触发指定实例的日志采集

#### 7. 定期运维报表

- **3 种报表类型**：日报 / 周报 / 月报
- **健康评分算法**：基础 100 分，扣减制
  - critical 错误 -5/条
  - warning 错误 -2/条
  - critical 告警 -10/条
  - warning 告警 -5/条
  - 慢查询 -3/条（上限 -30）
- **报表内容**：错误统计、慢查询 Top、死锁事件、告警汇总、优化建议

### 实时监控

| 指标 | 来源 |
|------|------|
| QPS（每秒查询数） | SHOW GLOBAL STATUS → Queries / Uptime |
| TPS（每秒事务数） | SHOW GLOBAL STATUS → (Com_commit + Com_rollback) / Uptime |
| 连接数 | Threads_connected / Max_used_connections |
| Buffer Pool 命中率 | (read_requests - reads) / read_requests × 100% |
| InnoDB 行锁等待 | Innodb_row_lock_waits / avg_time / total_time |
| 慢查询数 | Slow_queries |
| 进程列表 | SHOW FULL PROCESSLIST |
| 复制状态 | SHOW MASTER/SLAVE STATUS |
| InnoDB 引擎状态 | SHOW ENGINE INNODB STATUS |

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
- MySQL 5.7+ / 8.0+（本机或远程）
- Node.js 18+（前端开发，可选）

### 安装

```bash
# 克隆仓库
git clone https://github.com/yumeng001yu/mysql-error-log-analyzer.git
cd mysql-error-log-analyzer

# 安装 Python 依赖
pip install -r requirements.txt

# 前端构建（可选，已包含预构建产物）
cd frontend && npm install && npm run build && cd ..

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

# MySQL 实例配置（可选，支持自动发现）
mysql:
  instances:
    - name: "production"
      host: "localhost"
      port: 3306
      user: "root"
      password: ""
      log_path: "/var/log/mysql/error.log"
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

# 或直接使用 uvicorn
uvicorn src.web.app:app --host 0.0.0.0 --port 8080
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

### 基础 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/auth/login` | 登录认证 |

### 日志与分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs` | 查询日志列表 |
| GET | `/api/logs/stats` | 日志统计 |
| GET | `/api/logs/distribution` | 错误分布 |
| GET | `/api/logs/trend` | 错误趋势 |
| POST | `/api/analysis/run` | 触发分析 |
| GET | `/api/analysis/results` | 获取分析结果 |
| POST | `/api/chat` | AI 对话 |

### 实时监控

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/monitor/status` | MySQL 实时状态指标 |
| GET | `/api/monitor/processlist` | 进程列表 |
| GET | `/api/monitor/innodb` | InnoDB 引擎状态 |
| GET | `/api/monitor/replication` | 主从复制状态 |
| GET | `/api/monitor/history` | 历史监控数据 |
| POST | `/api/monitor/test-connection` | 测试 MySQL 连接 |

### 智能告警

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alerts/rules` | 告警规则列表 |
| POST | `/api/alerts/rules` | 创建告警规则 |
| PUT | `/api/alerts/rules/{id}` | 更新告警规则 |
| DELETE | `/api/alerts/rules/{id}` | 删除告警规则 |
| GET | `/api/alerts/history` | 告警历史 |
| GET | `/api/alerts/stats` | 告警统计 |
| GET | `/api/alerts/channels` | 通知渠道列表 |
| POST | `/api/alerts/channels` | 创建通知渠道 |
| POST | `/api/alerts/check` | 手动触发告警检查 |

### 全文本搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search/` | 搜索（简单/正则/模糊） |
| GET | `/api/search/suggestions` | 搜索建议 |
| GET | `/api/search/context/{id}` | 查看上下文 |
| GET | `/api/search/fields` | 可搜索字段列表 |

### 模式识别

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/patterns/recognize` | 识别日志模式 |
| GET | `/api/patterns/anomalies` | 异常模式列表 |
| GET | `/api/patterns/stats` | 模式统计 |
| GET | `/api/patterns/trend` | 模式趋势 |

### 死锁分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/deadlock/list` | 死锁事件列表 |
| GET | `/api/deadlock/{id}` | 死锁详情 |
| GET | `/api/deadlock/stats` | 死锁统计 |
| POST | `/api/deadlock/analyze` | 手动触发死锁分析 |
| GET | `/api/deadlock/lock-chain/{id}` | 锁等待链可视化数据 |

### 性能基线

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/baseline/build` | 构建基线 |
| GET | `/api/baseline/anomalies` | 异常检测 |
| GET | `/api/baseline/list` | 基线列表 |
| GET | `/api/baseline/forecast` | 指标预测 |
| GET | `/api/baseline/overview` | 基线概览 |

### 多实例管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/instances/` | 实例列表 |
| POST | `/api/instances/` | 注册实例 |
| PUT | `/api/instances/{id}` | 更新实例 |
| DELETE | `/api/instances/{id}` | 删除实例 |
| POST | `/api/instances/{id}/test` | 测试连接 |
| GET | `/api/instances/{id}/status` | 实例状态 |
| POST | `/api/instances/{id}/collect` | 手动采集日志 |
| GET | `/api/instances/overview` | 统一概览 |
| GET | `/api/instances/groups` | 分组列表 |

### 运维报表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/reports/generate` | 生成报表 |
| GET | `/api/reports/list` | 报表列表 |
| GET | `/api/reports/{id}` | 报表详情 |
| DELETE | `/api/reports/{id}` | 删除报表 |
| GET | `/api/reports/latest` | 最新报表 |

### 慢查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/slow-query/list` | 慢查询列表 |
| GET | `/api/slow-query/stats` | 慢查询统计 |

### Redis 监控

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/redis/status` | Redis 实时状态指标 |
| GET | `/api/redis/clients` | 客户端连接列表 |
| GET | `/api/redis/replication` | 复制状态 |
| GET | `/api/redis/persistence` | 持久化状态 |
| GET | `/api/redis/config` | 配置信息 |
| GET | `/api/redis/latency` | 延迟事件 |
| POST | `/api/redis/test-connection` | 测试连接 |

### Redis 慢查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/redis/slowlog/` | 慢查询列表 |
| GET | `/api/redis/slowlog/stats` | 慢查询统计 |
| GET | `/api/redis/slowlog/config` | 慢查询配置 |

### Redis 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/redis/memory` | 内存详细分析 |
| POST | `/api/redis/keys/scan` | 扫描 Key（手动触发） |
| GET | `/api/redis/keys/top` | 大 Key 排行 |
| GET | `/api/redis/keyspace` | Key 空间分布 |
| GET | `/api/redis/key/{key}` | 单个 Key 详情 |
| GET | `/api/redis/persistence/detail` | 持久化详细状态 |

### Redis 集群/哨兵

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/redis/cluster/info` | 集群状态概览 |
| GET | `/api/redis/cluster/nodes` | 集群节点列表 |
| GET | `/api/redis/sentinel/masters` | Sentinel 主节点 |
| GET | `/api/redis/sentinel/slaves` | Sentinel 从节点 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/alerts` | 实时告警推送 |
| `/ws/status` | 实时状态推送 |

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI + Starlette | 异步、自带 API 文档、WebSocket |
| AI 编排 | LangGraph | 有状态多步骤工作流 |
| LLM 接口 | LangChain | 统一多模型接口 |
| MySQL 连接 | pymysql | 同步包装为异步（asyncio.to_thread） |
| 向量索引 | turbovec | 4bit 量化，内存节省 8 倍 |
| 数据存储 | SQLite (aiosqlite) | 零配置、单文件部署、异步操作 |
| 前端 | Vue3 + SVG 力导向图谱 | 深色主题、响应式布局、移动端适配 |
| 日志监控 | watchdog | Python 文件监控库 |
| 邮件通知 | smtplib + MIMEText | SMTP_SSL / STARTTLS |
| 部署 | Docker / systemd | 灵活部署方式 |

---

## 项目结构

```
mysql-error-log-analyzer/
├── config/
│   └── config.yaml.example          # 配置模板
├── docker/
│   ├── Dockerfile                    # Docker 镜像
│   └── docker-compose.yaml           # 编排配置
├── frontend/
│   └── src/
│       ├── components/               # Vue3 组件（22 个）
│       │   ├── Home.vue              # 首页（MySQL/Redis 卡片入口）
│       │   ├── Dashboard.vue         # MySQL 仪表盘
│       │   ├── LogQuery.vue          # 日志查询
│       │   ├── AnalysisReport.vue    # 分析报告
│       │   ├── KnowledgeGraph.vue    # SVG 力导向知识图谱
│       │   ├── ChatPanel.vue         # AI 对话
│       │   ├── StatusPanel.vue       # 系统状态
│       │   ├── MonitorPanel.vue      # MySQL 实时监控
│       │   ├── SlowQuery.vue         # MySQL 慢查询分析
│       │   ├── AlertPanel.vue        # 智能告警
│       │   ├── LogSearch.vue         # 全文本搜索
│       │   ├── PatternPanel.vue      # 模式识别
│       │   ├── DeadlockPanel.vue     # 死锁分析（SVG 锁等待链）
│       │   ├── BaselinePanel.vue     # 性能基线
│       │   ├── InstancesPanel.vue    # 多实例管理
│       │   ├── ReportPanel.vue       # 运维报表
│       │   ├── SettingsPanel.vue     # 设置页面
│       │   ├── ReplicationPanel.vue  # 复制状态
│       │   ├── LoginPage.vue         # 登录页
│       │   ├── RedisMonitor.vue      # Redis 实时监控
│       │   ├── RedisSlowlog.vue      # Redis 慢查询
│       │   ├── RedisMemory.vue       # Redis 内存分析
│       │   ├── RedisKeys.vue         # Redis Key 分析
│       │   ├── RedisPersistence.vue  # Redis 持久化
│       │   └── RedisCluster.vue      # Redis 集群/哨兵
│       ├── api.js                    # API 封装
│       ├── router.js                 # 路由配置
│       └── main.js                   # 入口
├── scripts/
│   ├── e2e_test.py                   # 端到端验证测试
│   ├── stress_test.py                # 压力测试
│   ├── create_real_deadlocks.py      # 死锁场景生成
│   └── generate_test_errors.py       # 测试错误生成
├── src/
│   ├── analyzer/                     # 分析引擎
│   │   ├── graph.py                  # LangGraph 工作流
│   │   ├── llm.py                    # LLM 接口
│   │   ├── nodes/                    # 工作流节点
│   │   ├── deadlock_analyzer.py      # 死锁深度分析
│   │   ├── pattern_recognizer.py     # 模式识别
│   │   ├── baseline.py               # 性能基线
│   │   └── report_generator.py       # 运维报表生成
│   ├── cli/                          # CLI 界面
│   ├── collector/                    # 日志采集
│   │   ├── discover.py               # 实例发现
│   │   ├── parser.py                 # 日志解析
│   │   ├── reader.py                 # 流式读取
│   │   ├── watcher.py                # 文件监控
│   │   ├── mysql_connector.py        # MySQL 连接器
│   │   └── slow_query_parser.py      # 慢查询解析
│   ├── notifier/                     # 通知推送
│   ├── storage/                      # 数据存储
│   ├── vector/                       # 向量搜索
│   ├── web/                          # Web 后端
│   │   ├── app.py                    # FastAPI 应用 + SPA fallback
│   │   └── api/                      # API 路由
│   │       ├── auth.py               # JWT 认证
│   │       ├── logs.py               # 日志查询
│   │       ├── analysis.py           # 分析引擎
│   │       ├── status.py             # 系统状态
│   │       ├── monitor.py            # 实时监控
│   │       ├── slow_query.py         # 慢查询
│   │       ├── alert_engine.py       # 告警引擎核心
│   │       ├── alerts.py             # 告警 API
│   │       ├── search.py             # 全文本搜索
│   │       ├── patterns.py           # 模式识别
│   │       ├── deadlock.py           # 死锁分析
│   │       ├── baseline.py           # 性能基线
│   │       ├── instances.py          # 多实例管理
│   │       ├── reports.py            # 运维报表
│   │       ├── settings.py           # 设置
│   │       ├── redis_monitor.py      # Redis 监控
│   │       ├── redis_slowlog.py      # Redis 慢查询
│   │       ├── redis_analysis.py     # Redis 内存/Key/持久化
│   │       └── redis_cluster.py      # Redis 集群/哨兵
│   ├── config.py                     # 配置管理
│   ├── status.py                     # 状态追踪
│   ├── utils.py                      # 工具函数
│   └── main.py                       # 主入口
├── systemd/
│   └── mysql-log-analyzer.service
├── requirements.txt
└── setup.py
```

---

## 验证结果

在真实 MySQL 8.0.46 和 Redis 7.0.15 环境下通过完整端到端验证：

### MySQL 验证（45/45 通过）

| 测试类别 | 通过 |
|----------|------|
| 基础服务 | 1/1 |
| 监控指标采集 | 6/6 |
| 进程列表 | 2/2 |
| InnoDB 状态 | 2/2 |
| 复制状态 | 1/1 |
| 日志采集与统计 | 3/3 |
| 全文本搜索 | 5/5 |
| 模式识别 | 3/3 |
| 死锁分析 | 4/4 |
| 智能告警 | 5/5 |
| 性能基线 | 4/4 |
| 多实例管理 | 5/5 |
| 运维报表 | 2/2 |
| 慢查询分析 | 1/1 |
| 分析与知识图谱 | 1/1 |

### Redis 验证

| 测试类别 | 结果 |
|----------|------|
| 实例注册（db_type=redis） | ✓ |
| 连接测试（7.0.15 standalone） | ✓ |
| 实时监控（QPS/内存/连接数/命中率/淘汰） | ✓ |
| 慢查询列表（命令/耗时/客户端） | ✓ |
| 慢查询统计（命令分布/平均耗时） | ✓ |
| 客户端列表 | ✓ |
| 复制状态 | ✓ |
| 持久化状态 | ✓ |
| 延迟事件 | ✓ |
| 配置查询 | ✓ |
| 内存分析（碎片率/淘汰策略/组成） | ✓ |
| Key 空间分布 | ✓ |
| Top Keys | ✓ |
| Key 扫描（1000 Key，0.06s） | ✓ |
| 单个 Key 详情 | ✓ |
| 持久化详情（RDB/AOF/建议） | ✓ |
| 集群信息（standalone 模式正确返回） | ✓ |
| Sentinel 信息（standalone 模式正确返回） | ✓ |

压力测试数据：MySQL 2,485 次查询（QPS 108.7），97 次死锁触发，12 个死锁事件成功解析。

---

## License

MIT
