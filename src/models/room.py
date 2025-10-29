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


class RoomJoinError(APIError):
    pass


class RoomConfig(BaseModel):
    enforce_timer: bool = False
    pick_time: int = 15
    spectators_get_world: bool = False

    def merge_config(self, other_config: dict) -> Self:
        import json
        from models.ws import deserialize, serialize
        our_data: dict = json.loads(serialize(self))
        other_config = {k: v for (k, v) in other_config if (k in our_data and isinstance(v, type(our_data[k])))}
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
