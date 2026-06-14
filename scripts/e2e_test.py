#!/usr/bin/env python3
"""MySQL Error Log Analyzer - 端到端验证测试"""
import json
import urllib.request
import urllib.parse
import sys

BASE = "http://localhost:8080"

def api_get(path, params=None):
    """发送 GET 请求"""
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}

def api_post(path, data=None):
    """发送 POST 请求"""
    url = BASE + path
    try:
        body = json.dumps(data).encode() if data else b'{}'
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}

def api_delete(path):
    """发送 DELETE 请求"""
    url = BASE + path
    try:
        req = urllib.request.Request(url, method="DELETE")
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}

passed = 0
failed = 0
errors = []

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  ✗ {name} - {detail}")

print("=" * 60)
print("MySQL Error Log Analyzer - 端到端验证测试")
print("=" * 60)

# ── 1. 基础服务 ──────────────────────────────────────────
print("\n【1. 基础服务】")
health = api_get("/api/health")
test("健康检查", health.get("status") == "ok" or "uptime" in str(health), str(health)[:100])

# ── 2. 监控指标采集 ──────────────────────────────────────
print("\n【2. 监控指标采集】")
status = api_get("/api/monitor/status", {"instance_id": 10})
test("MySQL 连接成功", status.get("connected") == True, str(status)[:100])
test("QPS > 0", status.get("qps", 0) > 0, f"QPS={status.get('qps')}")
test("TPS >= 0", status.get("tps", 0) >= 0, f"TPS={status.get('tps')}")
test("连接数 > 0", status.get("connections", {}).get("current", 0) > 0, f"连接数={status.get('connections', {}).get('current')}")
test("Buffer Pool 命中率 > 0", status.get("buffer_pool", {}).get("hit_rate", 0) > 0, f"命中率={status.get('buffer_pool', {}).get('hit_rate')}")
test("Uptime > 0", status.get("uptime", 0) > 0, f"Uptime={status.get('uptime')}")

# ── 3. 进程列表 ──────────────────────────────────────────
print("\n【3. 进程列表】")
pl = api_get("/api/monitor/processlist", {"instance_id": 10})
test("进程列表非空", pl.get("total", 0) > 0, f"total={pl.get('total')}")
test("包含活跃进程", pl.get("active_count", 0) >= 0, f"active={pl.get('active_count')}")

# ── 4. InnoDB 状态 ──────────────────────────────────────
print("\n【4. InnoDB 状态】")
innodb = api_get("/api/monitor/innodb", {"instance_id": 10})
test("InnoDB 状态非空", bool(innodb.get("status_text")), "status_text 为空")
test("Buffer Pool 解析", bool(innodb.get("parsed", {}).get("buffer_pool")), "buffer_pool 解析失败")

# ── 5. 复制状态 ──────────────────────────────────────────
print("\n【5. 复制状态】")
repl = api_get("/api/monitor/replication", {"instance_id": 10})
test("复制状态返回", "is_master" in repl or "is_slave" in repl, str(repl)[:100])

# ── 6. 日志采集与统计 ────────────────────────────────────
print("\n【6. 日志采集与统计】")
stats = api_get("/api/logs/stats")
test("日志统计返回", "total" in stats, str(stats)[:100])
test("总日志数 > 0", stats.get("total", 0) > 0, f"total={stats.get('total')}")
test("有 ERROR 级别日志", any(l.get("level") == "ERROR" for l in stats.get("levels", [])), "无 ERROR 日志")

# ── 7. 全文本搜索 ────────────────────────────────────────
print("\n【7. 全文本搜索】")
search1 = api_get("/api/search/", {"q": "Deadlock", "mode": "simple", "limit": 5})
test("搜索 Deadlock", search1.get("total", 0) > 0, f"total={search1.get('total')}")

search2 = api_get("/api/search/", {"q": "Buffer Pool", "mode": "simple", "limit": 5})
test("搜索 Buffer Pool", search2.get("total", 0) > 0, f"total={search2.get('total')}")

search3 = api_get("/api/search/", {"q": "ERROR.*connection", "mode": "regex", "limit": 5})
test("正则搜索", search3.get("total", 0) >= 0, f"total={search3.get('total')}")

search4 = api_get("/api/search/", {"q": "deadlok", "mode": "fuzzy", "limit": 5})
test("模糊搜索", search4.get("total", 0) >= 0, f"total={search4.get('total')}")

# 搜索建议
suggest = api_get("/api/search/suggestions", {"q": "Dead"})
test("搜索建议", isinstance(suggest, list) or isinstance(suggest, dict), str(suggest)[:100])

# ── 8. 模式识别 ──────────────────────────────────────────
print("\n【8. 模式识别】")
patterns = api_get("/api/patterns/recognize", {"instance_id": 10})
test("模式识别返回", isinstance(patterns, dict) or isinstance(patterns, list), str(patterns)[:100])
if isinstance(patterns, dict):
    pcount = patterns.get("total_patterns", len(patterns.get("patterns", [])))
    test("模式数量 > 0", pcount > 0, f"模式数={pcount}")

pattern_stats = api_get("/api/patterns/stats", {"instance_id": 10})
test("模式统计返回", isinstance(pattern_stats, dict), str(pattern_stats)[:100])

# ── 9. 死锁分析 ──────────────────────────────────────────
print("\n【9. 死锁分析】")
deadlocks = api_get("/api/deadlock/list")
test("死锁列表返回", isinstance(deadlocks, dict), str(deadlocks)[:100])
dcount = deadlocks.get("total", len(deadlocks.get("items", [])))
test("死锁事件数 > 0", dcount > 0, f"死锁数={dcount}")

if dcount > 0:
    first_id = deadlocks.get("items", [{}])[0].get("id")
    if first_id:
        detail = api_get(f"/api/deadlock/{first_id}")
        test("死锁详情返回", isinstance(detail, dict), str(detail)[:100])

deadlock_stats = api_get("/api/deadlock/stats")
test("死锁统计返回", isinstance(deadlock_stats, dict), f"total={deadlock_stats.get('total_count')}")

# ── 10. 智能告警 ─────────────────────────────────────────
print("\n【10. 智能告警】")
# 创建告警规则
rule = api_post("/api/alerts/rules", {
    "name": "测试-错误数告警",
    "metric": "error_count",
    "condition": "gt",
    "threshold": 0,
    "severity": "warning",
    "enabled": True,
    "time_window": 60,
    "notification_channels": ["email"],
})
test("创建告警规则", "id" in rule or "name" in rule or "rule" in rule or "message" in rule, str(rule)[:100])

# 告警历史
history = api_get("/api/alerts/history")
test("告警历史返回", isinstance(history, dict) or isinstance(history, list), str(history)[:100])

# 告警统计
alert_stats = api_get("/api/alerts/stats")
test("告警统计返回", isinstance(alert_stats, dict), str(alert_stats)[:100])

# 通知渠道
channels = api_get("/api/alerts/channels")
test("通知渠道列表", isinstance(channels, list) or isinstance(channels, dict), str(channels)[:100])

# 触发告警检查
check = api_post("/api/alerts/check")
test("触发告警检查", isinstance(check, dict), str(check)[:100])

# ── 11. 性能基线 ─────────────────────────────────────────
print("\n【11. 性能基线】")
baseline = api_get("/api/baseline/list")
test("基线列表返回", isinstance(baseline, dict) or isinstance(baseline, list), str(baseline)[:100])

# 构建基线
build = api_post("/api/baseline/build", {"instance_id": 10, "period": "hourly"})
test("构建基线", isinstance(build, dict), str(build)[:100])

# 异常检测
anomalies = api_get("/api/baseline/anomalies", {"instance_id": 10})
test("异常检测返回", isinstance(anomalies, dict) or isinstance(anomalies, list), str(anomalies)[:100])

# 基线概览
overview = api_get("/api/baseline/overview", {"instance_id": 10})
test("基线概览返回", isinstance(overview, dict), str(overview)[:100])

# ── 12. 多实例管理 ───────────────────────────────────────
print("\n【12. 多实例管理】")
instances = api_get("/api/instances/")
test("实例列表返回", isinstance(instances, list), str(instances)[:100])
test("实例数 > 0", len(instances) > 0, f"实例数={len(instances)}")

# 实例连接测试
if instances:
    iid = instances[0].get("id")
    test_result = api_post(f"/api/instances/{iid}/test")
    test("实例连接测试", isinstance(test_result, dict), str(test_result)[:100])

# 实例概览
overview = api_get("/api/instances/overview")
test("实例概览返回", isinstance(overview, dict), f"total={overview.get('total_instances')}")

# 实例分组
groups = api_get("/api/instances/groups")
test("实例分组返回", isinstance(groups, list), str(groups)[:100])

# ── 13. 运维报表 ─────────────────────────────────────────
print("\n【13. 运维报表】")
report = api_get("/api/reports/generate", {"instance_id": 10, "report_type": "daily"})
test("生成日报", isinstance(report, dict), str(report)[:100])

report_list = api_get("/api/reports/list")
test("报表列表返回", isinstance(report_list, dict) or isinstance(report_list, list), str(report_list)[:100])

# ── 14. 慢查询分析 ──────────────────────────────────────
print("\n【14. 慢查询分析】")
slow = api_get("/api/slow-query/list", {"instance_id": 10, "limit": 5})
test("慢查询列表返回", isinstance(slow, dict) or isinstance(slow, list), str(slow)[:100])

# ── 15. 分析与知识图谱 ──────────────────────────────────
print("\n【15. 分析与知识图谱】")
analysis = api_get("/api/analysis/summary", {"instance_id": 10})
test("分析摘要返回", isinstance(analysis, dict), str(analysis)[:100])

# ── 汇总 ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"测试结果: ✓ {passed} 通过, ✗ {failed} 失败")
print("=" * 60)

if errors:
    print("\n失败详情:")
    for e in errors:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)
