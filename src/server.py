import secrets
import time
from typing import Any, Callable, Coroutine

import jwt
from fastapi import FastAPI, Request, Response, WebSocketDisconnect, status, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import db
import rooms
from db import insert_user, setup_sqlite
from models.api import (APIError, APIErrorType, AuthenticationFailure,
                        AuthenticationResult, AuthenticationSuccess, api_error)
from models.generic import LoggedInUser, MojangInfo
from models.room import (Room, RoomIdentifier, RoomJoinError, RoomJoinState,
                         RoomResult)
from utils import get_user_from_request, validate_mojang_session
import sys

setup_sqlite()

JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
DEV_MODE_NO_AUTHENTICATE = True

if DEV_MODE_NO_AUTHENTICATE and 'dev' not in sys.argv:
    raise RuntimeError(f'Do not deploy without setting dev mode to False!')

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


@app.middleware("http")
async def check_valid(request: Request, call_next):
    request.state.valid_token = None

    public_routes = {
        '/',
        '/authenticate',
        "/docs",
        "/openapi.json",
    }

    if request.url.path not in public_routes:
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=('*'),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


################### Routes #####################

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
        insert_user(username=payload['username'], uuid=payload['uuid'])
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


async def handle_room_rejoin(user: LoggedInUser, cb: Callable[[], Coroutine[Any, Any, RoomResult]]) -> RoomResult | None:
    if user.room_code is not None:
        room = rooms.get_room_from_code(user.room_code)
        if room is None:
            # Handle room timeout / deletion
            user.room_code = None
            return await cb()
        if user.uuid in room.members:
            return None  # User is still in room. Shouldn't happen, but just in case
        if user.uuid == room.admin:
            return RoomResult(code=room.code, state=RoomJoinState.rejoined_as_admin)
        return RoomResult(code=room.code, state=RoomJoinState.rejoined)
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
    return RoomResult(code=room_code, state=RoomJoinState.created)


@app.post("/room/join")
async def join_room(request: Request, response: Response, room_code: RoomIdentifier) -> RoomResult | RoomJoinError:
    user = get_user_from_request(request)
    assert user
    rejoin_result = await handle_room_rejoin(user, lambda: create_room(request))
    if rejoin_result is not None:
        return rejoin_result
    if rooms.get_room_from_code(room_code.code) is None:
        return api_error(RoomJoinError(error_message=f"no such room: {room_code.code}"), response)
    # User can join this room!
    user.room_code = room_code.code
    addUserAttempt = rooms.add_room_member(room_code.code, user.uuid)
    if not addUserAttempt:
        # At some point we might want to differentiate these errors (i.e. room full vs other)
        return api_error(RoomJoinError(error_message=f"could not add user to room: {room_code.code}"), response)
    return RoomResult(code=room_code.code, state=RoomJoinState.joined)


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
    print('Got a connect / listen call with a websocket')
    user = token_to_user(token)
    full_user = db.populated_user(user)
    # Sane maximum
    if full_user.state.connections >= 10:
        raise RuntimeError("Max connections exceeded")
    # Do not increase connections until accept() succeeds
    await websocket.accept()
    full_user.state.connections += 1
    try:
        while True:
            data = await websocket.receive_text()
            print(data)
            await websocket.send_text('yeah got ur message' + data)
    except WebSocketDisconnect:
        pass
