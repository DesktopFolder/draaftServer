import sqlite3

from models.model import LoggedInUser

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
        return False


def get_user(username: str, uuid: str):
    # TODO - update username if changed or be dynamic elsewhere
    res = cur.execute("SELECT * FROM users WHERE uuid = ?", (uuid,)).fetchall()
    if not res:
        insert_user(username, uuid)
        return get_user(username, uuid)
    _, uuid, username, room_code = res[0]
    return LoggedInUser(username=username, uuid=uuid, room_code=room_code)
