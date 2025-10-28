from pydantic import BaseModel, Field, ValidationError
from typing import Literal, TypeVar, Union, Type
from enum import Enum

from models.room import RoomConfig

"""
Client -> Server:
    - Do we care about heartbeats?
        - Send ping/pong, apparently JS should autorespond with pong
        - https://stackoverflow.com/questions/63847205/fastapi-websocket-ping-pong-timeout.
            - tl;dr no reason to implement heartbeats for now.
    
"""

class Heartbeat(BaseModel):
    variant: Literal['<3 you matter']

class RoomActionEnum(str, Enum):
    start = 'start'
    close = 'close'

class RoomAction(BaseModel):
    variant: Literal['roomaction']
    action: RoomActionEnum

class PlayerActionEnum(str, Enum):
    kick = 'kick'
    leave = 'leave'
    spectate = 'spectate'
    player = 'player'
    joined = 'joined'

NON_ADMIN_PLAYER_ACTIONS = ['leave', 'joined']

class PlayerAction(BaseModel):
    variant: Literal['playeraction']
    uuid: str
    action: PlayerActionEnum

class PlayerUpdate(BaseModel):
    variant: Literal['playerupdate'] = 'playerupdate'
    uuid: str
    action: PlayerActionEnum

class RoomUpdateEnum(str, Enum):
    closed = 'closed'
    config = 'config'
    commenced = 'commenced'

class RoomUpdate(BaseModel):
    variant: Literal['roomupdate'] = 'roomupdate'
    update: RoomUpdateEnum
    config: RoomConfig | None = None

class RoomStatus(BaseModel):
    variant: Literal['roomdata'] = 'roomdata'
    players: list[str] # list of player usernames
    admin: str # username of admin player

class ActionError(BaseModel):
    variant: Literal['error'] = 'error'
    text: str

# Received by the server, so RoomStatus is not valid (we only send those)
class WebSocketMessage(BaseModel):
    message: Union[Heartbeat, RoomAction, PlayerAction] = Field(discriminator='variant')

    @staticmethod
    def deserialize(data: str) -> 'WebSocketMessage | None':
        import json
        try:
            # Ignore the type check error here lol, it works
            return WebSocketMessage(message=json.loads(data))
        except Exception as e:
            print(f'Warning: Got a bad deserialize: {e}')

def serialize(rs: BaseModel):
    return rs.model_dump_json()

DeserializeType = TypeVar('DeserializeType')
def deserialize(js: str, deserialize_type: Type[DeserializeType]) -> DeserializeType | None:
    import json
    try:
        return deserialize_type(**json.loads(js))
    except Exception:
        return None
