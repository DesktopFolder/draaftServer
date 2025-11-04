from fastapi import HTTPException
from db import PopulatedUser, get_populated_user_from_request, populated_user
from draft import Draft
from models.room import Room
from utils import get_user_from_request


def always_get_populated_user_from_request(request) -> PopulatedUser:
    u = get_user_from_request(request)
    if u is None:
        raise HTTPException(status_code=404, detail="Could not get user from request.")
    return populated_user(u)


def always_get_drafting_player(request) -> tuple[PopulatedUser, Room, Draft]:
    # Gets a user, room, and draft IFF the user is a player in the draft
    u = always_get_populated_user_from_request(request)
    r = u.get_room()
    if r is None:
        raise HTTPException(status_code=404, detail="Could not get room for user.")
    if r.draft is None:
        raise HTTPException(status_code=404, detail=f"Could not get draft for room {r.code}")
    if u.uuid not in r.draft.players:
        raise HTTPException(status_code=403, detail=f"{u.uuid} is not a player for room {r.code}")
    return (u, r, r.draft)
