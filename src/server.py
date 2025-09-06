import secrets
import time
from typing import Any, Callable, Coroutine

import jwt
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import db
import rooms
from db import setup_sqlite
from models.api_model import APIErrorType, AuthenticationFailure, AuthenticationResult, AuthenticationSuccess, api_error
from models.room_model import APIError, Room, RoomIdentifier, RoomJoinError, RoomJoinState, RoomResult
from models.model import LoggedInUser, MojangInfo
from db import insert_user
from utils import get_user_from_request, validate_mojang_session

setup_sqlite()

JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"

# https://pyjwt.readthedocs.io/en/stable/
# https://sessionserver.mojang.com/session/minecraft/hasJoined?username=DesktopFolder&serverId=draaft2025server


app = FastAPI()


################## Middlewares #####################


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
            return PlainTextResponse("bad request, sorry mate", status_code=403)
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return PlainTextResponse("token expired", status_code=403)
        except jwt.InvalidTokenError:
            return PlainTextResponse("invalid token", status_code=403)
        request.state.valid_token = token
        request.state.logged_in_user = db.get_user(
            username=payload["username"], uuid=payload["uuid"])

    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=('*'),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


################### Routes #####################

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
    print(f"Got user: {user}")
    room = rooms.get_room_from_code(user.room_code)
    print(f"Got room: {room}")
    if room is None:
        return api_error(APIError(error_message="no room found for user"), response, status.HTTP_404_NOT_FOUND)
    return room


@app.get("/room/create")
async def create_room(request: Request) -> RoomResult:
    # The user must be authenticated to get this.
    # Only create a room if the user is not already joined to a room.
    user = get_user_from_request(request)
    rejoin_result = await handle_room_rejoin(user, lambda: create_room(request))
    if rejoin_result is not None:
        return rejoin_result
    room_code = rooms.create(user.uuid)
    return RoomResult(code=room_code, state=RoomJoinState.created)


@app.post("/room/join")
async def join_room(request: Request, response: Response, room_code: RoomIdentifier) -> RoomResult | RoomJoinError:
    user = get_user_from_request(request)
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
async def get_user(request: Request, response: Response) -> LoggedInUser:
    user = get_user_from_request(request)
    if user is None:
        return api_error(APIErrorType(message="Could not find user"), response)
    return user
