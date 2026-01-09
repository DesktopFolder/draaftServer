from collections import defaultdict
from random import choice
import re
from typing import Generator
from os.path import expanduser

_settings = """
{
    "room": "%ROOMCODE%",
    "worldId": "%WORLDID%",
    "worldGenSettings": {
      "bonus_chest": false,
      "dimensions": {
        "minecraft:overworld": {
          "type": "minecraft:overworld",
          "generator": {
            "biome_source": {
              "seed": %OVERWORLD%,
              "large_biomes": false,
              "type": "minecraft:vanilla_layered"
            },
            "seed": %OVERWORLD%,
            "settings": "minecraft:overworld",
            "type": "minecraft:noise"
          }
        },
        "minecraft:the_nether": {
          "type": "minecraft:the_nether",
          "generator": {
            "biome_source": {
              "seed": %NETHER%,
              "preset": "minecraft:nether",
              "type": "minecraft:multi_noise"
            },
            "seed": %NETHER%,
            "settings": "minecraft:nether",
            "type": "minecraft:noise"
          }
        },
        "minecraft:the_end": {
          "type": "minecraft:the_end",
          "generator": {
            "biome_source": {
              "seed": %END%,
              "type": "minecraft:the_end"
            },
            "seed": %END%,
            "settings": "minecraft:end",
            "type": "minecraft:noise"
          }
        }
      },
      "seed": %OVERWORLD%,
      "generate_features": true
    }
}
"""
class SeedAnnotation:
    __slots__ = (
        "strongholds",
        "bastion",
        "fortress",
        "mushroom_island",
        "jungle",
        "mega_taiga",
        "snowy",
        "badlands", # mesa! :)
    )
    def __init__(self) -> None:
        self.strongholds: list[str] = list()
        self.bastion: str | None = None
        self.fortress: str | None = None
        self.mushroom_island: str | None = None
        self.jungle: str | None = None
        self.mega_taiga: str | None = None
        self.snowy: str | None = None
        self.badlands: str | None = None

    def as_dict(self) -> dict:
        return {
            "strongholds": self.strongholds,
            "bastion": self.bastion,
            "fortress": self.fortress,
            "mushroom_island": self.mushroom_island,
            "jungle": self.jungle,
            "mega_taiga": self.mega_taiga,
            "snowy": self.snowy,
            "badlands": self.badlands,
        }

    def merge_overworld(self, d: dict):
        us = self.as_dict()
        for k in ['strongholds', 'mushroom_island', 'jungle', 'mega_taiga', 'snowy', 'badlands']:
            d['annotations'][k] = us[k]

    def merge_nether(self, d: dict):
        us = self.as_dict()
        for k in ['bastion', 'fortress']:
            d['annotations'][k] = us[k]

        

SEED_ANNOTATIONS: defaultdict[int, SeedAnnotation] = defaultdict(lambda: SeedAnnotation())

MATCH_POS = re.compile(r'\{[^}]+\}')
MATCH_NUM = re.compile(r'[-0-9]+')
def parse_annotations(s: str) -> Generator[tuple[str, str], None, None]:
    import re
    s = s.strip()
    for match in re.findall(MATCH_POS, s):
        coords = re.findall(MATCH_NUM, match)
        yield (coords[0], coords[2])


def basic_annotation(xz: tuple[str, str] | tuple[int, int]):
    return f'x: {xz[0]}, z: {xz[1]}'

def stronghold_ano(xz: tuple[str, str]):
    x, z = [int(c) * 2 for c in xz]
    return basic_annotation((x, z))

def chunk_annotation(xz: tuple[str, str]):
    x, z = [int(c) * 16 for c in xz]
    return basic_annotation((x, z))

def load(s: str, tag: str, minimum: int = 0):
    res = s.split(' ', 1)
    seed = int(res[0])

    if seed == 3583022600183591551:
        print(res)
        raise RuntimeError

    if seed < minimum:
        return None

    annotations = res[1:] 
    # we need to add some annotations haha
    if annotations:
        an = list(parse_annotations(annotations[0]))
        ano = SEED_ANNOTATIONS[seed]
        if tag == 'overworld':
            # biome annotations - NOT CHUNK COORDS, Block Positions!!!
            ano.mushroom_island, ano.jungle, ano.mega_taiga, ano.snowy, ano.badlands = [basic_annotation(a) for a in an]
        elif tag == 'stronghold':
            # CHUNK COORDS, BUT GIVE THEM NETHER COORDS
            ano.strongholds = [stronghold_ano(a) for a in an]
        elif tag == 'nether':
            # CHUNK COORDS, BUT GIVE THEM BLOCK POS LOL
            ano.bastion, ano.fortress = [chunk_annotation(a) for a in an]
        else:
            raise RuntimeError(f"Bad tag encountered: {tag}")

    return seed

MAX_KNOWN_OW = 0
def load_seedlist(file, tag: str, ignore=False, minimum: bool = False) -> list[int]:
    global MAX_KNOWN_OW
    from random import shuffle
    if not ignore:
        sl = [load(s, tag, minimum = MAX_KNOWN_OW) for s in file if len(s) > 2 and not s.startswith('#')]
        sl = [s for s in sl if s is not None]
        if sl:
            MAX_KNOWN_OW = sl[-1]
        shuffle(sl)
        return sl
    else:
        for s in file:
            if len(s) > 2 and not s.startswith('#'):
                load(s, tag, minimum=MAX_KNOWN_OW)
        return []

with open('.seeds/overworld_seeds.txt') as file:
    OVERWORLD_SEEDS: list[int] = load_seedlist(file, 'overworld')
with open('.seeds/overworld_seeds_stronghold_annotations.txt') as file:
    # We just want to load the annotations
    load_seedlist(file, 'stronghold', True)
with open('.seeds/nether_seeds.txt') as file:
    NETHER_SEEDS: list[int] = load_seedlist(file, 'nether')
with open('.seeds/end_seeds.txt') as file:
    END_SEEDS: list[int] = load_seedlist(file, 'end')

def load_unknown_overworld_seeds() -> set[int]:
    from os.path import isfile
    sh_ano = expanduser("~/data/draaft/overworld_seeds_strongholds.txt")
    norm = expanduser("~/data/draaft/overworld_seeds.txt")
    if not isfile(sh_ano) or not isfile(norm):
        print("Warning: Not loading high quality seed lists (not found).")
        return set()
    seeds, anos = load_seedlist(norm, "overworld", minimum=True), load_seedlist(sh_ano, "stronghold", True, minimum=True)
    return set(seeds)

GENERATED_OW_LIST = expanduser("~/data/draaft/generated_overworld_seeds.txt")
def load_generated_overworld_seeds() -> set[int]:
    from os.path import isfile
    if not isfile(GENERATED_OW_LIST):
        print("Warning: Not loading list of previously generated ow seeds (not found).")
        return set()
    return set([int(x.strip()) for x in open(GENERATED_OW_LIST).readlines() if not x.startswith("#")])

# actually, just any seed lol
UNUSED_OW_SEEDS = load_unknown_overworld_seeds()
GENERATED_OW_SEEDS = load_generated_overworld_seeds()

# returns True for high quality seed, False for low quality seed
def get_overworld(request_quality=False, allow_retry=True) -> tuple[str, bool]:
    # Overworld seeds are much harder to filter for.
    # So our 'good overworld seeds list' is much shorter.
    valid_ow = UNUSED_OW_SEEDS - GENERATED_OW_SEEDS

    if allow_retry and (not valid_ow or (not request_quality and len(valid_ow) < 100)):
        # try this 1 more time after reloading unused seeds
        UNUSED_OW_SEEDS.update(load_unknown_overworld_seeds())
        return get_overworld(request_quality=request_quality, allow_retry=False)

    if not valid_ow:
        # sucks to suck. return old seed. sad! :/
        return str(choice(OVERWORLD_SEEDS)), False

    if not request_quality and (len(valid_ow) < 100):
        # you snooze you lose. oh well :/
        return str(choice(OVERWORLD_SEEDS)), False

    # otherwise you get a high quality seed. isn't that slick?
    your_epic_seed = str(min(valid_ow))

    with open(GENERATED_OW_LIST, 'a') as file:
        file.write(your_epic_seed)
        file.write("\n")
    
    return your_epic_seed, True

def get_nether():
    return str(choice(NETHER_SEEDS))
def get_end():
    return str(choice(END_SEEDS))

def make_settings(overworld: str, nether: str, end: str, room: str, worldtype: str) -> str:
    ### TODO - THIS SHOULD REALLY BE CACHED
    from hashlib import sha256, md5
    s_overworld = overworld
    s_nether = nether
    s_end = end

    combined = sha256()
    combined.update(md5(overworld.encode()).digest())
    combined.update(md5(worldtype.encode()).digest())


    return (_settings.replace("%OVERWORLD%", s_overworld).replace("%NETHER%", s_nether).replace("%END%", s_end)
            .replace("%WORLDID%", combined.hexdigest()[0:32]).replace("%ROOMCODE%", room))
