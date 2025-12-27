from pydantic import BaseModel

from utils import LOG


class Completion(BaseModel):
    uuid: str # user who completed the run
    username: str # user who completed the run's username

    room: str # room id of the run

    start: float
    end: float

    # tag id for later lookups
    tag: None | str = None

    # todo - should we have the gambits/etc?
    
    # Let's just bake this into the type. It just seems... easier.
    def insert_into_db(self) -> bool:
        from db import sql
        import sqlite3
        try:
            with sql as cur:
                cur.execute("INSERT INTO completions (uuid, username, room, start, end, tag) VALUES (?,?,?,?,?,?)",
                            (self.uuid, self.username, self.room, self.start, self.end, self.tag))
            return True
        except sqlite3.IntegrityError as e:
            LOG("Failed insert_completion with error:", e)
            return False

    @staticmethod
    def from_tuple(tup):
        uuid, username, room, start, end, tag = tup
        return Completion(uuid=uuid, username=username, room=room, start=start, end=end, tag=tag)
