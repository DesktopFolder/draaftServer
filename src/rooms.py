from db import cur
import string
import random
from sqlite3 import IntegrityError

from models.room_model import Room
from db import DB


def generate_code() -> str:
    return ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=7))


# Returns a room code and creates the room :)
def create(uuid: str) -> str:
    while True:
        room_code = generate_code()
        try:
            cur.execute(
                "INSERT INTO rooms (code, admin) VALUES (?,?);", (room_code, uuid))
            cur.execute("UPDATE users SET room_code = ? WHERE uuid = ?",
                        (room_code, uuid))
            DB.commit()
            return room_code
        except IntegrityError:
            # Duplicate code, try again
            # Not sure if this is needed as the collision space in 36^7 (78 billion possible codes)
            continue


def get_room_from_code(room_code: str) -> Room | None:
    """ Returns a Room object from a room code, or None if not found """
    if not room_code:
        return None
    res = cur.execute(
        "SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchall()
    if not res:
        return None
    room_code = res[0][1]
    admin = res[0][2]
    members_res = cur.execute(
        "SELECT uuid FROM users WHERE room_code = ?", (room_code,)).fetchall()
    members = set(m[0] for m in members_res)
    room_code = str(room_code) if room_code is not None else ""
    return Room(code=room_code, members=members, admin=admin)


def add_room_member(room_code: str, uuid: str) -> bool:
    """ Adds a user to a room by room code. Returns True on success, False on failure (room not found or other db issue) """
    try:
        cur.execute("UPDATE users SET room_code = ? WHERE uuid = ?",
                    (room_code, uuid))
        DB.commit()
        return True
    except IntegrityError:
        return False


def remove_room_member(uuid: str) -> bool:
    try:
        cur.execute("UPDATE users SET room_code = NULL WHERE uuid = ?",
                    (uuid,))
        DB.commit()
        return True
    except IntegrityError:
        return False


def get_user_room_code(uuid: str) -> str | None:
    """ Returns the room code the user is in, or None if not in a room """
    res = cur.execute("SELECT room_code FROM users WHERE uuid = ?",
                      (uuid,)).fetchall()
    if not res or res[0][0] is None:
        return None
    return res[0][0]
