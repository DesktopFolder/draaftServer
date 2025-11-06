from enum import Enum
from typing import Literal
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Response

from utils import LOG

rt = APIRouter(prefix='/draft')

class AutoName(BaseModel):
    @staticmethod
    def make_simple(name: str) -> 'AutoName':
        return AutoName(full_name=name, short_name=name)

    full_name: str
    short_name: str

class Draftable(BaseModel):
    # How other objects refer to this object
    key: str

    name: AutoName

    # Generally, the pop-up text for this object
    description: str

    # The image tied to this object
    image_uri: str

    @staticmethod
    def basic(key: str, description: str, image: str | None = None, name: str | None = None) -> "Draftable":
        if image is None:
            image = f'{key}.png'
        if name is None:
            name = key
        return Draftable(key=key, name=AutoName.make_simple(name), description=description, image_uri=image)

class PoolTypeEnum(str, Enum):
    icons = 'icons'
    auto_names = 'auto_names'

class DraftPool(BaseModel):
    name: AutoName

    # Draftables (keys)
    contains: list[str]

    # Pool type
    kind: PoolTypeEnum


DRAFTABLES: dict[str, Draftable] = {}
_draftable_file = "draftables.json"
def _add_draftable(d: Draftable):
    DRAFTABLES[d.key] = d
_add_draftable(Draftable.basic(key="bucket", description="A fully-enchanted, max-tier bucket.", image="bucket.gif"))


# Configurable later, just get it working for now.
POOLS: list[DraftPool] = [
    DraftPool(name=AutoName.make_simple('Miscellaneous'), contains=["bucket"], kind=PoolTypeEnum.auto_names)
]


class DraftPick(BaseModel):
    # Key of the draftable
    key: str
    # UUID of the player who drafted it (for now, I guess)
    player: str
    # Number of the pick
    index: int


class DraftPickUpdate(DraftPick):
    variant: Literal['draftpick']


class Draft(BaseModel):
    @staticmethod
    def from_players(players: set[str]) -> 'Draft':
        import random
        p = list(players)
        random.shuffle(p)
        return Draft(players=p, position=list(p))

    def serialized(self) -> str:
        from models.ws import serialize
        res = serialize(self)
        if res is None:
            raise RuntimeError('Could not serialize draft object?!')
        return res

    players: list[str] = list()
    draft: list[DraftPick] = list()
    position: list[str] = list()
    picked: set[str] = set()

@rt.get('/status')
async def get_status(request: Request) -> Draft:
    from db import get_started_room
    LOG("Getting status of room...")
    ru = get_started_room(request)
    if ru is None:
        raise HTTPException(status_code=404, detail="no valid draft found")
    return ru[2]

@rt.get('/draftables')
async def get_draftables() -> tuple[list[DraftPool], dict[str, Draftable]]:
    return (POOLS, DRAFTABLES)

@rt.post('/pick')
async def do_pick(request: Request, key: str):
    from db_utils import always_get_drafting_player
    from room_manager import mg
    from rooms import update_draft
    user, room, draft = always_get_drafting_player(request)
    
    if user.uuid != draft.position[0]:
        raise HTTPException(status_code=403, detail="You cannot pick right now.")
    if key not in DRAFTABLES:
        raise HTTPException(status_code=404, detail=f"Draft pick {key} could not be found.")
    if key in draft.picked:
        raise HTTPException(status_code=403, detail=f"The key {key} has already been picked.")

    p = DraftPick(key=key, player=user.uuid, index=len(draft.draft))

    draft.position.pop(0)
    draft.draft.append(p)
    if not draft.position:
        num_picks = len(draft.draft)
        num_players = len(draft.players)
        assert num_picks % num_players == 0
        if (num_picks / num_players) % 2 == 1:
            # 4 picks, 4 players -> 1 -> reversed
            # 8 picks, 4 players -> 2 -> not reversed...
            draft.position = list(reversed(draft.players))
        else:
            draft.position = list(draft.players)

    draft.picked.add(key)
    if not update_draft(draft, room.code):
        raise HTTPException(status_code=500, detail='Could not update draft internally..!')

    await mg.broadcast_room(room, p)
