from asyncio import Task
from enum import Enum
from pydantic import BaseModel
from typing import Self, get_type_hints, Optional

from models.api import APIError
from draft import Draft
from utils import LOG


# These players are, if they create a room, allowed to mark it
# as a tournament room (ie. tracked live, in theory)
ADMINS = set(['5d831a52730a4b4dadb7d1ea69617f3e', # DesktopFolder
              'f41c16957a9c4b0cbd2277a7e28c37a6', # PacManMVC
              '9038803187de426fbc4eea42e19c68ef', # me_nx
              '810ad7db704a46039dd3eaacd2908553', # Memerson
          ])


class RoomJoinState(str, Enum):
    created = "created"
    rejoined = "rejoined"
    rejoined_as_admin = "rejoined_as_admin"
    joined = "joined"


class RoomIdentifier(BaseModel):
    code: str


class RoomJoinError(APIError):
    pass


# really really awkward that we seemingly have to do this.
# workarounds are atrocious, basically.
OPTIONALS = { 'overworld_seed': str, 'nether_seed': str, 'end_seed': str }
INTS = { 'max_gambits', 'pick_time' }


def check_type(k, v, data):
    if isinstance(v, str):
        if len(v) > 64:
            return False
        if '\n' in v:
            return False
    import re
    if k not in data:
        return False
    if not isinstance(k, str):
        return False
    if (k.endswith('seed') or k in INTS) and (not isinstance(v, str) or re.match(r'^-?\d+$', v) is None):
        return False
    if k in OPTIONALS:
        return v is None or isinstance(v, OPTIONALS[k])
    return isinstance(v, type(data[k]))


class RoomConfig(BaseModel):
    enforce_timer: bool = False
    pick_time: str = '30'
    spectators_get_world: bool = False

    enable_gambits: bool = True
    max_gambits: str = '3'

    overworld_seed: str | None = None
    nether_seed: str | None = None
    end_seed: str | None = None

    restrict_players: list[str] = list()

    # If true, generate a live game JSON definition after draft completion
    live_game: bool = False

    # If true, require that the draft is finished specifically through /draft/finish
    admin_starts_game: bool = False

    # If true, it's an OQ submission
    open_qualifier_submission: bool = False

    def merge_config(self, other_config: dict) -> tuple[Self, set[str]]:
        import json
        from models.ws import serialize

        our_data: dict = json.loads(serialize(self))
        other_config = {
            k: v
            for (k, v) in other_config.items()
            if check_type(k, v, our_data)
        }
        print(other_config)
        if not other_config:
            return self, set()
        for k, v in other_config.items():
            our_data[k] = v
        return RoomConfig(**our_data), set(other_config.keys())


class RoomState(BaseModel):
    overworld_seed: str | None = None
    nether_seed: str | None = None
    end_seed: str | None = None

    player_advancements: dict[str, set[str]] = dict()

    ready_players: set[str] = set()
    has_sent_start: bool = False

    def start_draft(self, o):
        from seeds import get_overworld, get_nether, get_end
        assert isinstance(o, Room)

        self.overworld_seed = o.config.overworld_seed
        self.nether_seed = o.config.nether_seed
        self.end_seed = o.config.end_seed

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

    def admin_owned(self) -> bool:
        return self.admin in ADMINS

    def drafting(self) -> bool:
        return self.draft is not None and not self.draft.complete

    def playing(self) -> bool:
        return self.draft is not None and self.draft.complete

    def start_timer(self):
        import asyncio
        if not self.config.enforce_timer:
            return
        asyncio.create_task(pick_timer(self, 10))

    def num_picks(self):
        if self.draft is not None:
            return len(self.draft.draft)
        return 0

    async def check_all_ready(self):
        from room_manager import CLIENT_TO_WEBSOCKET, mg
        from models.ws import serialize
        from db import sql
        from models.ws import RoomUpdate, RoomUpdateEnum
        if self.draft is None or self.state.has_sent_start:
            return
        if not self.draft.complete:
            return
        for p in self.draft.players:
            if p in CLIENT_TO_WEBSOCKET:
                if p not in self.state.ready_players:
                    # Is a client, is not ready
                    return
        LOG(f'Sending game start to room {self.code}')
        self.state.has_sent_start = True

        # update first. I guess we might crash. but whatever.
        state = serialize(self.state)
        with sql as cur:
            cur.execute(
                "UPDATE rooms SET state = ? WHERE code = ?",
                (state, self.code),
            )

        await mg.broadcast_room(
            self,
            RoomUpdate(update=RoomUpdateEnum.loading_complete),
        )

    async def set_ready(self, player: str, value: str):
        from models.ws import serialize
        from db import sql
        if value == 'ready':
            self.state.ready_players.add(player)
        else:
            self.state.ready_players.remove(player)
        state = serialize(self.state)
        with sql as cur:
            cur.execute(
                "UPDATE rooms SET state = ? WHERE code = ?",
                (state, self.code),
            )

        await self.check_all_ready()

    def set_drafting(self):
        from db import sql
        from models.ws import serialize
        from sqlite3 import IntegrityError

        self.state.start_draft(self)

        try:
            draft = serialize(Draft.from_players(self.get_players()))
            state = serialize(self.state)
            with sql as cur:
                cur.execute(
                    "UPDATE rooms SET draft = CASE WHEN draft IS NULL THEN ? ELSE draft END WHERE code = ?",
                    (draft, self.code),
                )
                cur.execute(
                    "UPDATE rooms SET state = ? WHERE code = ?",
                    (state, self.code),
                )
        except IntegrityError:
            pass

    def save_state(self):
        from db import sql
        from models.ws import serialize
        state = serialize(self.state)
        with sql as cur:
            cur.execute(
                "UPDATE rooms SET state = ? WHERE code = ?",
                (state, self.code),
            )

    def updated(self):
        from rooms import get_room_from_code

        return get_room_from_code(self.code)

    def get_players(self):
        from db import get_user_status

        return set([m for m in self.members if get_user_status(m) == "player"])

    def as_result(self, state: RoomJoinState) -> 'RoomResult':
        return RoomResult(
            code=self.code,
            state=state,
            members=list(self.members),
            drafting=self.drafting(),
            playing=self.playing(),
            room=self,
        )


PICK_TIMERS: dict[str, Task] = {}
BUFFER_PICK: int = 1
async def pick_timer(room: Room, extra_seconds: int = 0):
    import asyncio
    if room.code in PICK_TIMERS:
        PICK_TIMERS[room.code].cancel()
    cur_task = asyncio.current_task()
    if cur_task is not None:
        PICK_TIMERS[room.code] = cur_task
    
    # Now sleep! :)
    await asyncio.sleep(int(room.config.pick_time) + extra_seconds + BUFFER_PICK)

    # now we pick!
    new_room = room.updated()
    if new_room is None:
        return
    if room.num_picks() != new_room.num_picks():
        # nothing doing
        return

    if new_room.draft is None:
        LOG(f"{new_room} has no draft?!")
        return
    
    await new_room.draft.random_pick(new_room)


class RoomResult(RoomIdentifier):
    state: RoomJoinState
    members: list[str]
    drafting: bool = False
    playing: bool = False
    room: Room
