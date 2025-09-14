from collections import defaultdict
import sqlite3

from models.generic import LoggedInUser
from typing import Any, DefaultDict

DB = sqlite3.connect("./db/draaft.db")
cur = DB.cursor()

# Setup things


def setup_sqlite():
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code char(7) UNIQUE,
            admin char(32)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid char(32) UNIQUE,
            username char(32),
            room_code char(7) references rooms(code)
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_rooms_code ON rooms(code);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_uuid ON users(uuid);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_room_code ON users(room_code);
    """)


if __name__ == "__main__":
    setup_sqlite()


def insert_user(username: str, uuid: str) -> bool:
    try:
        cur.execute("INSERT INTO users (uuid, username) VALUES (?,?)",
                    (uuid, username))
        DB.commit()
        return True
    except sqlite3.IntegrityError:
        # UUID already exists
        # TODO: Should this also update usernames? I don't think it really matters
        return False


def get_user(username: str, uuid: str) -> LoggedInUser | None:
    """ Gets a user by UUID. If the user does not exist, it is created. """
    # TODO - update username if changed or be dynamic elsewhere
    res = cur.execute("SELECT * FROM users WHERE uuid = ?", (uuid,)).fetchall()
    if not res:
        if not insert_user(username, uuid):
            return None
        return get_user(username, uuid)
    _, uuid, stored_username, room_code = res[0]
    if stored_username != username:
        cur.execute("UPDATE users SET username = ? WHERE uuid = ?", (username, uuid))
        DB.commit()
    return LoggedInUser(username=username, uuid=uuid, room_code=room_code)

class UUIDState:
    def __init__(self):
        self.connections = 0
memory_db: DefaultDict[str, UUIDState] = defaultdict(lambda: UUIDState())

class PopulatedUser:
    def __init__(self, user: LoggedInUser):
        self.source = user
        self.uuid = user.uuid
        self.state = memory_db[self.uuid]
def populated_user(user: LoggedInUser) -> PopulatedUser:
    return PopulatedUser(user)

def update_user(user: LoggedInUser, key: str, value: Any):
    cur.execute("UPDATE users SET ? = ? WHERE uuid = ?", (key, value, user.uuid))
    DB.commit()
