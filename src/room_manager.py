from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from db import PopulatedUser, get_user_status
from models.room import Room, RoomConfig
from models.ws import PlayerActionEnum, PlayerUpdate, RoomUpdate, RoomUpdateEnum, serialize
from utils import LOG
import rooms

# Registered clients
CLIENT_TO_WEBSOCKET: dict[str, WebSocket] = dict()
WEBSOCKET_TO_CLIENT: dict[WebSocket, str] = dict()

async def handle_client_metadata(metadata: str, full_user: PopulatedUser, websocket: WebSocket):
    block = metadata.strip('# \n')
    if block == 'register_client':
        if full_user.uuid in CLIENT_TO_WEBSOCKET:
            raise WebSocketDisconnect(1000, reason = "cannot connect twice")
        CLIENT_TO_WEBSOCKET[full_user.uuid] = websocket
        WEBSOCKET_TO_CLIENT[websocket] = full_user.uuid
        return

    if full_user.uuid not in CLIENT_TO_WEBSOCKET:
        # Invalid? I guess.
        LOG("Got bad data from non-client:", metadata)
        return

    if block in ['ready', 'unready']:
        r = full_user.get_room()
        if r is None:
            return
        await r.set_ready(full_user.uuid, block)



class RoomManager:
    def __init__(self):
        self.users: defaultdict[str, set[WebSocket]] = defaultdict(lambda: set())
        self.room_updates = dict()

    def subscribe(self, websocket: WebSocket, user: PopulatedUser):
        self.users[user.uuid].add(websocket)

    def unsubscribe(self, websocket: WebSocket, user: PopulatedUser):
        self.users[user.uuid].remove(websocket)
        if websocket in WEBSOCKET_TO_CLIENT:
            u = WEBSOCKET_TO_CLIENT[websocket]
            WEBSOCKET_TO_CLIENT.pop(websocket)
            CLIENT_TO_WEBSOCKET.pop(u)

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

    async def update_room(self, room: Room, c: RoomConfig):
        from asyncio import create_task
        # TODO: This should really be buffered. Update the room after a second with the latest information.
        # Update the db first, then send the update, I guess
        if room.code not in self.room_updates:
            create_task(update_room_delayed(self, room))
        self.room_updates[room.code] = c

    async def send_join(self, ws: WebSocket, room: Room):
        # Send any information that wasn't initially sent.
        for m in room.members:
            if get_user_status(m) != "player":
                await self.send_ws(ws, PlayerUpdate(uuid=m, action=PlayerActionEnum.spectate))


mg = RoomManager()

async def update_room_delayed(mgr: RoomManager, room: Room):
    from asyncio import sleep
    await sleep(1)
    c = mgr.room_updates[room.code]
    mgr.room_updates.pop(room.code)
    await mgr.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.config, config=c))
