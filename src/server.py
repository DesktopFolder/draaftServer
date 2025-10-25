from collections import defaultdict
from random import random, choice
import secrets
import time
from typing import Any, Callable, Coroutine

import jwt
from fastapi import FastAPI, Request, Response, WebSocketDisconnect, status, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import db
import rooms
from db import PopulatedUser, get_admin_from_request, get_populated_user_from_request, get_user_status, insert_update_status, insert_user, populated_user, setup_sqlite
from models.api import (APIError, APIErrorType, AuthenticationFailure,
                        AuthenticationResult, AuthenticationSuccess, api_error)
from models.generic import LoggedInUser, MojangInfo
from models.room import (Room, RoomConfig, RoomIdentifier, RoomJoinError, RoomJoinState,
                         RoomResult)
from models.ws import PlayerActionEnum, PlayerUpdate, RoomUpdate, RoomUpdateEnum, WebSocketMessage, serialize
from utils import get_user_from_request, validate_mojang_session
import sys

setup_sqlite()

JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
ALLOW_DEV = 'dev' in sys.argv
DEV_MODE_NO_AUTHENTICATE = False and ALLOW_DEV
DEV_MODE_WEIRD_ENDPOINTS = True and ALLOW_DEV

if DEV_MODE_WEIRD_ENDPOINTS and 'dev' not in sys.argv:
    raise RuntimeError(f'Do not deploy without setting dev mode to False!')
if DEV_MODE_NO_AUTHENTICATE and 'dev' not in sys.argv:
    raise RuntimeError(f'Do not deploy without setting dev mode to False!')

def nolog(*_, **__):
    pass
LOG = print

# https://pyjwt.readthedocs.io/en/stable/
# https://sessionserver.mojang.com/session/minecraft/hasJoined?username=DesktopFolder&serverId=draaft2025server


app = FastAPI()


################## Middlewares #####################


def token_to_user(token: str) -> LoggedInUser:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    user = db.get_user(username=payload["username"], uuid=payload["uuid"])
    if user is None:
        raise RuntimeError('could not make user')
    return user


PUBLIC_ROUTES = {
    "/",
    "/authenticate",
    "/version",
}
if 'dev' in sys.argv:
    PUBLIC_ROUTES.add("/docs")
    PUBLIC_ROUTES.add("/openapi.json")


@app.middleware("http")
async def check_valid(request: Request, call_next):
    request.state.valid_token = None

    if request.url.path not in PUBLIC_ROUTES:
        token = request.headers.get("token")
        if not token:
            return PlainTextResponse("bad request, sorry mate :/", status_code=403)
        try:
            user = token_to_user(token)
        except jwt.ExpiredSignatureError:
            return PlainTextResponse("token expired...", status_code=403)
        except jwt.InvalidTokenError:
            return PlainTextResponse("invalid token >:|", status_code=403)
        except RuntimeError:
            return PlainTextResponse("server error :(", status_code=500)
        request.state.valid_token = token
        request.state.logged_in_user = user

    return await call_next(request)

if 'dev' in sys.argv:
    allow_origins = ('*')
else:
    allow_origins = ('https://disrespec.tech', 'https://api.disrespec.tech')

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


################### Routes #####################
def make_fake_user(uuid: str, username: str):
    insert_user(username=username, uuid=uuid)

if DEV_MODE_NO_AUTHENTICATE:
    @app.get("/authenticate")
    async def authenticate_no_auth(uuid: str|None = None, username: str|None = None) -> AuthenticationResult:
        if uuid is None:
            # Look, it's simple and easy
            uuid = 'uuid1a52730a4b4dadb7d1ea6' + rooms.generate_code()
        if username is None:
            username = 'tester' + rooms.generate_code()
        # JWT payload
        payload = {
            "username": username,
            "uuid": uuid,
            "serverID": 'draafttestserver',
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60 * 24  # 24 hours expiry
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        # add user to db if not exists
        make_fake_user(payload['uuid'], payload['username'])
        return AuthenticationSuccess(token=token)
else:
    @app.post("/authenticate")
    async def authenticate(mi: MojangInfo) -> AuthenticationResult:
        result = await validate_mojang_session(mi.username, mi.serverID)
        if not result["success"]:
            return AuthenticationFailure(message=result["error"])
        resp_data = result["data"]

        # JWT payload
        payload = {
            "username": resp_data['name'],
            "uuid": resp_data['id'],
            "serverID": mi.serverID,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60 * 24  # 24 hours expiry
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        # add user to db if not exists
        insert_user(username=resp_data['name'], uuid=resp_data['id'])
        return AuthenticationSuccess(token=token)


@app.get("/authenticated")
async def is_authenticated():
    return True

@app.get("/version")
async def server_version():
    return 1 # Version 1 until public beta


async def handle_room_rejoin(user: LoggedInUser, cb: Callable[[], Coroutine[Any, Any, RoomResult]] | None) -> RoomResult | None:
    if user.room_code is not None:
        LOG("User had room code...")
        room = rooms.get_room_from_code(user.room_code)
        if room is None:
            # Handle room timeout / deletion
            LOG("...Room was timed out.")
            user.room_code = None
            # Update this in the DB as well.
            db.cur.execute(f"UPDATE users SET room_code = NULL WHERE uuid IN (?)", (user.uuid,))
            db.DB.commit()
            if cb is not None:
                return await cb()
            return None
        # if user.uuid in room.members:
        #     return None  # User is still in room. Shouldn't happen, but just in case
        if user.uuid == room.admin:
            return RoomResult(code=room.code, state=RoomJoinState.rejoined_as_admin, members=list(room.members))
        return RoomResult(code=room.code, state=RoomJoinState.rejoined, members=list(room.members))
    else:
        LOG("User did not have room code...")
    return None


@app.get("/room")
async def get_room(request: Request, response: Response) -> Room | APIError:
    print("Getting room for user...")
    user = get_user_from_request(request)
    assert user
    print(f"Got user: {user}")
    if user.room_code is None:
        return api_error(APIError(error_message="no room code found for user"), response, status.HTTP_404_NOT_FOUND)
    room = rooms.get_room_from_code(user.room_code)
    print(f"Got room: {room}")
    if room is None:
        return api_error(APIError(error_message="no room found for user's room code"), response, status.HTTP_404_NOT_FOUND)
    return room


@app.get("/room/create")
async def create_room(request: Request) -> RoomResult:
    # The user must be authenticated to get this.
    # Only create a room if the user is not already joined to a room.
    user = get_user_from_request(request)
    assert user
    rejoin_result = await handle_room_rejoin(user, lambda: create_room(request))
    if rejoin_result is not None:
        return rejoin_result
    room_code = rooms.create(user.uuid)
    return RoomResult(code=room_code, state=RoomJoinState.created, members=[user.uuid])


@app.post("/room/join")
async def join_room(request: Request, response: Response, room_code: RoomIdentifier) -> RoomResult | RoomJoinError:
    user = get_user_from_request(request)
    assert user
    rejoin_result = await handle_room_rejoin(user, None)
    if rejoin_result is not None:
        LOG("Got rejoin result:", rejoin_result)
        return rejoin_result
    LOG("Fresh room join from user", user.username)
    room = rooms.get_room_from_code(room_code.code)
    if room is None:
        return api_error(RoomJoinError(error_message=f"no such room: {room_code.code}"), response)
    # User can join this room!
    user.room_code = room_code.code
    addUserAttempt = rooms.add_room_member(room_code.code, user.uuid)
    if not addUserAttempt:
        # At some point we might want to differentiate these errors (i.e. room full vs other)
        return api_error(RoomJoinError(error_message=f"could not add user to room: {room_code.code}"), response)
    await mg.broadcast_room(room, PlayerUpdate(uuid=user.uuid, action=PlayerActionEnum.joined))
    room.members.add(user.uuid)
    return RoomResult(code=room_code.code, state=RoomJoinState.joined, members=list(room.members))


@app.post("/room/leave")
async def leave_room(request: Request):
    user = get_user_from_request(request)
    assert user
    rm = rooms.get_user_room_code(user.uuid)
    if rm is None:
        LOG("Could not leave room - Room does not exist")
        return
    room = rooms.get_room_from_code(rm)
    if room is None:
        LOG(f"Error: Could not get room from id {rm}")
        return
    isadmin = room.admin == user.uuid
    if isadmin:
        await mg.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.closed))
    else:
        await mg.broadcast_room(room, PlayerUpdate(uuid=user.uuid, action=PlayerActionEnum.leave))
    rooms.remove_room_member(user.uuid)

@app.post("/room/kick")
async def kick_room(request: Request, member: str):
    user = get_user_from_request(request)
    assert user
    rm = rooms.get_user_room_code(user.uuid)
    if rm is None:
        LOG("Could not kick from room - Room does not exist")
        return
    room = rooms.get_room_from_code(rm)
    if room is None:
        LOG(f"Error: Could not get room from id {rm}")
        return
    isadmin = room.admin == user.uuid
    if not isadmin or member == user.uuid:
        # They are not the room admin, kick them.
        # Alternatively, you can't kick yourself.
        return
    if member not in room.members:
        # Member also just doesn't exist.
        LOG("Could not kick from room - member is not in room.")
        return
    
    await mg.broadcast_room(room, PlayerUpdate(uuid=member, action=PlayerActionEnum.kick))
    rooms.remove_room_member(member)

@app.post("/room/swapstatus")
async def swap_status(request: Request, uuid: str):
    ad = get_admin_from_request(request)
    if ad is None:
        return
    _, r = ad

    # actually important check!
    if uuid not in r.members:
        return

    status = get_user_status(uuid)
    LOG("Current user status:", status)
    if status != "player":
        status = "player"
        await mg.update_status(r, uuid, PlayerActionEnum.player)
    else:
        status = "spectate"
        await mg.update_status(r, uuid, PlayerActionEnum.spectate)
    insert_update_status(uuid, status)


@app.post("/room/configure")
async def configure_room(request: Request, config: RoomConfig):
    ad = get_admin_from_request(request)
    if ad is None:
        return
    _, r = ad
    await mg.update_room(r, config)


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

    async def update_room(self, room: Room, c: RoomConfig):
        # Update the db first, then send the update, I guess
        await self.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.config, config=c))

    async def send_join(self, ws: WebSocket, room: Room):
        # Send any information that wasn't initially sent.
        for m in room.members:
            if get_user_status(m) != "player":
                await self.send_ws(ws, PlayerUpdate(uuid=m, action=PlayerActionEnum.spectate))


mg = RoomManager()


@app.get("/user")
async def get_user(request: Request, response: Response) -> LoggedInUser | APIError:
    user = get_user_from_request(request)
    if user is None:
        return api_error(APIError(error_message="Could not find user"), response)
    return user

@app.websocket("/listen")
async def websocket_endpoint(
    *,
    websocket: WebSocket,
    token: str    
):
    from handlers import handle_websocket_message
    LOG('Got a connect / listen call with a websocket')
    user = token_to_user(token)
    full_user = db.populated_user(user)
    room = full_user.get_room()
    if room is None:
        return # User must be in a room to be listening for updates.
    # Sane maximum
    if full_user.state.connections >= 10:
        raise RuntimeError(f"Max connections exceeded for user {user.username}")
    # Do not increase connections until accept() succeeds
    await websocket.accept()
    full_user.state.connections += 1
    mg.subscribe(websocket, full_user)
    await mg.send_join(websocket, room)
    try:
        while True:
            data = await websocket.receive_text()
            message = WebSocketMessage.deserialize(data)
            if message is not None:
                await handle_websocket_message(websocket, message, full_user)
            else:
                await websocket.send_text('{"status": "error"}')
    except WebSocketDisconnect:
        full_user.state.connections -= 1
    finally:
        mg.unsubscribe(websocket, full_user)

# Development endpoints.
if DEV_MODE_WEIRD_ENDPOINTS:
    @app.post("/dev/adduser")
    async def add_user(request: Request, response: Response):
        user = get_user_from_request(request)
        assert user
        room = db.populated_user(user).get_room()
        PAIRS = {
                "f41c16957a9c4b0cbd2277a7e28c37a6": "PacManMVC",
                "4326adfebd724170953fd8dabd660538": "Totorewa",
                "9038803187de426fbc4eea42e19c68ef": "me_nx",
                "810ad7db704a46039dd3eaacd2908553": "Memerson",
                "9a8e24df4c8549d696a6951da84fa5c4": "Feinberg",
                "562a308be86c4ec09438387860e792cc": "Oxidiot",
                "c17fdba3b5ee46179131c5b547069477": "Rejid",
                "dc2fe0a1c03647778ee98b80e53397a0": "CrazySMC",
                "afecd7c643b54d8a8a32b42a0db53418": "DoyPingu",
                "754f6771eeca46f3b4f293e90a8df75c": "coosh02",
                "c81a44e0c18544c29d1a93e0362b7777": "Snakezy",
                "4129d8d1aafb4e73b97b9999db248060": "CroProYT",
        }
        UUIDS = set(PAIRS.keys())
        if room is None:
            return
        valid_users = UUIDS - room.members
        if not valid_users:
            LOG("No valid users left to add to the room.")
            return
        to_add: str = choice(list(valid_users))
        make_fake_user(uuid=to_add, username=PAIRS[to_add])
        if not await mg.add_user(room, to_add):
            LOG("Failed to add made-up user")
        new_room = rooms.get_room_from_code(room.code)
        if new_room:
            LOG("Updated members, now contains:", new_room.members)

    @app.post("/dev/kickself")
    async def kick_self(request: Request, response: Response):
        user = get_user_from_request(request)
        assert user
        room = db.populated_user(user).get_room()
        if room is None:
            return
        if room.admin != user.uuid:
            return
        await mg.broadcast_room(room, PlayerUpdate(uuid=user.uuid, action=PlayerActionEnum.kick))
        # do nothing on backend. just broadcast the info...
        # rooms.remove_room_member(member)
