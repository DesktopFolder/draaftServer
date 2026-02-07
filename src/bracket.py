from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi import APIRouter, Request, Response

rt = APIRouter(prefix="/bracket")

# Hacking things together for now.
class Participant(BaseModel):
    id: int
    tournament_id: int
    name: str

PL: dict[str, int] = dict()
def auto_participants(p: list[str]):
    tid = 0
    pid = 0
    l: list[Participant] = []
    for pa in p:
        l.append(Participant(id=pid, tournament_id=tid, name=pa))
        PL[l[-1].name] = l[-1].id
        pid += 1
    return l

DRAAFT2_PARTICIPANTS = auto_participants(["Snakezy", "Coosh", "Feinberg", "CroPro", "DoyPingu", "dolphinman", "SuperC", "dbowzer", "Oxidiot"])

class StageSettings(BaseModel):
    size: int

class Stage(BaseModel):
    id: int
    tournament_id: int
    name: str
    type: str = "single_elimination"
    settings: StageSettings

    @staticmethod
    def of_basic(name: str, settings: StageSettings):
        return Stage(id=0, tournament_id=0, name=name, settings=settings)

class ParticipantResult(BaseModel):
    # forfeit: bool | Literal['_undefined'] # -> undefined
    id: int | None # -> None

class Match(BaseModel):
    child_count: int
    group_id: int
    id: int

    opponent1: ParticipantResult | None
    opponent2: ParticipantResult | None

    number: int
    stage_id: int = 0
    round_id: int
    status: int = 2

def as_pid(pname: str | None):
    if pname is None:
        return None
    return PL[pname]

def setup_log():
    from os.path import isfile
    import json
    if not isfile(".bracket-log.json"):
        with open(".bracket-log.json", "w") as file:
            json.dump({
                "players": ["Snakezy", None, None, None, None, None, None, None]
            }, file)

setup_log()

def create_matches():
    mtr = {"match_id": 0, "number": 1, "round": 0, "cap": 4}
    def auto_match(p1: str | None, p2: str | None, miter: dict) -> tuple[Match, dict]:
        match = Match(child_count=0, group_id=0, id=miter["match_id"],
                             opponent1=ParticipantResult(id=as_pid(p1)),
                             opponent2=ParticipantResult(id=as_pid(p2)),
                             number=miter["number"], stage_id=0, round_id=miter["round"])

        num = miter["number"] + 1
        cap = miter["cap"]
        rnd = miter["round"]
        if num > miter["cap"]:
            num = 1
            cap = int(cap / 2)
            rnd += 1

        return (match, {"match_id": miter["match_id"] + 1, "number": num, "round": rnd, "cap": cap})

    m1, mtr = auto_match("Snakezy", "Coosh", mtr)
    m2, mtr = auto_match("dolphinman", "Feinberg", mtr)
    m3, mtr = auto_match("CroPro", "SuperC", mtr)
    m4, mtr = auto_match("dbowzer", "DoyPingu", mtr)

    with open(".bracket-log.json", "r") as file:
        import json
        p: list[str | None] = json.load(file)["players"]

    s1, mtr = auto_match(p.pop(0), p.pop(0), mtr)
    s2, mtr = auto_match(p.pop(0), p.pop(0), mtr)
    f, mtr = auto_match(p.pop(0), p.pop(0), mtr)

    return [m1, m2, m3, m4, s1, s2, f]


@rt.post("/admin/update_bracket")
async def register_completion_manually(request: Request):
    from models.room import ADMINS
    from utils import get_user_from_request
    user = get_user_from_request(request)
    if user is None:
        return
    if user.uuid not in ADMINS:
        return

    global BRACKET_RESP
    BRACKET_RESP = d2_bracket_serialized()


class MatchGame(BaseModel):
    pass

class Bracket(BaseModel):
    stages: list[Stage]
    matches: list[Match]
    matchGames: list[MatchGame]
    participants: list[Participant]

def generate_draaft_bracket():
    stage = Stage.of_basic("drAAft 2 Main Bracket", StageSettings(size=8))
    matches = create_matches()
    match_games = []
    participants = DRAAFT2_PARTICIPANTS
    return Bracket(stages=[stage], matches=matches, matchGames=match_games, participants=participants)

def d2_bracket_serialized():
    from models.ws import serialize
    return serialize(generate_draaft_bracket())

BRACKET_RESP = d2_bracket_serialized()

@rt.get("/external/current")
async def get_current_bracket():
    return Response(
        BRACKET_RESP,
        media_type=JSONResponse.media_type
    )
