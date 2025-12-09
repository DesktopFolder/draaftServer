from collections import defaultdict
from random import choice
import re
from typing import Generator

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

def load(s: str, tag: str):
    res = s.split(' ', 1)
    seed = int(res[0])

    if seed == 3583022600183591551:
        print(res)
        raise RuntimeError

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

def load_seedlist(file, tag: str, ignore=False):
    from random import shuffle
    if not ignore:
        sl = [load(s, tag) for s in file if len(s) > 2 and not s.startswith('#')]
        shuffle(sl)
        return sl
    else:
        for s in file:
            if len(s) > 2 and not s.startswith('#'):
                load(s, tag)
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

def get_overworld():
    return str(choice(OVERWORLD_SEEDS))
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
