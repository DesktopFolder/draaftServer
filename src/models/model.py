from pydantic import BaseModel


class LoggedInUser(BaseModel):
    username: str
    uuid: str
    room_code: str | None = None


class MojangInfo(BaseModel):
    serverID: str
    username: str
