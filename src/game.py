from fastapi import APIRouter, Request

#another unused file :)

rt = APIRouter(prefix="/game")

@rt.post("/advance")
def add_advancement(request: Request, advancement: str):
    from db_utils import always_get_gaming_player
    u, r, d, s = always_get_gaming_player(request)
    uuid = u.uuid

    if uuid not in s.player_advancements:
        s.player_advancements[uuid] = set()

    print(advancement)

    #if s.player_advancements[uuid]
    #adv = s.player_advancements[u.uuid]
