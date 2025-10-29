from pydantic import BaseModel

# This could probably be moved into a user model later


class LoggedInUser(BaseModel):
    username: str
    uuid: str
    room_code: str | None = None
    status: str


# This could be moved into a mojang model later so we don't need a generic models file
class MojangInfo(BaseModel):
    serverID: str
    username: str
