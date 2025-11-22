from enum import Enum
from pydantic import BaseModel
from typing import Self, get_type_hints, Optional

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


# really really awkward that we seemingly have to do this.
# workarounds are atrocious, basically.
OPTIONALS = { 'overworld_seed': int, 'nether_seed': int, 'end_seed': int }


def check_type(k, v, data):
    if k not in data:
        return False
    if k in OPTIONALS:
        return v is None or isinstance(v, OPTIONALS[k])
    return isinstance(v, type(data[k]))


class RoomConfig(BaseModel):
    enforce_timer: bool = False
    pick_time: int = 15
    spectators_get_world: bool = False
    gambits: bool = True
    overworld_seed: int | None = None
    nether_seed: int | None = None
    end_seed: int | None = None


    def merge_config(self, other_config: dict) -> tuple[Self, set[str]]:
        import json
        from models.ws import deserialize, serialize

        our_data: dict = json.loads(serialize(self))
        other_config = {
            k: v
            for (k, v) in other_config.items()
            if check_type(k, v, our_data)
        }
        if not other_config:
            return self
        for k, v in other_config.items():
            our_data[k] = v
        return RoomConfig(**our_data), set(other_config.keys())


class RoomState(BaseModel):
    overworld_seed: int | None = None
    nether_seed: int | None = None
    end_seed: int | None = None

    def start_draft(self):
        from seeds import get_overworld, get_nether, get_end
        if self.overworld_seed is None:
            self.overworld_seed = get_overworld()
        if self.nether_seed is None:
            self.nether_seed = get_nether()
        if self.end_seed is None:
            self.end_seed = get_end()


class Room(BaseModel):
    code: str
    members: set[str]

    # Room creator UUID
    admin: str

    config: RoomConfig
    draft: None | Draft = None
    state: RoomState

    def drafting(self) -> bool:
        return self.draft is not None and not self.draft.complete

    def set_drafting(self):
        from db import DB, cur
        from models.ws import serialize
        from sqlite3 import IntegrityError

        self.state.start_draft()

        try:
            cur.execute(
                "UPDATE rooms SET draft = CASE WHEN draft IS NULL THEN ? ELSE draft END WHERE code = ?",
                (serialize(Draft.from_players(self.get_players())), self.code),
            )
            cur.execute(
                "UPDATE rooms SET state = ? WHERE code = ?",
                (serialize(self.state), self.code),
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
