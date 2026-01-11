from random import choice
import time
from typing import Any, Callable, Coroutine
from datapack_utils import setup_datapack_caching
import asyncio

import jwt
from fastapi import (
    Body,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocketDisconnect,
    status,
    WebSocket,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import seeds

import db
import rooms
from db import (
    get_admin_from_request,
    get_admin_in_unstarted_room,
    get_user_status,
    insert_update_status,
    insert_user,
    setup_sqlite,
)
from models.api import (
    APIError,
    AuthenticationFailure,
    AuthenticationResult,
    AuthenticationSuccess,
    api_error,
)
from models.generic import LoggedInUser, MojangInfo, OQInfo, UserSettings
from models.room import Room, RoomIdentifier, RoomJoinError, RoomJoinState, RoomResult
from models.ws import (
    PlayerActionEnum,
    PlayerUpdate,
    RoomUpdate,
    RoomUpdateEnum,
    WebSocketMessage,
    serialize,
)
from utils import get_user_from_request, validate_mojang_session, LOG, persistent_token
import sys
from room_manager import mg, handle_client_metadata
from draft import rt
from lb import rt as lb_rt
from game import insert_test_completions, autoload_completions

setup_sqlite()
setup_datapack_caching()
autoload_completions()

if 'dev' in sys.argv:
    LOG("Inserting test completions (dev mode)")
    insert_test_completions()

JWT_SECRET = persistent_token(32, "JWT_SECRET")
JWT_ALGORITHM = "HS256"
ALLOW_DEV = "dev" in sys.argv
DEV_MODE_NO_AUTHENTICATE = False and ALLOW_DEV
DEV_MODE_WEIRD_ENDPOINTS = True and ALLOW_DEV

if DEV_MODE_WEIRD_ENDPOINTS and "dev" not in sys.argv:
    raise RuntimeError(f"Do not deploy without setting dev mode to False!")
if DEV_MODE_NO_AUTHENTICATE and "dev" not in sys.argv:
    raise RuntimeError(f"Do not deploy without setting dev mode to False!")

# https://pyjwt.readthedocs.io/en/stable/
# https://sessionserver.mojang.com/session/minecraft/hasJoined?username=DesktopFolder&serverId=draaft2025server


app = FastAPI()
app.include_router(rt)
app.include_router(lb_rt)

################## Middlewares #####################


def token_to_user(token: str) -> LoggedInUser:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    user = db.get_user(username=payload["username"], uuid=payload["uuid"])
    if user is None:
        raise RuntimeError("could not make user")
    return user


PUBLIC_ROUTES = {
    "/",
    "/authenticate",
    "/version",
    "/dev/becomeuser",
    "/draft/external/draftables",
    "/draft/external/room",
    "/lb/external/oq1",
    "/otplogin"
}
if "dev" in sys.argv:
    PUBLIC_ROUTES.add("/docs")
    PUBLIC_ROUTES.add("/openapi.json")
    PUBLIC_ROUTES.add("/dev/becomeuser")


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
        except RuntimeError as e:
            print(e)
            return PlainTextResponse("server error :(", status_code=500)
        request.state.valid_token = token
        request.state.logged_in_user = user

    return await call_next(request)


if "dev" in sys.argv:
    allow_origins = "*"
else:
    allow_origins = ("https://disrespec.tech", "https://api.disrespec.tech")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


################### Routes #####################
def make_fake_user(uuid: str, username: str):
    return insert_user(username=username, uuid=uuid)


if DEV_MODE_NO_AUTHENTICATE:

    @app.get("/authenticate")
    async def authenticate_no_auth(
        uuid: str | None = None, username: str | None = None
    ) -> AuthenticationResult:
        from utils import associate_username
        if uuid is None:
            # Look, it's simple and easy
            uuid = "uuid1a52730a4b4dadb7d1ea6" + rooms.generate_code()
        if username is None:
            username = "tester" + rooms.generate_code()
        # JWT payload
        payload = {
            "username": username,
            "uuid": uuid,
            "serverID": "draafttestserver",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60 * 24,  # 24 hours expiry
        }
        
        associate_username(uuid=uuid, username=username)

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        # add user to db if not exists
        make_fake_user(payload["uuid"], payload["username"])
        return AuthenticationSuccess(token=token)

else:

    @app.post("/authenticate")
    async def authenticate(mi: MojangInfo) -> AuthenticationResult:
        from utils import associate_username
        result = await validate_mojang_session(mi.username, mi.serverID)
        if not result["success"]:
            return AuthenticationFailure(message=result["error"])
        resp_data = result["data"]

        # JWT payload
        payload = {
            "username": resp_data["name"],
            "uuid": resp_data["id"],
            "serverID": mi.serverID,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60 * 24,  # 24 hours expiry
        }

        associate_username(uuid=resp_data["id"], username=resp_data["name"])

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        # add user to db if not exists
        insert_user(username=resp_data["name"], uuid=resp_data["id"])
        return AuthenticationSuccess(token=token)


@app.get("/authenticated")
async def is_authenticated():
    return True


@app.get("/version")
async def server_version():
    return 1  # Version 1 until public beta

NO_OTP = Response(
    "false",
    media_type=PlainTextResponse.media_type
)
OTP_LOOKUP = { }
OTP_PQ = [ ]
def generate_otp():
    import secrets
    import random
    import string
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=480)) + secrets.token_urlsafe(24)

async def clear_task():
    import time
    from utils import cache_usernames
    last_schedule = time.time()
    while True:
        now: float = time.time()

        # Scheduling.

        # Per five minutes.
        if now > (last_schedule + (60 * 5)):
            cache_usernames()

        while OTP_PQ:
            ts, otp = OTP_PQ[0]
            if now - 30 < ts:
                # has not been 30s yet
                break
            OTP_PQ.pop(0)
            if otp in OTP_LOOKUP:
                OTP_LOOKUP.pop(otp)
        await asyncio.sleep(30)

CLEAR_TASK = None

@app.get("/otp")
async def get_otp(request: Request):
    global CLEAR_TASK
    if CLEAR_TASK is None:
        CLEAR_TASK = asyncio.create_task(clear_task())

    import ipaddress
    import time
    # Guaranteed to be authenticated
    user_ip = request.headers.get('cf-connecting-ip')
    user_token = request.headers.get("token")

    if user_ip is None or user_token is None:
        LOG(f"Refused OTP for user with IP {user_ip} and token==None {user_token is None}")
        return NO_OTP

    addr = ipaddress.ip_address(user_ip)
    if addr.is_private:
        LOG("Refused OTP for user: IP address was private")
        pass

    otp = generate_otp()

    assert otp not in OTP_LOOKUP
    OTP_LOOKUP[otp] = (user_ip, user_token)
    OTP_PQ.append((time.time(), otp))

    return Response(otp, media_type=PlainTextResponse.media_type)


@app.get("/otplogin")
async def login_with_otp(request: Request, otp: str):
    if otp not in OTP_LOOKUP:
        raise HTTPException(status_code=404)
    uip, utok = OTP_LOOKUP.pop(otp)
    if request.headers.get("cf-connecting-ip") != uip:
        LOG("Got IP mismatch, ignored")
        # raise HTTPException(status_code=403)

    return Response(utok, media_type=PlainTextResponse.media_type)


@app.get("/lookup/{useridentifier}")
async def lookup_user(useridentifier: str):
    from utils import lookup_user
    return lookup_user(useridentifier)


async def handle_room_rejoin(
    user: LoggedInUser, cb: Callable[[], Coroutine[Any, Any, RoomResult]] | None
) -> RoomResult | None:
    if user.room_code is not None:
        LOG("User had room code...")
        room = rooms.get_room_from_code(user.room_code)
        if room is None:
            # Handle room timeout / deletion
            LOG("...Room was timed out.")
            user.room_code = None
            # Update this in the DB as well.
            with db.sql as cur:
                cur.execute(
                    f"UPDATE users SET room_code = NULL WHERE uuid IN (?)", (user.uuid,)
                )
            if cb is not None:
                return await cb()
            return None
        # if user.uuid in room.members:
        #     return None  # User is still in room. Shouldn't happen, but just in case
        if user.uuid == room.admin:
            return room.as_result(state=RoomJoinState.rejoined_as_admin)
        return room.as_result(state=RoomJoinState.rejoined)
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
        return api_error(
            APIError(error_message="no room code found for user"),
            response,
            status.HTTP_404_NOT_FOUND,
        )
    room = rooms.get_room_from_code(user.room_code)
    print(f"Got room: {room}")
    if room is None:
        return api_error(
            APIError(error_message="no room found for user's room code"),
            response,
            status.HTTP_404_NOT_FOUND,
        )
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
    room = rooms.get_room_from_code(room_code)
    assert room is not None
    return RoomResult(code=room_code, state=RoomJoinState.created, members=[user.uuid], room=room)


@app.post("/room/join")
async def join_room(
    request: Request, response: Response, room_code: RoomIdentifier
) -> RoomResult | RoomJoinError:
    user = get_user_from_request(request)
    assert user
    rejoin_result = await handle_room_rejoin(user, None)
    if rejoin_result is not None:
        LOG("Got rejoin result:", rejoin_result)
        return rejoin_result
    LOG("Fresh room join from user", user.username)
    room = rooms.get_room_from_code(room_code.code)
    if room is None:
        return api_error(
            RoomJoinError(error_message=f"no such room: {room_code.code}"), response
        )
    # User can join this room! room room room room HAAHAHAAHA TAKE THAT YOU ROOMS
    user.room_code = room_code.code
    addUserAttempt = rooms.add_room_member(room_code.code, user.uuid)
    if not addUserAttempt:
        # At some point we might want to differentiate these errors (i.e. room full vs other)
        return api_error(
            RoomJoinError(
                error_message=f"could not add user to room: {room_code.code}"
            ),
            response,
        )

    # Add the user to the room first, THEN broadcast to the room.
    room.members.add(user.uuid)
    await mg.broadcast_room(
        room, PlayerUpdate(uuid=user.uuid, action=PlayerActionEnum.joined)
    )

    # If the room is already live
    if room.drafting() or room.playing() or (room.config.restrict_players and user.uuid not in room.config.restrict_players):
        await mg.update_status(room, user.uuid, PlayerActionEnum.spectate)
        insert_update_status(user.uuid, "spectate")

    return room.as_result(state=RoomJoinState.joined)


@app.post("/room/leave")
async def leave_room(request: Request):
    from rooms import update_draft, destroy_room
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

    # ONLY delete the room for admins IFF draft is None
    # Note: We broadcast the information first, THEN remove the player
    if isadmin and room.draft is None:
        await mg.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.closed))
    else:
        await mg.broadcast_room(
            room, PlayerUpdate(uuid=user.uuid, action=PlayerActionEnum.leave)
        )
    rooms.remove_room_member(user.uuid, room.draft is not None)

    if room.draft is not None:
        if user.uuid in room.draft.players:
            room.draft.skip_players.add(user.uuid)
            # Update it here so we don't do it later
            update_draft(room.draft, room.code)

            # DESTROY THE ROOM IF EVERYONE LEAVES
            if all([p in room.draft.skip_players for p in room.draft.players]):
                destroy_room(room.code)
                await mg.broadcast_room(room, RoomUpdate(update=RoomUpdateEnum.closed))
                return # Return, don't do more logic

            await room.draft.do_skip(room)


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

    # Broadcast information first, THEN remove the player from the room.
    await mg.broadcast_room(
        room, PlayerUpdate(uuid=member, action=PlayerActionEnum.kick)
    )
    rooms.remove_room_member(member)


@app.post("/room/swapstatus")
async def swap_status(request: Request, uuid: str):
    ad = get_admin_in_unstarted_room(request)
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


@app.get("/usersettings")
async def get_settings(request: Request):
    u = get_user_from_request(request)
    if u is None:
        raise HTTPException(status_code=403, detail="you aren't logged in. no settings for you! >:|")

    return UserSettings(pronouns=u.pronouns)


@app.post("/settings")
async def set_user_settings(request: Request, s: UserSettings):
    u = get_user_from_request(request)
    if u is None:
        raise HTTPException(status_code=403, detail="you aren't logged in. no settings for you! >:|")

    if s.pronouns is not None:
        with db.sql as cur:
            cur.execute("UPDATE users SET pronouns = ? WHERE uuid = ?", (s.pronouns[:12], u.uuid))

    if s.twitch_username is not None:
        with db.sql as cur:
            cur.execute("UPDATE users SET twitch = ? WHERE uuid = ?", (s.twitch_username[:25], u.uuid))


@app.post("/room/configure")
async def configure_room(request: Request, payload: Any = Body(None)):
    ad = get_admin_in_unstarted_room(request)
    if ad is None:
        return
    _, r = ad

    if payload is None:
        LOG("Got empty payload for /room/configure")
        return

    LOG("Got configuration update:", payload)

    if r.drafting():
        # I guess technically this should be done at the sql level but whatever
        # Not really that worried about this
        LOG("Cannot modify a room's configuration once draft begins.")
        return

    if not isinstance(payload, dict):
        LOG("Got weird type", type(payload), "for /room/configure")
        return

    if not r.admin_owned():
        pass # TODO.

    new_config, changed_keys = r.config.merge_config(payload)

    rooms.update_config(code=r.code, config=serialize(new_config))
    await mg.update_room(r, new_config)


@app.post("/room/commence")
async def commence_room(request: Request):
    ad = get_admin_in_unstarted_room(request)
    if ad is None:
        return
    _, r = ad

    if not r.get_players():
        raise HTTPException(status_code=403, detail=f'Cannot start room {r.code} - no players.')
    if len(r.get_players()) > 4:
        raise HTTPException(status_code=403, detail=f'Cannot start room {r.code} - too many players ({len(r.get_players())})')

    LOG("Commencing room:", r.code)

    r.set_drafting()
    await mg.broadcast_room(r, RoomUpdate(update=RoomUpdateEnum.commenced, config=r.config))
    r.start_timer()


@app.post("/admin/register_completion")
async def force_register_completion(request: Request, room_id: str, rta_code: str):
    from db import get_user_from_request
    from models.room import ADMINS
    from rooms import get_room_from_code
    user = get_user_from_request(request)
    if user is None or user.uuid not in ADMINS:
        raise HTTPException(status_code=403)

    # Allow force registering a completion.
    r = get_room_from_code(room_id)
    if r is None:
        raise HTTPException(status_code=404)

    start_sent = r.state.start_sent_at
    if start_sent is None or len(r.state.hit_80_at):
        # for now we don't handle if we hit 80
        raise HTTPException(status_code=400)

    # r.register_completion
    # WIP :) do this later


@app.get("/checkoq")
async def check_oq(request: Request) -> OQInfo:
    from db import sql
    from rooms import get_config_from_line, get_draft_from_line, get_state_from_line
    user = get_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=500, detail="you don't exist")

    # wip lol
    maxoq = 7
    theiroq = 0

    with sql as cur:
        maxoq += len(cur.execute("SELECT * FROM oqboons WHERE uuid = ? AND oq = 'oq1'", (user.uuid,)).fetchall())

        res = cur.execute("SELECT * FROM rooms WHERE instr(draft,?) > 0", (user.uuid,)).fetchall()

        for r in res:
            rc = get_config_from_line(r)
            if rc is None or not rc.open_qualifier_submission:
                LOG("OQ Check failed: Room config")
                continue
            dr = get_draft_from_line(r)
            if dr is None or user.uuid not in dr.players:
                LOG("OQ Check failed: Draft")
                continue
            rs = get_state_from_line(r)
            if rs is None or not rs.has_sent_start:
                LOG("OQ Check failed: No start")
                continue
            # otherwise for now let's just increment
            theiroq += 1


    return OQInfo(oq_attempts=theiroq, max_oq_attempts=maxoq, finished_oq=theiroq >= maxoq)


@app.get("/user")
async def get_user(request: Request, response: Response) -> LoggedInUser | APIError:
    user = get_user_from_request(request)
    if user is None:
        return api_error(APIError(error_message="Could not find user"), response)

    # Fix frontend issue where we get an error because we try to join the room in /user
    # but the room does not exist in the backend. TODO - Maybe get_user_from_request
    # should check for this itself so we don't have to check in other locations.
    if user.room_code is not None and rooms.get_room_from_code(user.room_code) is None:
        # Handle room timeout / deletion
        LOG("/user : room was deleted, removing it from the user")
        user.room_code = None
        # Update this in the DB as well.
        with db.sql as cur:
            cur.execute(
                f"UPDATE users SET room_code = NULL WHERE uuid IN (?)", (user.uuid,)
            )

    return user


@app.websocket("/listen")
async def websocket_endpoint(*, websocket: WebSocket, token: str):
    from handlers import handle_websocket_message

    LOG("Got a connect / listen call with a websocket")
    user = token_to_user(token)
    full_user = db.populated_user(user)
    room = full_user.get_room()
    if room is None:
        LOG(f"Note: User {user.username} is listening to websocket before joining a room.")
        # return  # User must be in a room to be listening for updates.
    # Sane maximum
    if full_user.state.connections >= 10:
        raise RuntimeError(f"Max connections exceeded for user {user.username}")
    # Do not increase connections until accept() succeeds
    await websocket.accept()
    full_user.state.connections += 1
    mg.subscribe(websocket, full_user)
    if room is not None:
        await mg.send_join(websocket, room)
    try:
        while True:
            data = await websocket.receive_text()
            LOG('Got websocket data:', data)
            if data.startswith("##"):
                await handle_client_metadata(data, full_user, websocket)
                continue
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
    @app.post("/dev/becomeuser")
    async def become_user(request: Request, response: Response, username: str | None = None):
        from utils import ratelimited_username_to_uuid, associate_username
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
        if username is not None:
            maybe_uuid = await ratelimited_username_to_uuid(username)
            if maybe_uuid is None:
                return AuthenticationFailure(message=f"{username} is not a valid username")
            uuid = maybe_uuid
        else:
            UUIDS = set(PAIRS.keys())
            uuid: str = choice(list(UUIDS))
            username = PAIRS[uuid]

        if not make_fake_user(uuid=uuid, username=username):
            LOG(f"Note: Did not make user {username}, simply returned new token")

        payload = {
            "username": username,
            "uuid": uuid,
            "serverID": "draafttestserver",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60 * 60 * 24,  # 24 hours expiry
        }
        
        associate_username(uuid=uuid, username=username)

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        # add user to db if not exists
        return AuthenticationSuccess(token=token)

    @app.post("/dev/adduser")
    async def add_user(request: Request, response: Response):
        from utils import associate_username
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
        associate_username(uuid=to_add, username=PAIRS[to_add])
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
        await mg.broadcast_room(
            room, PlayerUpdate(uuid=user.uuid, action=PlayerActionEnum.kick)
        )
        # do nothing on backend. just broadcast the info...
        # rooms.remove_room_member(member)
