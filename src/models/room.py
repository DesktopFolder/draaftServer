from enum import Enum
from pydantic import BaseModel
from typing import Self

from models.api import APIError
from draft import Draft


class RoomJoinState(str, Enum):
    created = "created"
    rejoined = "rejoined"
    rejoined_as_admin = "rejoined_as_admin"
    joined = "joined"


class RoomIdentifier(BaseModel):
    code: str


class RoomResult(RoomIdentifier):
    state: RoomJoinState
    members: list[str]
    drafting: bool = False


class RoomJoinError(APIError):
    pass


class RoomConfig(BaseModel):
    enforce_timer: bool = False
    pick_time: int = 15
    spectators_get_world: bool = False
    gambits: bool = True

    def merge_config(self, other_config: dict) -> Self:
        import json
        from models.ws import deserialize, serialize

        our_data: dict = json.loads(serialize(self))
        other_config = {
            k: v
            for (k, v) in other_config
            if (k in our_data and isinstance(v, type(our_data[k])))
        }
        if not other_config:
            return self
        for k, v in other_config.items():
            our_data[k] = v
        return RoomConfig(**our_data)


class Room(BaseModel):
    code: str
    members: set[str]

    # Room creator UUID
    admin: str

    config: RoomConfig
    draft: None | Draft = None

    def drafting(self) -> bool:
        return self.draft is not None

    def set_drafting(self):
        from db import DB, cur
        from models.ws import serialize
        from sqlite3 import IntegrityError

        try:
            cur.execute(
                "UPDATE rooms SET draft = CASE WHEN draft IS NULL THEN ? ELSE draft END WHERE code = ?",
                (serialize(Draft.from_players(self.get_players())), self.code),
            )
            DB.commit()
        except IntegrityError:
            pass

    def updated(self):
        from rooms import get_room_from_code

        return get_room_from_code(self.code)

    def get_players(self):
        from db import get_user_status

        return set([m for m in self.members if get_user_status(m) == "player"])

    def as_result(self, state: RoomJoinState) -> RoomResult:
        return RoomResult(
            code=self.code,
            state=state,
            members=list(self.members),
            drafting=self.drafting(),
        )
