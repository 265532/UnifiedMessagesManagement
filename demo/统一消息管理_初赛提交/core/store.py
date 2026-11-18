"""SQLite 持久化。

设计上只做三件事：存消息、去重、记状态流转。
换 MySQL 时，把这里的 SQL 换成对应驱动即可，上层服务代码不用动。
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager

import config
from core import state_machine
from core.schema import now_iso

_lock = threading.Lock()


@contextmanager
def get_conn():
    """每次操作开一个新连接，避免多线程共用连接出问题。"""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                platform        TEXT NOT NULL,
                event_id        TEXT NOT NULL UNIQUE,   -- 幂等键：同一平台事件只允许一条
                conversation_id TEXT NOT NULL,
                conversation_name TEXT,
                sender_id       TEXT NOT NULL,
                sender_name     TEXT NOT NULL,
                msg_type        TEXT NOT NULL,
                content         TEXT NOT NULL,          -- JSON
                reply_to        TEXT,
                status          TEXT NOT NULL,
                version         INTEGER NOT NULL DEFAULT 1,   -- 乐观锁版本号
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS traces (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id  TEXT NOT NULL,
                status      TEXT NOT NULL,
                at          TEXT NOT NULL,
                note        TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_platform ON messages(platform);
            CREATE INDEX IF NOT EXISTS idx_traces_message ON traces(message_id);
            """
        )


def _row_to_message(row) -> dict:
    return {
        "id": row["id"],
        "platform": row["platform"],
        "event_id": row["event_id"],
        "conversation": {"id": row["conversation_id"], "name": row["conversation_name"]},
        "sender": {"id": row["sender_id"], "name": row["sender_name"]},
        "msg_type": row["msg_type"],
        "content": json.loads(row["content"]),
        "reply_to": row["reply_to"],
        "status": row["status"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def insert_message(message: dict) -> bool:
    """写入一条消息。返回 True 表示新插入，False 表示已存在（被幂等去重）。

    event_id 上有 UNIQUE 约束，重复投递会直接命中 IntegrityError，这里转成返回值。
    """
    with _lock, get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO messages (
                    id, platform, event_id, conversation_id, conversation_name,
                    sender_id, sender_name, msg_type, content, reply_to,
                    status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message["id"],
                    message["platform"],
                    message["event_id"],
                    message["conversation"]["id"],
                    message["conversation"].get("name", ""),
                    message["sender"]["id"],
                    message["sender"]["name"],
                    message["msg_type"],
                    json.dumps(message["content"], ensure_ascii=False),
                    message.get("reply_to"),
                    message["status"],
                    1,
                    message["created_at"],
                    message["updated_at"],
                ),
            )
        except sqlite3.IntegrityError:
            return False

        conn.execute(
            "INSERT INTO traces (message_id, status, at, note) VALUES (?, ?, ?, ?)",
            (message["id"], message["status"], now_iso(), "平台事件到达，验签通过"),
        )
        return True


def get_message(message_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return _row_to_message(row) if row else None


def list_messages(platform: str | None = None, status: str | None = None, limit: int = 60) -> list[dict]:
    sql = "SELECT * FROM messages WHERE 1=1"
    args: list = []
    if platform:
        sql += " AND platform = ?"
        args.append(platform)
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    args.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [_row_to_message(r) for r in rows]


def transition(message_id: str, target: str, note: str = "", expected_version: int | None = None) -> dict:
    """推进消息状态。

    两层保护：
    1. 状态机校验：不允许的状态跳跃直接抛异常；
    2. 乐观锁：传入 expected_version 时，版本对不上就说明有人先改了，抛异常。
    """
    with _lock, get_conn() as conn:
        row = conn.execute("SELECT status, version FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not row:
            raise KeyError(f"消息 {message_id} 不存在")

        current = row["status"]
        state_machine.check(current, target)

        if expected_version is not None and row["version"] != expected_version:
            raise RuntimeError("消息已被其他操作修改，请刷新后重试")

        # 带上版本号做条件更新：多进程部署时线程锁管不到另一个进程，
        # 靠这条 CAS 语句保证只有一个请求能把状态改成功。
        updated = conn.execute(
            "UPDATE messages SET status = ?, version = version + 1, updated_at = ? "
            "WHERE id = ? AND version = ?",
            (target, now_iso(), message_id, row["version"]),
        )
        if updated.rowcount == 0:
            raise RuntimeError("消息状态刚被其他请求改过，请刷新后重试")
        conn.execute(
            "INSERT INTO traces (message_id, status, at, note) VALUES (?, ?, ?, ?)",
            (message_id, target, now_iso(), note),
        )

    return get_message(message_id)


def log_duplicate(event_id: str) -> bool:
    """重复投递被丢弃时留一条记录，挂在已存在的那条消息上。

    不写这条的话，stats 里的「已拦截重复」永远是 0，指标就成了摆设。
    """
    with _lock, get_conn() as conn:
        row = conn.execute("SELECT id FROM messages WHERE event_id = ?", (event_id,)).fetchone()
        if not row:
            return False
        conn.execute(
            "INSERT INTO traces (message_id, status, at, note) VALUES (?, ?, ?, ?)",
            (row["id"], "duplicate", now_iso(), "重复事件，已丢弃"),
        )
        return True


def log_note(message_id: str, tag: str, note: str) -> bool:
    """记一条不影响状态的流水，比如发送重试。

    和 transition 的区别：这里不动 messages.status，只往 traces 追加一行。
    重试信息以前只走 SSE，页面一刷新就丢了；落库之后「第几次、为什么失败」还能翻出来。
    """
    with _lock, get_conn() as conn:
        row = conn.execute("SELECT id FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not row:
            return False
        conn.execute(
            "INSERT INTO traces (message_id, status, at, note) VALUES (?, ?, ?, ?)",
            (message_id, tag, now_iso(), note),
        )
        return True


def get_traces(message_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, at, note FROM traces WHERE message_id = ? ORDER BY id",
            (message_id,),
        ).fetchall()
        return [{"status": r["status"], "at": r["at"], "note": r["note"]} for r in rows]


def stats() -> dict:
    """给首页仪表盘用的计数。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM messages GROUP BY status").fetchall()
        by_status = {r["status"]: r["n"] for r in rows}

        platform_rows = conn.execute("SELECT platform, COUNT(*) AS n FROM messages GROUP BY platform").fetchall()
        by_platform = {r["platform"]: r["n"] for r in platform_rows}

        total = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        duplicated = conn.execute(
            "SELECT COUNT(*) AS n FROM traces WHERE status = 'duplicate'"
        ).fetchone()["n"]

    return {
        "total": total,
        "by_status": by_status,
        "by_platform": by_platform,
        "rejected_duplicates": duplicated,
    }


def reset_demo_data() -> None:
    """清空演示数据，演示前点一下就有干净的初始状态。"""
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM traces")
