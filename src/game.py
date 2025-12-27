from typing import Any
from models.completion import Completion
from models.room import Room
from utils import LOG
import datetime

FORMAT = "%d-%m-%Y %H:%M:%S"
def as_key(start: str, end: str):
    from zoneinfo import ZoneInfo
    s = datetime.datetime.strptime(start, FORMAT).replace(tzinfo=ZoneInfo("America/New_York"))
    e = datetime.datetime.strptime(end, FORMAT).replace(tzinfo=ZoneInfo("America/New_York"))
    return (s.timestamp(), e.timestamp())

OQ_TAGS = {
    # Okay, so this code is a bit suspicious, but I'm pretty sure it's correct.
    # The timestamps we get are from time.time(), which is NOT localized, but... you can't localize
    # time.time(), it's just a timestamp, it's UTC already.
    # Here, we're getting timestamps OUT OF date strings, which do require localization to contextualize.
    # But, they're still ultimately utc timestamps at the end, so they compare with the time.time()s.
    as_key("26-12-2025 23:59:59", "12-01-2026 00:00:00"): "oq1"
}

def to_oq_submission_tag(r: Room):
    from draft import POOLS, POOL_MAPPING, DraftPool
    from collections import defaultdict
    # Keep the logic split out for these.
    # Do generic requirements for OQ submissions first.
    # Because of how shared picks work, we're going to require 1 player.
    FAIL = lambda reason: LOG(f"Failed {r.code} OQ submission tag: {reason}.")

    if r.draft is None:
        return FAIL("no draft.")
    if len(r.draft.players) != 1:
        return FAIL("wrong player count.")
    # Elapsed time check is already done by register_completion
    # We need to check that the picks are valid.
    # We also need to check that the start time is valid.
    # Start time is at the end because we will return out of a for loop.
    # Check picks here, now, etc.
    
    picks = defaultdict(lambda: 0)
    for d in r.draft.draft:
        p = POOL_MAPPING[d.key]
        n = p.name.full_name
        picks[n] += 1
        if picks[n] > p.oq_pick_count():
            return FAIL(f"too many picks in pool {n} ({picks[n]})")

    game_start = r.state.start_sent_at
    if game_start is None:
        return FAIL("game start is none")

    for ((start, end), tag) in OQ_TAGS.items():
        if game_start >= start and game_start <= end:
            return tag

    return FAIL(f"game start {game_start} was not a valid start time")


def to_tag(r: Room):
    if r.config.open_qualifier_submission:
        # Tag requested: OQ submission
        return to_oq_submission_tag(r)
    return None

COMPLETIONS: list[Completion] = list()

def insert_test_completions():
    from draft import Draft
    import time
    import random
    import sys
    if 'dev' not in sys.argv:
        raise RuntimeError("Cannot insert test completions when not in development mode!!")
    r = Room.make_fake()
    r.draft = Draft.from_players(r.members)
    cur_time = time.time() + (7 * 60 * 60)
    r.state.start_sent_at = cur_time - (40 * 60) - random.randrange(10, 60 * 40)
    r.state.hit_80_at[r.admin] = cur_time
    r.config.open_qualifier_submission = True
    # Let's just insert one for now.
    register_completion(r, uuid=r.admin)

def autoload_completions():
    from db import sql
    from models.completion import Completion
    from lb import regen_oq1_cache
    """
    uuid char(32) NOT NULL,
    username char(20) NOT NULL,
    room char(7) NOT NULL,
    start float NOT NULL,
    end float NOT NULL
    tag char(32)
    """
    with sql as cur:
        res = cur.execute("SELECT uuid,username,room,start,end,tag FROM completions", ()).fetchall()
    for x in res:
        c = Completion.from_tuple(x)
        COMPLETIONS.append(c)
        if c.tag is not None:
            update_tagged_cache(c, c.tag, regen=False)
    
    regen_oq1_cache()


def update_tagged_cache(c: Any, tag: str, regen: bool = True):
    from models.completion import Completion
    assert isinstance(c, Completion)

    if tag == 'oq1':
        from lb import update_oq1_cache
        update_oq1_cache(c, regen=regen)


def register_completion(r: Room, uuid: str):
    from models.completion import Completion
    from utils import to_username
    username = to_username(uuid)
    if username is None:
        LOG(f"Could not register completion for uuid {uuid} from room {r.code} - no username found for user.")
        return
    start = r.state.start_sent_at
    if start is None:
        LOG(f"Could not register completion for uuid {uuid} from room {r.code} - no start sent.")
        return
    end = r.state.hit_80_at.get(uuid)
    if end is None:
        LOG(f"Could not register completion for uuid {uuid} from room {r.code} - no end time found.")
        return

    minutes = (end - start) / 60
    if minutes < 0:
        LOG(f"Could not register completion for uuid {uuid} from room {r.code} - bad time elapsed.")
        return
    if minutes < 40:
        LOG(f"Did not register completion for uuid {uuid} from room {r.code} - minutes elapsed {minutes} is too small.")
        return

    tag = to_tag(r)

    c = Completion(uuid=uuid, username=username, room=r.code, start=start, end=end, tag=tag)
    if c.insert_into_db():
        COMPLETIONS.append(c)
        if tag is not None:
            update_tagged_cache(c, tag)
