#!/usr/bin/env python3
"""MySQL 大规模压力测试 - 验证项目可行性
测试场景：
1. 并发读写压力 (1000+ QPS)
2. 大量死锁场景 (10+ 死锁)
3. 慢查询生成 (复杂 JOIN/子查询/全表扫描)
4. 连接超限/错误
5. 锁等待超时
6. 重复键/外键冲突
7. 大事务回滚
8. 临时表溢出
"""
import pymysql
import threading
import time
import random
import string
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'testuser',
    'password': 'testpass123',
    'database': 'ecommerce',
    'charset': 'utf8mb4',
    'connect_timeout': 5,
    'read_timeout': 30,
}

# 统计
stats = {
    'queries': 0,
    'errors': 0,
    'deadlocks': 0,
    'lock_timeouts': 0,
    'dup_keys': 0,
    'fk_errors': 0,
    'slow_queries': 0,
    'connections_failed': 0,
}
lock = threading.Lock()


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def prepare_test_tables():
    """准备压力测试表"""
    conn = get_conn()
    with conn.cursor() as cur:
        # 压力测试专用表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stress_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                email VARCHAR(100),
                balance DECIMAL(10,2) DEFAULT 0,
                status TINYINT DEFAULT 1,
                created_at DATETIME DEFAULT NOW(),
                INDEX idx_username (username),
                INDEX idx_status (status)
            ) ENGINE=InnoDB
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stress_orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                product_id INT NOT NULL,
                amount DECIMAL(10,2),
                status VARCHAR(20) DEFAULT 'pending',
                created_at DATETIME DEFAULT NOW(),
                INDEX idx_user (user_id),
                INDEX idx_product (product_id),
                INDEX idx_status (status)
            ) ENGINE=InnoDB
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stress_products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                price DECIMAL(10,2),
                stock INT DEFAULT 100,
                category VARCHAR(50),
                INDEX idx_category (category),
                INDEX idx_price (price)
            ) ENGINE=InnoDB
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stress_transfers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                from_user INT NOT NULL,
                to_user INT NOT NULL,
                amount DECIMAL(10,2),
                status VARCHAR(20) DEFAULT 'pending',
                created_at DATETIME DEFAULT NOW(),
                INDEX idx_from (from_user),
                INDEX idx_to (to_user)
            ) ENGINE=InnoDB
        """)

        # 插入基础数据
        cur.execute("SELECT COUNT(*) FROM stress_users")
        if cur.fetchone()[0] == 0:
            print("  插入 stress_users 数据...")
            users_data = []
            for i in range(5000):
                username = f"user_{i:05d}"
                email = f"{username}@test.com"
                balance = round(random.uniform(100, 10000), 2)
                users_data.append((username, email, balance))
            cur.executemany(
                "INSERT IGNORE INTO stress_users (username, email, balance) VALUES (%s, %s, %s)",
                users_data
            )

        cur.execute("SELECT COUNT(*) FROM stress_products")
        if cur.fetchone()[0] == 0:
            print("  插入 stress_products 数据...")
            prods_data = []
            categories = ['electronics', 'clothing', 'food', 'books', 'toys', 'sports', 'home', 'auto']
            for i in range(2000):
                name = f"product_{i:05d}"
                price = round(random.uniform(5, 500), 2)
                stock = random.randint(0, 1000)
                cat = random.choice(categories)
                prods_data.append((name, price, stock, cat))
            cur.executemany(
                "INSERT IGNORE INTO stress_products (name, price, stock, category) VALUES (%s, %s, %s, %s)",
                prods_data
            )

        cur.execute("SELECT COUNT(*) FROM stress_orders")
        if cur.fetchone()[0] == 0:
            print("  插入 stress_orders 数据...")
            orders_data = []
            statuses = ['pending', 'paid', 'shipped', 'delivered', 'cancelled']
            for i in range(20000):
                uid = random.randint(1, 5000)
                pid = random.randint(1, 2000)
                amount = round(random.uniform(5, 500), 2)
                status = random.choice(statuses)
                orders_data.append((uid, pid, amount, status))
            cur.executemany(
                "INSERT INTO stress_orders (user_id, product_id, amount, status) VALUES (%s, %s, %s, %s)",
                orders_data
            )

    conn.commit()
    conn.close()
    print("  测试表准备完成")


def scenario_concurrent_reads(thread_id, iterations):
    """场景1: 并发读查询"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for i in range(iterations):
                try:
                    query_type = random.randint(1, 6)
                    if query_type == 1:
                        cur.execute("SELECT COUNT(*) FROM stress_orders WHERE status = %s", (random.choice(['pending', 'paid', 'shipped']),))
                    elif query_type == 2:
                        cur.execute("SELECT * FROM stress_users WHERE id = %s", (random.randint(1, 5000),))
                    elif query_type == 3:
                        cur.execute("SELECT * FROM stress_products WHERE category = %s LIMIT 10", (random.choice(['electronics', 'clothing', 'food']),))
                    elif query_type == 4:
                        cur.execute("SELECT u.username, COUNT(o.id) as order_count FROM stress_users u LEFT JOIN stress_orders o ON u.id = o.user_id GROUP BY u.id LIMIT 100")
                    elif query_type == 5:
                        cur.execute("SELECT category, AVG(price), SUM(stock) FROM stress_products GROUP BY category")
                    else:
                        cur.execute("SELECT * FROM stress_orders WHERE amount > %s LIMIT 50", (random.uniform(100, 300),))
                    cur.fetchall()
                    with lock:
                        stats['queries'] += 1
                except Exception as e:
                    with lock:
                        stats['errors'] += 1
    finally:
        conn.close()


def scenario_concurrent_writes(thread_id, iterations):
    """场景2: 并发写操作"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for i in range(iterations):
                try:
                    write_type = random.randint(1, 4)
                    if write_type == 1:
                        uid = random.randint(1, 5000)
                        pid = random.randint(1, 2000)
                        amount = round(random.uniform(5, 500), 2)
                        cur.execute("INSERT INTO stress_orders (user_id, product_id, amount, status) VALUES (%s, %s, %s, 'pending')", (uid, pid, amount))
                    elif write_type == 2:
                        oid = random.randint(1, 20000)
                        cur.execute("UPDATE stress_orders SET status = 'shipped' WHERE id = %s", (oid,))
                    elif write_type == 3:
                        uid = random.randint(1, 5000)
                        delta = round(random.uniform(-50, 50), 2)
                        cur.execute("UPDATE stress_users SET balance = balance + %s WHERE id = %s", (delta, uid))
                    else:
                        pid = random.randint(1, 2000)
                        cur.execute("UPDATE stress_products SET stock = stock - 1 WHERE id = %s AND stock > 0", (pid,))
                    conn.commit()
                    with lock:
                        stats['queries'] += 1
                except pymysql.err.OperationalError as e:
                    conn.rollback()
                    with lock:
                        stats['errors'] += 1
                        if e.args[0] == 1213:
                            stats['deadlocks'] += 1
                        elif e.args[0] == 1205:
                            stats['lock_timeouts'] += 1
                except Exception:
                    conn.rollback()
                    with lock:
                        stats['errors'] += 1
    finally:
        conn.close()


def scenario_deadlock(thread_id):
    """场景3: 制造死锁 - 交叉更新用户余额"""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            # 随机选两个用户
            uid1 = random.randint(1, 5000)
            uid2 = random.randint(1, 5000)
            while uid2 == uid1:
                uid2 = random.randint(1, 5000)

            # 按线程决定锁顺序（偶数线程先锁小ID，奇数线程先锁大ID）
            if thread_id % 2 == 0:
                first, second = min(uid1, uid2), max(uid1, uid2)
            else:
                first, second = max(uid1, uid2), min(uid1, uid2)

            cur.execute("UPDATE stress_users SET balance = balance + 1 WHERE id = %s", (first,))
            time.sleep(random.uniform(0.01, 0.1))
            cur.execute("UPDATE stress_users SET balance = balance - 1 WHERE id = %s", (second,))
            conn.commit()
            with lock:
                stats['queries'] += 2
    except pymysql.err.OperationalError as e:
        try:
            conn.rollback()
        except:
            pass
        with lock:
            stats['errors'] += 1
            if e.args[0] == 1213:
                stats['deadlocks'] += 1
    except Exception:
        try:
            conn.rollback()
        except:
            pass
        with lock:
            stats['errors'] += 1
    finally:
        try:
            conn.close()
        except:
            pass


def scenario_slow_queries():
    """场景4: 生成慢查询"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 复杂 JOIN
            cur.execute("""
                SELECT u.username, COUNT(o.id) as orders, SUM(o.amount) as total,
                       p.name, p.category
                FROM stress_users u
                LEFT JOIN stress_orders o ON u.id = o.user_id
                LEFT JOIN stress_products p ON o.product_id = p.id
                GROUP BY u.id, p.id
                ORDER BY total DESC
                LIMIT 1000
            """)
            cur.fetchall()
            with lock:
                stats['queries'] += 1
                stats['slow_queries'] += 1

            # 全表扫描
            cur.execute("SELECT * FROM stress_orders WHERE amount > 10")
            cur.fetchall()
            with lock:
                stats['queries'] += 1
                stats['slow_queries'] += 1

            # 子查询
            cur.execute("""
                SELECT * FROM stress_users
                WHERE id IN (
                    SELECT user_id FROM stress_orders
                    WHERE amount > (SELECT AVG(amount) FROM stress_orders)
                )
            """)
            cur.fetchall()
            with lock:
                stats['queries'] += 1
                stats['slow_queries'] += 1

            # 笛卡尔积
            cur.execute("""
                SELECT COUNT(*) FROM stress_users u1
                CROSS JOIN stress_users u2
                LIMIT 1
            """)
            cur.fetchall()
            with lock:
                stats['queries'] += 1
                stats['slow_queries'] += 1

            # 大排序
            cur.execute("""
                SELECT * FROM stress_orders ORDER BY amount DESC LIMIT 5000
            """)
            cur.fetchall()
            with lock:
                stats['queries'] += 1
                stats['slow_queries'] += 1

    finally:
        conn.close()


def scenario_duplicate_keys():
    """场景5: 重复键错误"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for i in range(20):
                try:
                    username = f"user_{random.randint(1, 5000):05d}"
                    cur.execute(
                        "INSERT INTO stress_users (username, email, balance) VALUES (%s, %s, 0)",
                        (username, f"{username}@dup.com")
                    )
                    conn.commit()
                    with lock:
                        stats['queries'] += 1
                except pymysql.err.IntegrityError as e:
                    conn.rollback()
                    with lock:
                        stats['dup_keys'] += 1
                        stats['errors'] += 1
    finally:
        conn.close()


def scenario_connection_stress():
    """场景6: 连接压力测试"""
    errors = 0
    for i in range(50):
        try:
            c = pymysql.connect(**DB_CONFIG)
            with c.cursor() as cur:
                cur.execute("SELECT 1")
            c.close()
            with lock:
                stats['queries'] += 1
        except Exception:
            with lock:
                stats['connections_failed'] += 1
                stats['errors'] += 1
    return errors


def scenario_lock_wait_timeout():
    """场景7: 锁等待超时"""
    conn1 = get_conn()
    conn2 = get_conn()
    try:
        with conn1.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE stress_users SET balance = 999999 WHERE id = 1")
            # 不提交，持有锁

        with conn2.cursor() as cur:
            cur.execute("SET SESSION innodb_lock_wait_timeout = 2")
            try:
                cur.execute("UPDATE stress_users SET balance = 888888 WHERE id = 1")
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1205:
                    with lock:
                        stats['lock_timeouts'] += 1
                        stats['errors'] += 1
    finally:
        try:
            conn1.rollback()
            conn2.rollback()
        except:
            pass
        conn1.close()
        conn2.close()


def scenario_big_transaction_rollback():
    """场景8: 大事务回滚"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            # 插入大量数据
            for i in range(500):
                uid = random.randint(1, 5000)
                pid = random.randint(1, 2000)
                cur.execute(
                    "INSERT INTO stress_orders (user_id, product_id, amount, status) VALUES (%s, %s, %s, 'pending')",
                    (uid, pid, round(random.uniform(5, 500), 2))
                )
            # 回滚
            conn.rollback()
            with lock:
                stats['queries'] += 500
    finally:
        conn.close()


def scenario_transfer_deadlock():
    """场景9: 转账死锁 - 更真实的场景"""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            # 随机选两个用户做转账
            from_user = random.randint(1, 5000)
            to_user = random.randint(1, 5000)
            while to_user == from_user:
                to_user = random.randint(1, 5000)

            # 先锁 from_user
            cur.execute("UPDATE stress_users SET balance = balance - 10 WHERE id = %s", (from_user,))
            time.sleep(random.uniform(0.01, 0.05))
            # 再锁 to_user
            cur.execute("UPDATE stress_users SET balance = balance + 10 WHERE id = %s", (to_user,))

            # 记录转账
            cur.execute(
                "INSERT INTO stress_transfers (from_user, to_user, amount, status) VALUES (%s, %s, 10, 'completed')",
                (from_user, to_user)
            )
            conn.commit()
            with lock:
                stats['queries'] += 3
    except pymysql.err.OperationalError as e:
        try:
            conn.rollback()
        except:
            pass
        with lock:
            stats['errors'] += 1
            if e.args[0] == 1213:
                stats['deadlocks'] += 1
    except Exception:
        try:
            conn.rollback()
        except:
            pass
        with lock:
            stats['errors'] += 1
    finally:
        try:
            conn.close()
        except:
            pass


def main():
    print("=" * 60)
    print("MySQL 大规模压力测试")
    print("=" * 60)

    # 准备数据
    print("\n[1/9] 准备测试数据...")
    prepare_test_tables()

    # 确保死锁日志打印开启
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SET GLOBAL innodb_print_all_deadlocks = ON")
        cur.execute("SET GLOBAL long_query_time = 1")
    conn.close()
    print("  已开启 innodb_print_all_deadlocks 和 long_query_time=1")

    start_time = time.time()

    # 场景1: 并发读 (10线程 x 100次)
    print("\n[2/9] 并发读查询 (10线程 x 100次)...")
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(scenario_concurrent_reads, i, 100) for i in range(10)]
        for f in as_completed(futures):
            f.result()

    # 场景2: 并发写 (10线程 x 50次)
    print("[3/9] 并发写操作 (10线程 x 50次)...")
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(scenario_concurrent_writes, i, 50) for i in range(10)]
        for f in as_completed(futures):
            f.result()

    # 场景3: 死锁 (50线程并发)
    print("[4/9] 死锁场景 (50线程并发)...")
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(scenario_deadlock, i) for i in range(50)]
        for f in as_completed(futures):
            f.result()

    # 场景4: 慢查询
    print("[5/9] 慢查询生成...")
    for _ in range(5):
        scenario_slow_queries()

    # 场景5: 重复键
    print("[6/9] 重复键错误...")
    scenario_duplicate_keys()

    # 场景6: 连接压力
    print("[7/9] 连接压力测试...")
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(scenario_connection_stress) for _ in range(5)]
        for f in as_completed(futures):
            f.result()

    # 场景7: 锁等待超时
    print("[8/9] 锁等待超时...")
    for _ in range(3):
        scenario_lock_wait_timeout()

    # 场景8: 大事务回滚
    print("[9/9] 大事务回滚 + 转账死锁...")
    with ThreadPoolExecutor(max_workers=30) as pool:
        futures = [pool.submit(scenario_transfer_deadlock) for _ in range(30)]
        futures.append(pool.submit(scenario_big_transaction_rollback))
        for f in as_completed(futures):
            f.result()

    elapsed = time.time() - start_time

    # 统计结果
    print("\n" + "=" * 60)
    print("压力测试结果")
    print("=" * 60)
    print(f"  总查询数:     {stats['queries']}")
    print(f"  总错误数:     {stats['errors']}")
    print(f"  死锁次数:     {stats['deadlocks']}")
    print(f"  锁等待超时:   {stats['lock_timeouts']}")
    print(f"  重复键错误:   {stats['dup_keys']}")
    print(f"  慢查询:       {stats['slow_queries']}")
    print(f"  连接失败:     {stats['connections_failed']}")
    print(f"  耗时:         {elapsed:.1f}s")
    print(f"  QPS:          {stats['queries']/elapsed:.1f}")

    # 检查 MySQL 状态
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
        slow = cur.fetchone()[1]
        cur.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
        threads = cur.fetchone()[1]
        cur.execute("SHOW GLOBAL STATUS LIKE 'Innodb_row_lock_waits'")
        lock_waits = cur.fetchone()[1]
        cur.execute("SHOW GLOBAL STATUS LIKE 'Uptime'")
        uptime = cur.fetchone()[1]
    conn.close()

    print(f"\nMySQL 全局状态:")
    print(f"  慢查询总数:   {slow}")
    print(f"  当前连接数:   {threads}")
    print(f"  行锁等待:     {lock_waits}")
    print(f"  运行时间:     {uptime}s")

    # 检查错误日志中的死锁
    try:
        with open('/var/log/mysql/error.log', 'r') as f:
            content = f.read()
        deadlock_count = content.count('LATEST DETECTED DEADLOCK')
        error_count = content.count('[ERROR]')
        warning_count = content.count('[Warning]')
        print(f"\nMySQL 错误日志:")
        print(f"  死锁事件:     {deadlock_count}")
        print(f"  ERROR:        {error_count}")
        print(f"  Warning:      {warning_count}")
    except Exception as e:
        print(f"  读取日志失败: {e}")

    print("\n压力测试完成！")


if __name__ == '__main__':
    main()
