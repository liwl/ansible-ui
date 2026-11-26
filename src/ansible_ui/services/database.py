import sqlite3
from contextlib import contextmanager
import os
from .crypto_utils import CryptoUtils


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.getenv('DB_PATH', 'db/ansible.db')
        self.crypto = CryptoUtils()

        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self.init_database()

    def init_database(self):
        """初始化数据库表"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    comment TEXT NOT NULL,
                    address TEXT NOT NULL,
                    username TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    password TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    auth_method TEXT NOT NULL DEFAULT 'password',
                    private_key_path TEXT,
                    tag TEXT,
                    last_status TEXT,
                    last_checked TIMESTAMP
                )
            """)

            # 兼容旧数据库：已有表可能缺少后加的字段
            columns = {row[1] for row in conn.execute("PRAGMA table_info(hosts)").fetchall()}
            if 'private_key_path' not in columns:
                conn.execute("ALTER TABLE hosts ADD COLUMN private_key_path TEXT")
            if 'tag' not in columns:
                conn.execute("ALTER TABLE hosts ADD COLUMN tag TEXT")
            if 'last_status' not in columns:
                conn.execute("ALTER TABLE hosts ADD COLUMN last_status TEXT")
            if 'last_checked' not in columns:
                conn.execute("ALTER TABLE hosts ADD COLUMN last_checked TIMESTAMP")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS command_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host_id INTEGER,
                    command TEXT NOT NULL,
                    output TEXT,
                    status TEXT NOT NULL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    playbook_id INTEGER,
                    FOREIGN KEY (host_id) REFERENCES hosts (id)
                )
            """)

            log_columns = {row[1] for row in conn.execute("PRAGMA table_info(command_logs)").fetchall()}
            if 'playbook_id' not in log_columns:
                conn.execute("ALTER TABLE command_logs ADD COLUMN playbook_id INTEGER")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    access_time TIMESTAMP DEFAULT (datetime('now', '+8 hours'))
                )
            """)

            access_columns = {row[1] for row in conn.execute("PRAGMA table_info(access_logs)").fetchall()}
            if 'username' not in access_columns:
                conn.execute("ALTER TABLE access_logs ADD COLUMN username TEXT")
            if 'method' not in access_columns:
                conn.execute("ALTER TABLE access_logs ADD COLUMN method TEXT")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS playbooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT (datetime('now', '+8 hours')),
                    last_login TIMESTAMP
                )
            """)

            # 兼容可能存在的旧 users 表（只有 username/password）
            user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if 'password_hash' not in user_columns and 'password' in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            for col, ddl in (
                ('role', "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'"),
                ('is_primary', "ALTER TABLE users ADD COLUMN is_primary INTEGER NOT NULL DEFAULT 0"),
                ('created_at', "ALTER TABLE users ADD COLUMN created_at TIMESTAMP"),
                ('last_login', "ALTER TABLE users ADD COLUMN last_login TIMESTAMP"),
            ):
                if col not in user_columns:
                    conn.execute(ddl)

    def count_users(self):
        """用户总数"""
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_primary_admin_username(self):
        """取主管理员用户名（用于初始化判定）"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE is_primary = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            return row['username'] if row else None

    def get_users(self):
        """用户列表（不含密码哈希）"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT id, username, role, is_primary, created_at, last_login
                FROM users ORDER BY is_primary DESC, id ASC
            """).fetchall()
            return [dict(row) for row in rows]

    def get_user(self, user_id):
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_user_by_username(self, username):
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def create_user(self, username, password_hash, role='viewer', is_primary=False):
        """新建用户，返回新用户 id；用户名重复时抛 sqlite3.IntegrityError"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO users (username, password_hash, role, is_primary)
                VALUES (?, ?, ?, ?)
            """, (username, password_hash, role, 1 if is_primary else 0))
            return cursor.lastrowid

    def update_user(self, user_id, password_hash=None, role=None, is_primary=None):
        """按需更新用户字段"""
        fields, params = [], []
        if password_hash is not None:
            fields.append("password_hash = ?")
            params.append(password_hash)
        if role is not None:
            fields.append("role = ?")
            params.append(role)
        if is_primary is not None:
            fields.append("is_primary = ?")
            params.append(1 if is_primary else 0)
        if not fields:
            return False
        params.append(user_id)
        with self.get_connection() as conn:
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(params))
        return True

    def delete_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cursor.rowcount > 0

    def touch_user_login(self, user_id):
        """记录最近登录时间（北京时间）"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_login = datetime('now', '+8 hours') WHERE id = ?",
                (user_id,)
            )

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def add_host(self, host_data):
        """添加单个主机"""
        with self.get_connection() as conn:
            encrypted_password = None
            auth_method = host_data.get('auth_method', 'password')
            
            if auth_method == 'password' and host_data.get('password'):
                encrypted_password = self.crypto.encrypt(host_data['password'])

            cursor = conn.execute("""
                INSERT INTO hosts (comment, address, username, port, password, auth_method, private_key_path, tag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                host_data['comment'],
                host_data['address'],
                host_data['username'],
                host_data['port'],
                encrypted_password,
                auth_method,
                (host_data.get('private_key_path') or '').strip() or None,
                (host_data.get('tag') or '').strip() or None
            ))
            return cursor.lastrowid

    def add_hosts_batch(self, hosts_data):
        """批量添加主机"""
        with self.get_connection() as conn:
            processed_hosts = []
            for host in hosts_data:
                encrypted_password = None
                auth_method = host.get('auth_method', 'password')
                
                if auth_method == 'password' and host.get('password'):
                    encrypted_password = self.crypto.encrypt(host['password'])
                
                processed_hosts.append((
                    host['comment'],
                    host['address'],
                    host['username'],
                    host['port'],
                    encrypted_password,
                    auth_method,
                    (host.get('private_key_path') or '').strip() or None,
                    (host.get('tag') or '').strip() or None
                ))

            cursor = conn.executemany("""
                INSERT INTO hosts (comment, address, username, port, password, auth_method, private_key_path, tag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, processed_hosts)
            return cursor.rowcount

    def get_hosts(self):
        """获取所有主机"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM hosts ORDER BY created_at DESC")
            hosts = [dict(row) for row in cursor.fetchall()]
            
            for host in hosts:
                host['encrypted_password'] = host['password']
                if host['auth_method'] == 'password' and host['password']:
                    host['password'] = self.crypto.decrypt(host['password'])
                else:
                    host['password'] = None
            return hosts

    def get_host(self, host_id):
        """获取单个主机信息"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM hosts WHERE id = ?", (host_id,))
            row = cursor.fetchone()
            if row:
                host = dict(row)
                host['encrypted_password'] = host['password']
                if host['auth_method'] == 'password' and host['password']:
                    host['password'] = self.crypto.decrypt(host['password'])
                else:
                    host['password'] = None
                return host
            return None

    def update_host(self, host_id, host_data):
        """更新主机信息"""
        with self.get_connection() as conn:
            auth_method = host_data.get('auth_method', 'password')
            current_host = conn.execute(
                "SELECT password, private_key_path, tag FROM hosts WHERE id = ?",
                (host_id,)
            ).fetchone()
            current_password = current_host["password"] if current_host else None
            current_tag = current_host["tag"] if current_host else None

            if auth_method == 'key':
                encrypted_password = None
            elif host_data.get('password'):
                encrypted_password = self.crypto.encrypt(host_data['password'])
            else:
                encrypted_password = current_password
            
            current_key_path = current_host["private_key_path"] if current_host else None
            key_path = (host_data.get('private_key_path') or '').strip() or None
            if key_path is None and auth_method == 'key':
                key_path = current_key_path

            # 请求带 tag 字段才更新分组，否则保留原值（兼容不带 tag 的旧调用）
            if 'tag' in host_data:
                tag = (host_data.get('tag') or '').strip() or None
            else:
                tag = current_tag

            conn.execute("""
                UPDATE hosts
                SET comment = ?, address = ?, username = ?, port = ?, password = ?, auth_method = ?, private_key_path = ?, tag = ?
                WHERE id = ?
            """, (
                host_data['comment'],
                host_data['address'],
                host_data['username'],
                host_data['port'],
                encrypted_password,
                auth_method,
                key_path,
                tag,
                host_id
            ))

    def update_hosts_status(self, status_map):
        """批量更新主机巡检状态。

        status_map: {host_id: 'success' | 'unreachable' | 'failed'}
        """
        if not status_map:
            return
        with self.get_connection() as conn:
            conn.executemany(
                """UPDATE hosts
                   SET last_status = ?, last_checked = datetime('now', '+8 hours')
                   WHERE id = ?""",
                [(status, host_id) for host_id, status in status_map.items()]
            )

    def delete_host(self, host_id):
        """删除主机"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM command_logs WHERE host_id = ?", (host_id,))
            conn.execute("DELETE FROM hosts WHERE id = ?", (host_id,))

    def delete_hosts_batch(self, host_ids):
        """批量删除主机，返回实际删除数量（单事务）"""
        if not host_ids:
            return 0
        placeholders = ','.join('?' for _ in host_ids)
        with self.get_connection() as conn:
            conn.execute(
                f"DELETE FROM command_logs WHERE host_id IN ({placeholders})", host_ids
            )
            cursor = conn.execute(
                f"DELETE FROM hosts WHERE id IN ({placeholders})", host_ids
            )
            return cursor.rowcount

    # ---------- Playbook 管理 ----------
    def get_playbooks(self):
        """获取所有 playbook"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, content, created_at, updated_at "
                "FROM playbooks ORDER BY updated_at DESC, id DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_playbook(self, playbook_id):
        """获取单个 playbook"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, content, created_at, updated_at "
                "FROM playbooks WHERE id = ?", (playbook_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_playbook(self, data):
        """新增 playbook，返回新 id"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO playbooks (name, description, content)
                VALUES (?, ?, ?)
            """, (data['name'], data.get('description', ''), data['content']))
            return cursor.lastrowid

    def update_playbook(self, playbook_id, data):
        """更新 playbook"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE playbooks
                SET name = ?, description = ?, content = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (data['name'], data.get('description', ''), data['content'], playbook_id))
            return cursor.rowcount > 0

    def delete_playbook(self, playbook_id):
        """删除 playbook"""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM playbooks WHERE id = ?", (playbook_id,))
            return cursor.rowcount > 0

    def log_command(self, host_id, command, output, status, playbook_id=None):
        """记录命令执行日志（playbook_id 用于关联已保存的 Playbook）"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO command_logs (host_id, command, output, status, playbook_id)
                VALUES (?, ?, ?, ?, ?)
            """, (host_id, command, output, status, playbook_id))

    def get_command_logs(self, limit=50, offset=0, host_id=None, status=None,
                         date_from=None, date_to=None, keyword=None,
                         sort=None, order='desc'):
        """获取命令执行日志（支持筛选、排序与分页）。

        date_from/date_to 为 YYYY-MM-DD，按北京时间(UTC+8)比较。
        sort 走字段白名单（不接受任意列名，避免 SQL 注入），未知值回落到时间倒序。
        返回 {'items': [...], 'total': 总数}。
        """
        clauses = []
        params = []
        if host_id is not None:
            clauses.append("cl.host_id = ?")
            params.append(host_id)
        if status:
            clauses.append("cl.status = ?")
            params.append(status)
        if date_from:
            clauses.append("date(cl.executed_at, '+8 hours') >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("date(cl.executed_at, '+8 hours') <= ?")
            params.append(date_to)
        if keyword:
            clauses.append("(cl.command LIKE ? OR cl.output LIKE ? OR h.comment LIKE ? OR h.address LIKE ?)")
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, kw])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # 白名单以外的 sort 一律回落到 id（等价于执行时间）
        sortable = {
            'executed_at': 'cl.id',
            'host': 'h.comment',
            'type': 'cl.command',
            'command': 'cl.command',
            'status': 'cl.status',
        }
        order_column = sortable.get(sort or '', 'cl.id')
        direction = 'ASC' if str(order).lower() == 'asc' else 'DESC'
        # 追加 cl.id 作为稳定次序，避免排序值相同时分页抖动
        order_sql = f"{order_column} {direction}, cl.id DESC"

        with self.get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM command_logs cl "
                f"LEFT JOIN hosts h ON cl.host_id = h.id {where_sql}",
                tuple(params)
            ).fetchone()[0]

            cursor = conn.execute(f"""
                SELECT cl.id, cl.host_id, cl.command, cl.output, cl.status,
                       datetime(cl.executed_at, '+8 hours') AS executed_at,
                       cl.playbook_id, pb.name AS playbook_name,
                       h.comment, h.address
                FROM command_logs cl
                LEFT JOIN hosts h ON cl.host_id = h.id
                LEFT JOIN playbooks pb ON cl.playbook_id = pb.id
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
            """, tuple(params) + (limit, offset))
            return {'items': [dict(row) for row in cursor.fetchall()], 'total': total}

    def add_access_log(self, ip_address, path, status, status_code, username=None, method=None):
        """添加访问日志（携带操作人便于审计）"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO access_logs (ip_address, path, status, status_code, username, method)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ip_address, path, status, status_code, username, method))

    def get_access_logs(self, limit=100, ip_filter='', path_filter='', user_filter=''):
        """获取访问日志"""
        with self.get_connection() as conn:
            clauses = []
            params = []

            if ip_filter:
                clauses.append("ip_address LIKE ?")
                params.append(f"%{ip_filter}%")

            if path_filter:
                clauses.append("path LIKE ?")
                params.append(f"%{path_filter}%")

            if user_filter:
                clauses.append("username = ?")
                params.append(user_filter)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            query = f"""
                SELECT * FROM access_logs
                {where_sql}
                ORDER BY access_time DESC
                LIMIT ?
            """
            params.append(limit)

            cursor = conn.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def get_access_log_users(self):
        """审计日志中出现过的操作人列表（用于前端筛选下拉）"""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT DISTINCT username FROM access_logs
                WHERE username IS NOT NULL AND username != ''
                ORDER BY username
            """).fetchall()
            return [row['username'] for row in rows]

    def cleanup_old_logs(self):
        """清理3天前的访问日志和命令日志（使用北京时间）"""
        with self.get_connection() as conn:
            conn.execute("""
                DELETE FROM access_logs 
                WHERE access_time < datetime('now', '+8 hours', '-3 days')
            """)
            conn.execute("""
                DELETE FROM command_logs
                WHERE datetime(executed_at, '+8 hours') < datetime('now', '+8 hours', '-3 days')
            """)
