from random import choice

_settings = """
{
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
"""

def load_seedlist(file):
    from random import shuffle
    sl = [int(s) for s in file if len(s) > 2 and not s.startswith('#')]
    shuffle(sl)
    return sl

with open('.seeds/overworld_seeds.txt') as file:
    OVERWORLD_SEEDS: list[int] = load_seedlist(file)
with open('.seeds/nether_seeds.txt') as file:
    NETHER_SEEDS: list[int] = load_seedlist(file)
with open('.seeds/end_seeds.txt') as file:
    END_SEEDS: list[int] = load_seedlist(file)

def get_overworld():
    return str(choice(OVERWORLD_SEEDS))
def get_nether():
    return str(choice(NETHER_SEEDS))
def get_end():
    return str(choice(END_SEEDS))

def make_settings(overworld: str, nether: str, end: str) -> str:
    s_overworld = overworld
    s_nether = nether
    s_end = end
    return _settings.replace("%OVERWORLD%", s_overworld).replace("%NETHER%", s_nether).replace("%END%", s_end)
