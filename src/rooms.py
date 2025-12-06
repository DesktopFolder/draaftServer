import string
import random
from sqlite3 import IntegrityError
from draft import Draft

from models.room import Room, RoomConfig, RoomState
from models.ws import deserialize, serialize


def generate_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=7))


# Returns a room code and creates the room :)
def create(uuid: str) -> str:
    from db import sql

    while True:
        room_code = generate_code()
        try:
            with sql as cur:
                cur.execute(
                    "INSERT INTO rooms (code, admin) VALUES (?,?);", (room_code, uuid)
                )
                cur.execute(
                    "UPDATE users SET room_code = ? WHERE uuid = ?", (room_code, uuid)
                )
            return room_code
        except IntegrityError:
            # Duplicate code, try again
            # Not sure if this is needed as the collision space in 36^7 (78 billion possible codes)
            continue


def get_room_from_code(room_code: str) -> Room | None:
    from db import sql

    """ Returns a Room object from a room code, or None if not found """
    if not room_code:
        return None
    with sql as cur:
        res = cur.execute("SELECT * FROM rooms WHERE code = ?", (room_code,)).fetchall()
        if not res:
            return None
        room_code = res[0][1]
        admin = res[0][2]
        members_res = cur.execute(
            "SELECT uuid FROM users WHERE room_code = ?", (room_code,)
        ).fetchall()
    members = set(m[0] for m in members_res)
    room_code = str(room_code) if room_code is not None else ""
    rc = deserialize(res[0][3], RoomConfig)
    if rc is None:
        print("ERROR: Could not deserialize room config:", res[0][3])
        rc = RoomConfig()
    dr = deserialize(res[0][4], Draft)
    roomstate = deserialize(res[0][5], RoomState)
    assert roomstate is not None
    return Room(code=room_code, members=members, admin=admin, config=rc, draft=dr, state=roomstate)


def update_config(config: str, code: str) -> bool:
    from db import sql

    """ Adds a user to a room by room code. Returns True on success, False on failure (room not found or other db issue) """
    try:
        with sql as cur:
            cur.execute("UPDATE rooms SET config = ? WHERE code = ?", (config, code))
        return True
    except IntegrityError:
        return False


def update_draft(draft: Draft, code: str) -> bool:
    from db import sql

    """ Adds a user to a room by room code. Returns True on success, False on failure (room not found or other db issue) """
    try:
        with sql as cur:
            cur.execute(
                "UPDATE rooms SET draft = ? WHERE code = ?", (serialize(draft), code)
            )
        return True
    except IntegrityError:
        return False


def add_room_member(room_code: str, uuid: str) -> bool:
    from db import sql

    """ Adds a user to a room by room code. Returns True on success, False on failure (room not found or other db issue) """
    try:
        with sql as cur:
            cur.execute("UPDATE users SET room_code = ? WHERE uuid = ?", (room_code, uuid))
        return True
    except IntegrityError:
        return False


def remove_room_member(uuid: str) -> bool:
    from db import sql

    """
    If a room member is the admin, we must destroy the room.
    """
    rm = get_room_from_uuid(uuid)
    if rm is None:
        return False  # Some error!
    try:
        if rm.admin == uuid:
            uuids = list(rm.members)
            # Destroy the room
            with sql as cur:
                cur.execute("DELETE FROM rooms WHERE code = ?", (rm.code,))
        else:
            uuids = [uuid]
        fmt = ",".join("?" * len(uuids))
        with sql as cur:
            cur.execute(f"UPDATE users SET room_code = NULL WHERE uuid IN ({fmt})", uuids)
        return True
    except IntegrityError:
        return False


def get_user_room_code(uuid: str) -> str | None:
    from db import sql

    """ Returns the room code the user is in, or None if not in a room """
    with sql as cur:
        res = cur.execute("SELECT room_code FROM users WHERE uuid = ?", (uuid,)).fetchall()
    if not res or res[0][0] is None:
        return None
    return res[0][0]


def get_room_from_uuid(uuid: str) -> Room | None:
    code = get_user_room_code(uuid)
    if code is None:
        return None
    return get_room_from_code(code)
