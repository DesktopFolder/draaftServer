from collections import defaultdict

from fastapi import WebSocket
from pydantic import BaseModel

from db import PopulatedUser, get_user_status
from models.room import Room, RoomConfig
from models.ws import PlayerActionEnum, PlayerUpdate, RoomUpdate, RoomUpdateEnum, serialize
from utils import LOG
import rooms


class RoomManager:
    def __init__(self):
        self.users: defaultdict[str, set[WebSocket]] = defaultdict(lambda: set())

    def subscribe(self, websocket: WebSocket, user: PopulatedUser):
        self.users[user.uuid].add(websocket)

    def unsubscribe(self, websocket: WebSocket, user: PopulatedUser):
        self.users[user.uuid].remove(websocket)

    async def broadcast_room(self, room: Room, data: BaseModel):
        ser = serialize(data)
        for m in room.members:
            wso = self.users.get(m)
            if wso is None:
                LOG("No websockets found for user", m)
                continue
            for ws in wso:
                await ws.send_text(ser)

    async def send_ws(self, ws: WebSocket, data: BaseModel):
        await ws.send_text(serialize(data))

    async def add_user(self, room: Room, user: str):
        if not rooms.add_room_member(room.code, user):
            LOG("Failed adding user", user, "to room", room.code)
            return False
        LOG("Broadcasting room", room.code, "notice that player", user, "joined.")
        await self.broadcast_room(room, PlayerUpdate(uuid=user, action=PlayerActionEnum.joined))
        return True

    async def update_status(self, room: Room, user: str, status: PlayerActionEnum):
        await self.broadcast_room(room, PlayerUpdate(uuid=user, action=status))

    async def update_room(self, room: Room, c: RoomConfig, restrict: set[str] | None = None):
        # Update the db first, then send the update, I guess
        if restrict is not None:
            await self.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.config, config=c))
        else:
            await self.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.config, config=c))

    async def send_join(self, ws: WebSocket, room: Room):
        # Send any information that wasn't initially sent.
        for m in room.members:
            if get_user_status(m) != "player":
                await self.send_ws(ws, PlayerUpdate(uuid=m, action=PlayerActionEnum.spectate))


mg = RoomManager()
