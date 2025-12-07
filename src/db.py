from collections import defaultdict
import sqlite3
from draft import Draft

from models.generic import LoggedInUser
from typing import Any, DefaultDict

from models.room import Room
from utils import LOG, IndentLog, get_user_from_request
import threading

# https://stackoverflow.com/questions/41206800/how-should-i-handle-multiple-threads-accessing-a-sqlite-database-in-python
class LockableSqliteConnection():
    def __init__(self, dburi):
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(dburi, check_same_thread=False)
        self.cursor = None

    def __enter__(self) -> sqlite3.Cursor:
        self.lock.acquire()
        self.cursor = self.connection.cursor()
        return self.cursor

    def __exit__(self, type, value, traceback):
        self.connection.commit()

        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None

        self.lock.release()


sql = LockableSqliteConnection("./db/draaft.db")
# DB = sqlite3.connect("./db/draaft.db")
# cur = DB.cursor()

# Setup things


def setup_sqlite():
    with sql as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code char(7) UNIQUE NOT NULL,
                admin char(32) NOT NULL,
                config VARCHAR DEFAULT '{}',
                draft VARCHAR,
                state VARCHAR DEFAULT '{}'
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid char(32) UNIQUE NOT NULL,
                username char(32) NOT NULL,
                room_code char(7) references rooms(code),
                pronouns char(12)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid char(32) UNIQUE NOT NULL,
                status char(32) NOT NULL
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
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_status_uuid ON status(uuid);
        """)


if __name__ == "__main__":
    setup_sqlite()


def insert_user(username: str, uuid: str) -> bool:
    try:
        with sql as cur:
            cur.execute("INSERT INTO users (uuid, username) VALUES (?,?)",
                        (uuid, username))
        LOG("Created new user with username", username)
        return True
    except sqlite3.IntegrityError as e:
        # UUID already exists
        # TODO: Should this also update usernames? I don't think it really matters
        LOG("Failed insert_user with error:", e)
        return False

def insert_update_status(uuid: str, status: str):
    try:
        with sql as cur:
            cur.execute("INSERT INTO status (uuid, status) VALUES (?,?)", (uuid, status))
    except sqlite3.IntegrityError as e:
        # update instead
        LOG("Failed insert_update_status with error:", e)
        with sql as cur:
            cur.execute("UPDATE status SET status = ? WHERE uuid = ?", (status, uuid))


def get_user_status(uuid: str) -> str:
    with sql as cur:
        status_res = cur.execute("SELECT status FROM status WHERE uuid = ?", (uuid,)).fetchall()
    if status_res:
        assert isinstance(status_res[0][0], str)
        return status_res[0][0]
    else:
        return "player"


def get_user(username: str, uuid: str) -> LoggedInUser | None:
    """ Gets a user by UUID. If the user does not exist, it is created. """
    # TODO - update username if changed or be dynamic elsewhere
    with sql as cur:
        res = cur.execute("SELECT * FROM users WHERE uuid = ?", (uuid,)).fetchall()
    if not res:
        if not insert_user(username, uuid):
            return None
        return get_user(username, uuid)
    _, uuid, stored_username, room_code, pronouns = res[0]
    if stored_username != username:
        with sql as cur:
            cur.execute("UPDATE users SET username = ? WHERE uuid = ?", (username, uuid))
    return LoggedInUser(username=username, uuid=uuid, room_code=room_code, status=get_user_status(uuid), pronouns=pronouns)

def try_get_user(uuid: str) -> LoggedInUser | None:
    with sql as cur:
        res = cur.execute("SELECT * FROM users WHERE uuid = ?", (uuid,)).fetchall()
    if not res:
        return None
    _, uuid, stored_username, room_code = res[0]
    return LoggedInUser(username=stored_username, uuid=uuid, room_code=room_code, status=get_user_status(uuid))

class UUIDState:
    def __init__(self):
        self.connections = 0
memory_db: DefaultDict[str, UUIDState] = defaultdict(lambda: UUIDState())

class PopulatedUser:
    def __init__(self, user: LoggedInUser):
        self.source = user
        self.uuid = user.uuid
        self.state = memory_db[self.uuid]

    # Convenience method. Get the room that this user is in.
    def get_room(self) -> Room | None:
        from rooms import get_user_room_code, get_room_from_code
        rc = get_user_room_code(self.uuid)
        if rc is None:
            return None
        return get_room_from_code(rc)

    def update_status(self, status: str):
        insert_update_status(self.uuid, status)


def populated_user(user: LoggedInUser) -> PopulatedUser:
    return PopulatedUser(user)

def populated_users(room: Room) -> list[PopulatedUser]:
    l = [try_get_user(u) for u in room.members]
    return [populated_user(u) for u in l if u is not None]

def get_populated_user_from_request(request) -> PopulatedUser | None:
    u = get_user_from_request(request)
    if u is None:
        return None
    return populated_user(u)

def get_active_user_from_request(request) -> tuple[PopulatedUser, Room] | None:
    u = get_populated_user_from_request(request)
    if u is None:
        return None
    r = u.get_room()
    if r is None:
        return None
    return (u, r)

def get_started_room(request) -> tuple[PopulatedUser, Room, Draft] | None:
    u = get_populated_user_from_request(request)
    if u is None:
        return None
    r = u.get_room()
    if r is None or r.draft is None:
        return None
    return (u, r, r.draft)

def get_admin_from_request(request) -> tuple[PopulatedUser, Room] | None:
    ad = get_active_user_from_request(request)
    if ad is None:
        return None
    u, r = ad
    if u.uuid != r.admin:
        return None
    return (u, r)

def get_admin_in_unstarted_room(request) -> tuple[PopulatedUser, Room] | None:
    IL = IndentLog()
    IL("-- get_admin_in_unstarted_room --")
    ad = get_active_user_from_request(request)
    if ad is None:
        IL("-> no active user found from request")
        return None
    u, r = ad
    if u.uuid != r.admin:
        IL("-> active user was not admin")
        return None
    if r.drafting():
        IL("-> room was already started")
        return None
    IL("-> successfully got admin")
    return (u, r)

def update_user(user: LoggedInUser, key: str, value: Any):
    with sql as cur:
        cur.execute("UPDATE users SET ? = ? WHERE uuid = ?", (key, value, user.uuid))
