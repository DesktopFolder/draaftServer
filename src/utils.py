import re
import aiohttp
import json
import sys

from models.generic import LoggedInUser

def nolog(*_, **__):
    pass


if "dev" in sys.argv:
    LOG = print
else:
    LOG = nolog


UUID_TO_USERNAME = dict()
USERNAME_TO_UUID = dict()
def associate_username(uuid: str, username: str):
    UUID_TO_USERNAME[uuid] = username
    USERNAME_TO_UUID[username.lower()] = uuid


def random_username():
    from random import choice
    starters = ["Pac", "Folder", "Menx", "Memerson", "Totorewa", "Feinberg", "Oxidiot", "CroPro", "Snakezy", "Ludwig"]
    enders = ["Fan", "Follower", "Hater", "73", "1972", "TheWinner", "Champ", "Yarr", "Coal", "MCSR", "MC", "Ranked"]
    return (choice(starters) + choice(enders))[0:16]

def associate_uuid_to_random_username(uuid: str):
    associate_username(uuid, random_username())

def to_username(uuid: str) -> str | None:
    return UUID_TO_USERNAME.get(uuid)

def to_uuid(username: str) -> str | None:
    return USERNAME_TO_UUID.get(username.lower())

def lookup_user(identifier: str) -> dict[str, str]:
    if identifier in UUID_TO_USERNAME:
        uuid = identifier
        username = UUID_TO_USERNAME[identifier]
    elif identifier.lower() in USERNAME_TO_UUID:
        username = identifier
        uuid = USERNAME_TO_UUID[identifier.lower()]
    else:
        return { "error": "not found" }
    return { "username": username, "uuid": uuid }

def cache_usernames():
    import json
    import shutil
    to_dump = {
        "USERNAME_TO_UUID": USERNAME_TO_UUID,
        "UUID_TO_USERNAME": UUID_TO_USERNAME,
    }
    with open(".tmp.cache", "w") as file:
        json.dump(to_dump, file)

    # Do an atomic move
    shutil.move(".tmp.cache", "usernames.json")

def load_usernames():
    global UUID_TO_USERNAME
    global USERNAME_TO_UUID
    import json
    try:
        with open("usernames.json") as file:
            data = json.load(file)
            UUID_TO_USERNAME = data["UUID_TO_USERNAME"]
            USERNAME_TO_UUID = data["USERNAME_TO_UUID"]
    except:
        pass
load_usernames()

class IndentLog:
    def __call__(self, *args, **kwargs):
        LOG(" ", *args, **kwargs)

async def validate_mojang_session(username: str, serverID: str):
    uri = getSessionCheckURI(username, serverID)
    if uri is None:
        return {"success": False, "error": "Your data sucks, try harder"}
    async with aiohttp.ClientSession() as session:
        async with session.get(uri) as resp:
            if resp.status != 200:
                return {"success": False, "error": f"Your response error code sucks ({resp.status}), try harder"}
            resp_data = await resp.json()
    if 'id' not in resp_data or 'name' not in resp_data:
        return {"success": False, "error": f"your JSON sucks ({json.dumps(resp_data)}), try harder"}
    return {"success": True, "data": resp_data}


async def ratelimited_username_to_uuid(username: str):
    if not valid_username(username):
        return None
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.mojang.com/users/profiles/minecraft/{username}") as resp:
            if resp.status != 200:
                return None
            resp_data = await resp.json()
    uuid = resp_data["id"]
    if not isinstance(uuid, str):
        return None
    return uuid



def get_user_from_request(request) -> LoggedInUser | None:
    token = request.state.valid_token
    if token is None or not hasattr(request.state, 'logged_in_user') or request.state.logged_in_user is None or not isinstance(request.state.logged_in_user, LoggedInUser):
        return None
    return request.state.logged_in_user


def valid_username(un: str):
    return re.match(r"^[\w\d_*]{2,18}$", un) is not None


def valid_server_id(sid: str):
    # Valid drAAft server ID:
    # 24 characters of base32 -> "draaaaft"
    return re.match(r"^[\w\d]{24}draaaaft$", sid) is not None


def getSessionCheckURI(username: str, serverId: str) -> str | None:
    if valid_server_id(serverId) and valid_username(username):
        print(f'Valid login from {username}')
        return f"https://sessionserver.mojang.com/session/minecraft/hasJoined?username={username}&serverId={serverId}"
    return None

def persistent_token(length: int, name: str):
    from os.path import isdir, isfile
    if not isdir('auth'):
        from os import mkdir
        mkdir('auth')

    loc = f'auth/{name}'
    if isfile(loc):
        return open(loc).read()

    import secrets
    res = secrets.token_urlsafe(length)
    open(loc, 'w').write(res)
    return res


def serialize_list(l: list) -> str:
    # TODO - should generically serialize any list
    # right now assumed list[BaseModel]
    from models.ws import serialize
    from json import loads, dumps
    # serialize object to string -> reload as dictionary -> place in list -> dump list
    return dumps([loads(serialize(o)) for o in l])
