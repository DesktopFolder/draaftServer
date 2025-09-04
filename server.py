import json
import random
import re
import string
import time

import aiohttp
import jwt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# Change this to a secure value in production
JWT_SECRET = "your-very-secret-key"
JWT_ALGORITHM = "HS256"

# https://pyjwt.readthedocs.io/en/stable/
# https://sessionserver.mojang.com/session/minecraft/hasJoined?username=DesktopFolder&serverId=draaft2025server


def valid_username(un: str):
    return re.match(r"^[\w\d_]{2,17}$", un) is not None


def valid_serverid(sid: str):
    # Valid drAAft server ID:
    # 24 characters of base32 -> "draaaaft"
    return re.match(r"^[\w\d]{24}draaaaft$", sid) is not None


def getSessionCheckURI(username: str, serverId: str) -> str | None:
    if valid_serverid(serverId) and valid_username(username):
        print(f'Valid login from {username}')
        return f"https://sessionserver.mojang.com/session/minecraft/hasJoined?username={username}&serverId={serverId}"
    return None


app = FastAPI()


class LoggedInUser(BaseModel):
    username: str
    uuid: str
    serverID: str
    room: str | None = None


database: dict[str, LoggedInUser] = {}


class MojangInfo(BaseModel):
    serverID: str
    username: str


class AuthenticationSuccess(BaseModel):
    token: str


class AuthenticationFailure(BaseModel):
    message: str


AuthenticationResult = AuthenticationSuccess | AuthenticationFailure

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_valid(request: Request, call_next):
    if request.url.path != '/authenticate' and request.method != 'OPTIONS':
        token = request.headers.get("token")
        if not token:
            return PlainTextResponse("bad request, sorry mate", status_code=403)
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            # Optionally, check if user exists in database
            if token not in database:
                # Optionally, auto-add user from payload if not present
                user = LoggedInUser(
                    username=payload["username"], uuid=payload["uuid"], serverID=payload["serverID"])
                database[token] = user
        except jwt.ExpiredSignatureError:
            return PlainTextResponse("token expired", status_code=403)
        except jwt.InvalidTokenError:
            return PlainTextResponse("invalid token", status_code=403)
    return await call_next(request)


@app.post("/authenticate")
async def authenticate(mi: MojangInfo) -> AuthenticationResult:
    uri = getSessionCheckURI(mi.username, mi.serverID)
    if uri is None:
        return AuthenticationFailure(message="Your data sucks, try harder")
    async with aiohttp.ClientSession() as session:
        async with session.get(uri) as resp:
            if resp.status != 200:
                return AuthenticationFailure(message=f"Your response error code sucks ({resp.status}), try harder")
            respdata = await resp.json()
    if 'id' not in respdata or 'name' not in respdata:
        return AuthenticationFailure(message=f"your JSON sucks ({json.dumps(respdata)}), try harder")

    user = LoggedInUser(
        username=respdata['name'], uuid=respdata['id'], serverID=mi.serverID)
    # JWT payload
    payload = {
        "username": user.username,
        "uuid": user.uuid,
        "serverID": user.serverID,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60 * 60 * 24  # 24 hours expiry
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    print(f"Issued token for {user.username}: {token}")
    database[token] = user
    return AuthenticationSuccess(token=token)


class Room(BaseModel):
    code: str
    members: list[str]


rooms = {

}


@app.get("/authenticated")
async def authenticated():
    return True


def room_code():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(7))


@app.get("/room/create")
async def create_room():
    return room_code()
