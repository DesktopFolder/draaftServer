from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from models.completion import Completion

rt = APIRouter(prefix="/lb")

OQ1_CACHE = "[]"
OQ1_GAMES: list[Completion] = list()

def regen_oq1_cache():
    from utils import serialize_list
    global OQ1_CACHE
    OQ1_CACHE = serialize_list(OQ1_GAMES)


def update_oq1_cache(c: Completion, regen: bool = True):
    # IMPORTANT TODO: Only take first 5 completions per player!
    OQ1_GAMES.append(c)
    if regen:
        regen_oq1_cache()

@rt.get("/external/oq1")
async def get_external_oq1_leaderboard():
    return Response(
        OQ1_CACHE,
        media_type=JSONResponse.media_type
    )
