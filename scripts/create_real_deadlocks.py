#!/usr/bin/env python3
"""生成真实 MySQL 死锁场景"""
import pymysql
import threading
import time
import sys

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'testuser',
    'password': 'testpass123',
    'database': 'ecommerce',
    'charset': 'utf8mb4',
}

def prepare_data():
    """准备测试数据"""
    conn = pymysql.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deadlock_test (
                id INT PRIMARY KEY,
                value INT,
                name VARCHAR(50)
            ) ENGINE=InnoDB
        """)
        cur.execute("INSERT IGNORE INTO deadlock_test VALUES (1, 100, 'row1'), (2, 200, 'row2')")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deadlock_test2 (
                id INT PRIMARY KEY,
                value INT,
                name VARCHAR(50)
            ) ENGINE=InnoDB
        """)
        cur.execute("INSERT IGNORE INTO deadlock_test2 VALUES (1, 100, 'row1'), (2, 200, 'row2')")
    conn.commit()
    conn.close()
    print("测试数据准备完成")

def deadlock_scenario_1(result):
    """场景1: 同表交叉行锁死锁"""
    try:
        # 事务1: 锁 row1 -> 等 row2
        conn1 = pymysql.connect(**DB_CONFIG)
        conn2 = pymysql.connect(**DB_CONFIG)

        with conn1.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE deadlock_test SET value=value+1 WHERE id=1")

        # 信号: 事务1已锁row1
        result['t1_ready'].set()

        # 等事务2锁row2
        result['t2_ready'].wait()

        # 事务1尝试锁row2 -> 死锁!
        with conn1.cursor() as cur:
            cur.execute("UPDATE deadlock_test SET value=value+1 WHERE id=2")

        conn1.commit()
        result['t1_result'] = 'success'
    except Exception as e:
        result['t1_result'] = f'deadlock: {e}'
        try:
            conn1.rollback()
        except:
            pass
    finally:
        try:
            conn1.close()
            conn2.close()
        except:
            pass

def deadlock_thread_2(result):
    """场景1: 事务2"""
    try:
        conn = pymysql.connect(**DB_CONFIG)

        # 等事务1锁row1
        result['t1_ready'].wait()

        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE deadlock_test SET value=value+1 WHERE id=2")

        # 信号: 事务2已锁row2
        result['t2_ready'].set()

        time.sleep(0.3)

        # 事务2尝试锁row1 -> 死锁!
        with conn.cursor() as cur:
            cur.execute("UPDATE deadlock_test SET value=value+1 WHERE id=1")

        conn.commit()
        result['t2_result'] = 'success'
    except Exception as e:
        result['t2_result'] = f'deadlock: {e}'
        try:
            conn.rollback()
        except:
            pass
    finally:
        try:
            conn.close()
        except:
            pass

def deadlock_scenario_2(result):
    """场景2: 跨表死锁"""
    try:
        conn1 = pymysql.connect(**DB_CONFIG)

        with conn1.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE deadlock_test SET value=value+1 WHERE id=1")

        result['s2_t1_ready'].set()
        result['s2_t2_ready'].wait()

        with conn1.cursor() as cur:
            cur.execute("UPDATE deadlock_test2 SET value=value+1 WHERE id=1")

        conn1.commit()
        result['s2_t1_result'] = 'success'
    except Exception as e:
        result['s2_t1_result'] = f'deadlock: {e}'
        try:
            conn1.rollback()
        except:
            pass
    finally:
        try:
            conn1.close()
        except:
            pass

def deadlock_thread_2_s2(result):
    """场景2: 事务2"""
    try:
        conn = pymysql.connect(**DB_CONFIG)

        result['s2_t1_ready'].wait()

        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE deadlock_test2 SET value=value+1 WHERE id=2")

        result['s2_t2_ready'].set()

        time.sleep(0.3)

        with conn.cursor() as cur:
            cur.execute("UPDATE deadlock_test SET value=value+1 WHERE id=2")

        conn.commit()
        result['s2_t2_result'] = 'success'
    except Exception as e:
        result['s2_t2_result'] = f'deadlock: {e}'
        try:
            conn.rollback()
        except:
            pass
    finally:
        try:
            conn.close()
        except:
            pass

def main():
    prepare_data()

    # 场景1: 同表交叉行锁 (重复3次)
    for i in range(3):
        print(f"\n=== 场景1: 同表交叉行锁死锁 (第{i+1}次) ===")
        result = {
            't1_ready': threading.Event(),
            't2_ready': threading.Event(),
            't1_result': '',
            't2_result': '',
        }
        t1 = threading.Thread(target=deadlock_scenario_1, args=(result,))
        t2 = threading.Thread(target=deadlock_thread_2, args=(result,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        print(f"  事务1: {result['t1_result']}")
        print(f"  事务2: {result['t2_result']}")
        time.sleep(1)

    # 场景2: 跨表死锁 (重复2次)
    for i in range(2):
        print(f"\n=== 场景2: 跨表死锁 (第{i+1}次) ===")
        result = {
            's2_t1_ready': threading.Event(),
            's2_t2_ready': threading.Event(),
            's2_t1_result': '',
            's2_t2_result': '',
        }
        t1 = threading.Thread(target=deadlock_scenario_2, args=(result,))
        t2 = threading.Thread(target=deadlock_thread_2_s2, args=(result,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        print(f"  事务1: {result['s2_t1_result']}")
        print(f"  事务2: {result['s2_t2_result']}")
        time.sleep(1)

    # 检查死锁日志
    print("\n=== 检查 MySQL 错误日志 ===")
    try:
        with open('/var/log/mysql/error.log', 'r') as f:
            content = f.read()
        count = content.count('LATEST DETECTED DEADLOCK')
        print(f"死锁事件数: {count}")
    except Exception as e:
        print(f"读取日志失败: {e}")

if __name__ == '__main__':
    main()
