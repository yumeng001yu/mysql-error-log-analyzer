#!/usr/bin/env python3
"""
Generate various MySQL errors and slow queries for testing the MySQL Error Log Analyzer.
"""

import time
import threading
import datetime
import pymysql
import sys

MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = ""
MYSQL_DB = "ecommerce"
MYSQL_SOCKET = "/var/run/mysqld/mysqld.sock"
ERROR_LOG_PATH = "/var/log/mysql/error.log"


def get_connection(user=MYSQL_USER, password=MYSQL_PASSWORD, db=MYSQL_DB):
    """Create a pymysql connection via Unix socket."""
    return pymysql.connect(
        host=MYSQL_HOST,
        user=user,
        password=password,
        database=db,
        unix_socket=MYSQL_SOCKET,
        autocommit=False,
    )


def log_section(title):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# =============================================================================
# 1. Slow Queries
# =============================================================================
def generate_slow_queries():
    log_section("1. Generating Slow Queries")

    conn = get_connection()
    cursor = conn.cursor()

    # Temporarily lower long_query_time to ensure queries are captured
    cursor.execute("SET SESSION long_query_time = 0.5")
    conn.commit()

    slow_queries = [
        (
            "Full table scan on orders",
            "SELECT * FROM ecommerce.orders WHERE total_price > 100 ORDER BY created_at DESC",
        ),
        (
            "Cross join without index",
            "SELECT u.username, p.name FROM ecommerce.users u CROSS JOIN ecommerce.products p LIMIT 100000",
        ),
        (
            "Complex aggregation",
            "SELECT u.city, COUNT(o.id), SUM(o.total_price), AVG(o.total_price) "
            "FROM ecommerce.users u JOIN ecommerce.orders o ON u.id=o.user_id "
            "GROUP BY u.city ORDER BY SUM(o.total_price) DESC",
        ),
        (
            "Subquery",
            "SELECT * FROM ecommerce.orders WHERE user_id IN "
            "(SELECT id FROM ecommerce.users WHERE city='Beijing') AND total_price > 500",
        ),
        (
            "LIKE with leading wildcard",
            "SELECT * FROM ecommerce.products WHERE name LIKE '%Product_1%'",
        ),
    ]

    for desc, query in slow_queries:
        repeat_count = 3 if "Cross join" in desc else 5
        print(f"\n  [{desc}] - running {repeat_count} times...")
        for i in range(repeat_count):
            start = time.time()
            try:
                cursor.execute(query)
                cursor.fetchall()
                elapsed = time.time() - start
                print(f"    Run {i+1}: {elapsed:.3f}s")
            except Exception as e:
                print(f"    Run {i+1}: ERROR - {e}")
            conn.commit()

    # Also run some intentionally heavy queries with SLEEP to guarantee >1s
    print("\n  [Heavy query with SLEEP] - ensuring slow query log entries >1s...")
    for i in range(3):
        start = time.time()
        try:
            # Use SLEEP in a subquery so it's only called once, combined with a heavy scan
            cursor.execute(
                "SELECT * FROM ecommerce.orders WHERE total_price > 100 AND "
                "created_at > (SELECT NOW() - INTERVAL 1 YEAR FROM (SELECT SLEEP(2)) AS t) "
                "ORDER BY created_at DESC"
            )
            cursor.fetchall()
            elapsed = time.time() - start
            print(f"    SLEEP+scan query {i+1}: {elapsed:.3f}s")
        except Exception as e:
            print(f"    SLEEP+scan query {i+1}: ERROR - {e}")
        conn.commit()

    cursor.close()
    conn.close()
    print("  Done generating slow queries.")


# =============================================================================
# 2. Deadlocks
# =============================================================================
def generate_deadlocks():
    log_section("2. Generating Deadlocks")

    deadlock_scenarios = [
        (1, 2),
        (3, 4),
        (5, 6),
    ]

    for idx, (row_id_1, row_id_2) in enumerate(deadlock_scenarios):
        print(f"\n  Deadlock scenario {idx+1}: rows {row_id_1} and {row_id_2}")

        # Events for synchronization
        lock_a = threading.Event()
        lock_b = threading.Event()
        done_a = threading.Event()
        done_b = threading.Event()
        error_a = [None]
        error_b = [None]

        def session_a(rid1=row_id_1, rid2=row_id_2):
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    f"UPDATE ecommerce.orders SET status='cancelled' WHERE id={rid1}"
                )
                print(f"    Session A: Locked row {rid1}")
                lock_a.set()  # Signal that A has locked row 1
                lock_b.wait(timeout=10)  # Wait for B to lock row 2
                time.sleep(0.3)  # Small delay to increase deadlock chance
                try:
                    cursor.execute(
                        f"UPDATE ecommerce.orders SET status='shipped' WHERE id={rid2}"
                    )
                    print(f"    Session A: Trying to lock row {rid2} (should wait/deadlock)")
                    conn.commit()
                except pymysql.Error as e:
                    error_a[0] = e
                    print(f"    Session A: Got error: {e}")
                    conn.rollback()
                cursor.close()
                conn.close()
            except Exception as e:
                error_a[0] = e
            finally:
                done_a.set()

        def session_b(rid1=row_id_1, rid2=row_id_2):
            try:
                conn = get_connection()
                cursor = conn.cursor()
                lock_a.wait(timeout=10)  # Wait for A to lock row 1
                cursor.execute("BEGIN")
                cursor.execute(
                    f"UPDATE ecommerce.orders SET status='cancelled' WHERE id={rid2}"
                )
                print(f"    Session B: Locked row {rid2}")
                lock_b.set()  # Signal that B has locked row 2
                time.sleep(0.3)
                try:
                    cursor.execute(
                        f"UPDATE ecommerce.orders SET status='shipped' WHERE id={rid1}"
                    )
                    print(f"    Session B: Trying to lock row {rid1} (should deadlock)")
                    conn.commit()
                except pymysql.Error as e:
                    error_b[0] = e
                    print(f"    Session B: Got error: {e}")
                    conn.rollback()
                cursor.close()
                conn.close()
            except Exception as e:
                error_b[0] = e
            finally:
                done_b.set()

        t_a = threading.Thread(target=session_a)
        t_b = threading.Thread(target=session_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        if error_a[0] and "Deadlock" in str(error_a[0]):
            print(f"    Deadlock detected in Session A!")
        elif error_b[0] and "Deadlock" in str(error_b[0]):
            print(f"    Deadlock detected in Session B!")
        else:
            print(f"    No deadlock detected (may need retry)")

        time.sleep(1)  # Wait between scenarios

    print("  Done generating deadlocks.")


# =============================================================================
# 3. Lock Wait Timeouts
# =============================================================================
def generate_lock_wait_timeouts():
    log_section("3. Generating Lock Wait Timeouts")

    # Use a separate connection for the blocker, keep the transaction open
    conn_blocker = get_connection()
    cursor_blocker = conn_blocker.cursor()
    cursor_blocker.execute("BEGIN")
    cursor_blocker.execute("UPDATE ecommerce.orders SET status='pending' WHERE id=10")
    print("  Blocker: Locked row id=10 (transaction open)")

    blocker_ready = threading.Event()
    timeout_error = [None]
    waiter_done = threading.Event()

    def waiter_session():
        try:
            conn_waiter = get_connection()
            cursor_waiter = conn_waiter.cursor()
            # Use innodb_lock_wait_timeout for row-level lock timeouts (not lock_wait_timeout which is for metadata locks)
            cursor_waiter.execute("SET SESSION innodb_lock_wait_timeout = 5")
            conn_waiter.commit()
            blocker_ready.set()  # Signal that waiter is ready
            time.sleep(0.5)  # Ensure blocker has the lock
            print("  Waiter: Trying to update row id=10 (should timeout after 5s)...")
            try:
                cursor_waiter.execute("UPDATE ecommerce.orders SET status='delivered' WHERE id=10")
                conn_waiter.commit()
                print("  Waiter: Unexpectedly succeeded!")
            except pymysql.Error as e:
                timeout_error[0] = e
                print(f"  Waiter: Got error: {e}")
                conn_waiter.rollback()
            cursor_waiter.close()
            conn_waiter.close()
        except Exception as e:
            timeout_error[0] = e
            print(f"  Waiter: Connection error: {e}")
        finally:
            waiter_done.set()

    t = threading.Thread(target=waiter_session)
    t.start()

    # Wait for the waiter to finish (it should timeout after ~5s)
    waiter_done.wait(timeout=15)

    # Release the blocker lock
    conn_blocker.rollback()
    cursor_blocker.close()
    conn_blocker.close()

    t.join(timeout=5)

    if timeout_error[0] and "timeout" in str(timeout_error[0]).lower():
        print("  Lock wait timeout generated successfully!")
    else:
        print(f"  Lock wait timeout result: {timeout_error[0]}")

    print("  Done generating lock wait timeouts.")


# =============================================================================
# 4. Connection Errors
# =============================================================================
def generate_connection_errors():
    log_section("4. Generating Connection Errors")

    # Try connecting with wrong password via TCP (not socket, since root uses auth_socket)
    for i in range(5):
        try:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=3306,
                user="root",
                password="wrong_password",
                database=MYSQL_DB,
            )
            conn.close()
        except pymysql.Error as e:
            print(f"  Wrong password attempt {i+1}: {e}")

    # Try connecting with non-existent user
    for i in range(3):
        try:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=3306,
                user="nonexistent_user",
                password="some_password",
                database=MYSQL_DB,
            )
            conn.close()
        except pymysql.Error as e:
            print(f"  Non-existent user attempt {i+1}: {e}")

    # Try connecting to non-existent database
    for i in range(2):
        try:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=3306,
                user="root",
                password="",
                database="nonexistent_db",
            )
            conn.close()
        except pymysql.Error as e:
            print(f"  Non-existent DB attempt {i+1}: {e}")

    print("  Done generating connection errors.")


# =============================================================================
# 5. Duplicate Key Errors
# =============================================================================
def generate_duplicate_key_errors():
    log_section("5. Generating Duplicate Key Errors")

    conn = get_connection()
    cursor = conn.cursor()

    # Try inserting duplicate primary key into orders
    for i in range(3):
        try:
            cursor.execute(
                "INSERT INTO ecommerce.orders (id, user_id, product_id, quantity, total_price, status) "
                "VALUES (1, 1, 1, 1, 99.99, 'pending')"
            )
            conn.commit()
        except pymysql.Error as e:
            print(f"  Duplicate key error (orders) attempt {i+1}: {e}")
            conn.rollback()

    # Try inserting duplicate primary key into users
    for i in range(2):
        try:
            cursor.execute(
                "INSERT INTO ecommerce.users (id, username, email) VALUES (1, 'dup_user', 'dup@test.com')"
            )
            conn.commit()
        except pymysql.Error as e:
            print(f"  Duplicate key error (users) attempt {i+1}: {e}")
            conn.rollback()

    # Try inserting duplicate username (unique key)
    for i in range(2):
        try:
            # Get an existing username first
            cursor.execute("SELECT username FROM ecommerce.users LIMIT 1")
            existing_username = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO ecommerce.users (username, email) VALUES (%s, 'dup_email@test.com')",
                (existing_username,)
            )
            conn.commit()
        except pymysql.Error as e:
            print(f"  Duplicate unique key error attempt {i+1}: {e}")
            conn.rollback()

    cursor.close()
    conn.close()
    print("  Done generating duplicate key errors.")


# =============================================================================
# 6. Foreign Key Errors
# =============================================================================
def generate_foreign_key_errors():
    log_section("6. Generating Foreign Key Errors")

    conn = get_connection()
    cursor = conn.cursor()

    # First, add a foreign key constraint to payments table referencing orders
    try:
        # Check if FK already exists
        cursor.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA='ecommerce' AND TABLE_NAME='payments' "
            "AND CONSTRAINT_TYPE='FOREIGN KEY'"
        )
        fk_exists = cursor.fetchone()

        if not fk_exists:
            print("  Adding foreign key constraint to payments.order_id...")
            cursor.execute(
                "ALTER TABLE ecommerce.payments ADD CONSTRAINT fk_payment_order "
                "FOREIGN KEY (order_id) REFERENCES ecommerce.orders(id)"
            )
            conn.commit()
            print("  Foreign key added successfully.")
        else:
            print(f"  Foreign key already exists: {fk_exists[0]}")
    except Exception as e:
        print(f"  Could not add foreign key: {e}")
        conn.rollback()

    # Now try inserting a payment with non-existent order_id
    for i in range(3):
        try:
            cursor.execute(
                "INSERT INTO ecommerce.payments (order_id, amount, method, status) "
                "VALUES (999999, 100.00, 'credit_card', 'success')"
            )
            conn.commit()
        except pymysql.Error as e:
            print(f"  Foreign key error attempt {i+1}: {e}")
            conn.rollback()

    cursor.close()
    conn.close()
    print("  Done generating foreign key errors.")


# =============================================================================
# 7 & 8. Append Realistic Error Log Entries
# =============================================================================
def append_error_log_entries():
    log_section("7 & 8. Appending Realistic Error Log Entries")

    now = datetime.datetime.now()
    timestamp_fmt = "%Y-%m-%dT%H:%M:%S.%fZ"

    entries = []

    # Buffer pool errors
    ts = now.strftime(timestamp_fmt)
    entries.append(f"{ts} 7 [ERROR] [MY-012585] [InnoDB] Buffer pool(s) load failed, proceeding without buffer pool(s).")
    entries.append(f"{ts} 7 [Warning] [MY-012574] [InnoDB] Difficult to find free blocks in the buffer pool (21 iterations). Consider increasing the buffer pool size.")

    # Disk full error
    ts = (now - datetime.timedelta(seconds=30)).strftime(timestamp_fmt)
    entries.append(f"{ts} 7 [ERROR] [MY-012138] [Server] /usr/sbin/mysqld: Disk full writing '/var/lib/mysql/ib_logfile0' (Errcode: 28 - No space left on device). Waiting for someone to free space...")

    # Communication packet errors
    for i in range(5):
        ts = (now - datetime.timedelta(seconds=60 * (i + 1))).strftime(timestamp_fmt)
        entries.append(f"{ts} 7 [Warning] [MY-010926] [Server] Got an error reading communication packets")

    # Too many open files
    ts = (now - datetime.timedelta(seconds=120)).strftime(timestamp_fmt)
    entries.append(f"{ts} 7 [ERROR] [MY-010835] [Server] Error in accept: Too many open files")

    # Aborted connections
    for i in range(8):
        ts = (now - datetime.timedelta(seconds=180 + i * 10)).strftime(timestamp_fmt)
        conn_id = 100 + i * 7
        entries.append(
            f"{ts} 7 [Note] [MY-010926] [Server] Aborted connection {conn_id} to db: 'ecommerce' user: 'testuser' host: 'localhost' (Got timeout reading communication packets)"
        )

    # InnoDB deadlock log entries in standard MySQL format
    for i in range(3):
        ts = (now - datetime.timedelta(seconds=300 + i * 60)).strftime(timestamp_fmt)
        deadlock_entry = f"""{ts} 7 [ERROR] [MY-012492] [InnoDB] Deadlock found when trying to get lock; try restarting transaction
{ts} 7 [Note] [MY-012491] [InnoDB] *** (1) TRANSACTION:
{ts} 7 [Note] [MY-012491] [InnoDB] TRANSACTION 1234{i}, ACTIVE 2 sec starting index read
{ts} 7 [Note] [MY-012491] [InnoDB] mysql tables in use 1, locked 1
{ts} 7 [Note] [MY-012491] [InnoDB] LOCK WAIT 2 lock struct(s), heap size 1128, 1 row lock(s)
{ts} 7 [Note] [MY-012491] [InnoDB] MySQL thread id {50+i}, OS thread handle 140234567890, query id {1000+i} localhost root updating
{ts} 7 [Note] [MY-012491] [InnoDB] UPDATE ecommerce.orders SET status='shipped' WHERE id={2+i}
{ts} 7 [Note] [MY-012491] [InnoDB] *** (1) HOLDS THE LOCK(S):
{ts} 7 [Note] [MY-012491] [InnoDB] RECORD LOCKS space id 58 page no 4 n bits 72 index PRIMARY of table `ecommerce`.`orders` trx id 1234{i} lock_mode X locks rec but not gap
{ts} 7 [Note] [MY-012491] [InnoDB] Record lock, heap no {3+i} PHYSICAL RECORD: n_fields 8; compact format; info bits 0
{ts} 7 [Note] [MY-012491] [InnoDB] *** (1) WAITING FOR THIS LOCK TO BE GRANTED:
{ts} 7 [Note] [MY-012491] [InnoDB] RECORD LOCKS space id 58 page no 4 n bits 72 index PRIMARY of table `ecommerce`.`orders` trx id 1234{i} lock_mode X locks rec but not gap waiting
{ts} 7 [Note] [MY-012491] [InnoDB] *** (2) TRANSACTION:
{ts} 7 [Note] [MY-012491] [InnoDB] TRANSACTION 1235{i}, ACTIVE 2 sec starting index read
{ts} 7 [Note] [MY-012491] [InnoDB] mysql tables in use 1, locked 1
{ts} 7 [Note] [MY-012491] [InnoDB] 3 lock struct(s), heap size 1128, 2 row lock(s)
{ts} 7 [Note] [MY-012491] [InnoDB] MySQL thread id {51+i}, OS thread handle 140234567891, query id {1001+i} localhost root updating
{ts} 7 [Note] [MY-012491] [InnoDB] UPDATE ecommerce.orders SET status='shipped' WHERE id={1+i}
{ts} 7 [Note] [MY-012491] [InnoDB] *** (2) HOLDS THE LOCK(S):
{ts} 7 [Note] [MY-012491] [InnoDB] RECORD LOCKS space id 58 page no 4 n bits 72 index PRIMARY of table `ecommerce`.`orders` trx id 1235{i} lock_mode X locks rec but not gap
{ts} 7 [Note] [MY-012491] [InnoDB] *** (2) WAITING FOR THIS LOCK TO BE GRANTED:
{ts} 7 [Note] [MY-012491] [InnoDB] RECORD LOCKS space id 58 page no 4 n bits 72 index PRIMARY of table `ecommerce`.`orders` trx id 1235{i} lock_mode X locks rec but not gap waiting
{ts} 7 [Note] [MY-012491] [InnoDB] *** WE ROLL BACK TRANSACTION (1)"""
        entries.append(deadlock_entry)

    # Additional realistic errors
    ts = (now - datetime.timedelta(seconds=400)).strftime(timestamp_fmt)
    entries.append(f"{ts} 7 [Warning] [MY-013360] [Plugin] Could not create a temporary file in /tmp: Permission denied")
    entries.append(f"{ts} 7 [ERROR] [MY-010914] [Server] Can't open shared library '/usr/lib/mysql/plugin/auth_socket.so'")
    entries.append(f"{ts} 7 [Warning] [MY-010306] [Server] Implicit temporary table(s) are being created on disk due to table size. Consider increasing tmp_table_size and/or max_heap_table_size")

    # Write to error log
    try:
        with open(ERROR_LOG_PATH, "a") as f:
            for entry in entries:
                f.write(entry + "\n")
        print(f"  Appended {len(entries)} error log entries to {ERROR_LOG_PATH}")
    except PermissionError:
        print(f"  Permission denied writing to {ERROR_LOG_PATH}, trying with sudo...")
        import subprocess
        content = "\n".join(entries) + "\n"
        result = subprocess.run(
            ["sudo", "tee", "-a", ERROR_LOG_PATH],
            input=content.encode(),
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"  Appended {len(entries)} error log entries to {ERROR_LOG_PATH} (via sudo)")
        else:
            print(f"  Failed to write: {result.stderr.decode()}")

    print("  Done appending error log entries.")


# =============================================================================
# Main
# =============================================================================
def main():
    print("MySQL Error Log Test Data Generator")
    print(f"Started at: {datetime.datetime.now()}")
    print(f"MySQL: {MYSQL_USER}@{MYSQL_HOST}/{MYSQL_DB}")

    # Verify MySQL connection
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        print(f"MySQL Version: {version}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"FATAL: Cannot connect to MySQL: {e}")
        sys.exit(1)

    # Generate all test data
    generate_slow_queries()
    generate_deadlocks()
    generate_lock_wait_timeouts()
    generate_connection_errors()
    generate_duplicate_key_errors()
    generate_foreign_key_errors()
    append_error_log_entries()

    # Flush to ensure logs are written
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("FLUSH STATUS")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"  All test errors generated successfully!")
    print(f"  Completed at: {datetime.datetime.now()}")
    print(f"  Error log: {ERROR_LOG_PATH}")
    print(f"  Slow query log: /var/log/mysql/mysql-slow.log")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
