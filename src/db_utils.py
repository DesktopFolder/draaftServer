from fastapi import HTTPException
from db import PopulatedUser, get_populated_user_from_request, populated_user
from draft import Draft
from models.room import Room, RoomState
from utils import get_user_from_request


def always_get_populated_user_from_request(request) -> PopulatedUser:
    u = get_user_from_request(request)
    if u is None:
        raise HTTPException(status_code=404, detail="Could not get user from request.")
    return populated_user(u)


def always_get_drafting_player(request) -> tuple[PopulatedUser, Room, Draft]:
    # Gets a user, room, and draft IFF the user is a player in the draft
    # okay, technically does not check if the draft is complete
    u = always_get_populated_user_from_request(request)
    r = u.get_room()
    if r is None:
        raise HTTPException(status_code=404, detail="Could not get room for user.")
    if r.draft is None:
        raise HTTPException(status_code=404, detail=f"Could not get draft for room {r.code}")
    if u.uuid not in r.draft.players:
        raise HTTPException(status_code=403, detail=f"{u.uuid} is not a player for room {r.code}")
    return (u, r, r.draft)

def always_get_drafting_user(request) -> tuple[PopulatedUser, Room, Draft]:
    # Gets a user, room, and draft IFF the user is a player in the draft
    # okay, technically does not check if the draft is complete
    u = always_get_populated_user_from_request(request)
    r = u.get_room()
    if r is None:
        raise HTTPException(status_code=404, detail="Could not get room for user.")
    if r.draft is None:
        raise HTTPException(status_code=404, detail=f"Could not get draft for room {r.code}")
    return (u, r, r.draft)

def always_get_gaming_player(request) -> tuple[PopulatedUser, Room, Draft, RoomState]:
    u, r, d = always_get_drafting_player(request)
    if not d.complete:
        raise HTTPException(status_code=403, detail="Room has not started yet. You may not advance. No advancing!!")
    return (u, r, d, r.state)

def into_gaming_player(p: PopulatedUser) -> None | tuple[Room, Draft]:
    r = p.get_room()
    if r is None:
        return None
    if r.draft is None:
        return None
    if p.uuid not in r.draft.players:
        return None
    if not r.draft.complete:
        return None
    return (r, r.draft)
