from pydantic import BaseModel

# This could probably be moved into a user model later


class LoggedInUser(BaseModel):
    username: str
    uuid: str
    room_code: str | None = None
    status: str
    pronouns: str | None = None


class UserSettings(BaseModel):
    pronouns: str | None = None
    twitch_username: str | None = None

# This could be moved into a mojang model later so we don't need a generic models file
class MojangInfo(BaseModel):
    serverID: str
    username: str

class OQInfo(BaseModel):
    oq_attempts: int
    max_oq_attempts: int
    finished_oq: bool
