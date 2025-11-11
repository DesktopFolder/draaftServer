from collections import defaultdict
from enum import Enum
from typing import DefaultDict, Literal, Any, Callable
from typing_extensions import override
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Response

from utils import LOG

rt = APIRouter(prefix="/draft")


class AutoName(BaseModel):
    @staticmethod
    def make_simple(name: str) -> "AutoName":
        return AutoName(full_name=name, short_name=name, pretty_name=basic_prettify(name))

    full_name: str
    short_name: str
    pretty_name: str


class Draftable(BaseModel):
    # How other objects refer to this object
    key: str

    name: AutoName

    # Generally, the pop-up text for this object
    description: str

    # The image tied to this object
    image_uri: str
    advancement: str | None = None

    @staticmethod
    def basic(
        key: str,
        description: str,
        image: str | None = None,
        name: str | None = None,
        advancement: str | None = None,
    ) -> "Draftable":
        if image is None:
            image = f"{key}.png"
        if name is None:
            name = key
        return Draftable(
            key=key,
            name=AutoName.make_simple(name),
            description=description,
            image_uri=image,
            advancement=advancement,
        )


class PoolTypeEnum(str, Enum):
    icons = "icons"
    auto_names = "auto_names"


class DraftPool(BaseModel):
    def __init__(self, /, **data: Any) -> None:
        super().__init__(**data)

        for k in self.contains:
            POOL_MAPPING[k] = self
    name: AutoName

    # Draftables (keys)
    contains: list[str]

    # Pool type
    kind: PoolTypeEnum

POOL_MAPPING: dict[str, DraftPool] = dict()


class Datapack:
    def __init__(self):
        pass

    def onload(self, user: str) -> str:
        return ""

    def ontick(self, user: str) -> str:
        return ""

    # no players for this for now
    def custom_file(self) -> dict[str, str]:
        return {}

    def description(self) -> str:
        return "error: bad description call"


class CustomGranter(Datapack):
    def __init__(self, onload: str | None = None, ontick: str | None = None):
        self.onload_ = onload
        self.ontick_ = ontick

    @override
    def onload(self, user: str) -> str:
        return (self.onload_ or "").format(USERNAME=user)

    @override
    def ontick(self, user: str) -> str:
        return (self.ontick_ or "").format(USERNAME=user)


class LambdaGranter(Datapack):
    def __init__(self, onload: Callable[[str], str] | None = None, ontick: Callable[[str], str] | None = None):
        self.onload_ = onload
        self.ontick_ = ontick

    @override
    def onload(self, user: str) -> str:
        if self.onload_ is not None:
            return self.onload_(user)
        return ""

    @override
    def ontick(self, user: str) -> str:
        if self.ontick_ is not None:
            return self.ontick_(user)
        return ""


class FileGranter(Datapack):
    def __init__(self, file_granter: dict[str, str]):
        self.file_granter = file_granter

    @override
    def custom_file(self) -> dict[str, str]:
        return self.file_granter


PRETTY_ADVANCEMENTS = {
    "adventure/adventuring_time": "Adventuring Time",
    "adventure/kill_all_mobs": "Monsters Hunted",
    "husbandry/bred_all_animals": "Two by Two",
    "story/cure_zombie_villager": "Zombie Doctor",
}


def basic_prettify(string: str, title: bool = True):
    res = ((string.split(":")[-1]).split("/")[-1]).replace("_", " ")
    if title:
        return res.title()
    return res
def prettify_advancement(advancement: str):
    if advancement in PRETTY_ADVANCEMENTS:
        return PRETTY_ADVANCEMENTS[advancement]
    return basic_prettify(advancement)


class AdvancementGranter(Datapack):
    def __init__(
        self,
        advancement: str,
        criteria: str | None = None,
        pretty: str | None = None,
        prefix="minecraft",
        specifier="only",
        player: str | None = None,
    ):
        self.advancement = advancement
        self.criteria = criteria
        self.pretty = (
            pretty if pretty is not None else prettify_advancement(advancement)
        )
        self.player = player
        self.prefix = prefix
        self.specifier = specifier

    @override
    def onload(self, user: str) -> str:
        return self.build(user)

    def build(self, user: str) -> str:
        user = self.player or user
        crit = "" if self.criteria is None else f" {self.prefix}:{self.criteria}"
        return f"advancement grant {user} {self.specifier} {self.prefix}:{self.advancement}{crit}"

    @override
    def description(self) -> str:
        if self.criteria is not None:
            return f"Grants {prettify_advancement(self.criteria)} from {self.pretty}"
        return f"Grants the advancement {self.pretty}"


class ItemGranter(Datapack):
    def __init__(self, item: str, count: int = 1, player: str | None = None, desc_name: str | None=None, no_multi: bool = False):
        self.player = player
        self.item = item
        self.desc_item = desc_name or item.split('{', 1)[0].replace('_', ' ')
        self.count = count
        self.no_multi = no_multi

    @override
    def onload(self, user: str) -> str:
        return f"give {self.player or user} {self.item} {self.count}"

    @override
    def description(self) -> str:
        if self.count == 1 or self.no_multi:
            return f"Gives {self.count} {self.desc_item}"
        return f"Gives {self.count} {self.desc_item}s"


class EnchantedItemGranter(Datapack):
    def __init__(self, item: str, enchants: list[tuple[str, int]]):
        self.item = item
        self.enchants = enchants
        """
give @a minecraft:diamond_sword{Enchantments:[{id:"minecraft:smite",lvl:5},{id:"minecraft:looting",lvl:3},{id:"minecraft:unbreaking",lvl:3}]}
        """
        ENCHANT_SPECS = ','.join([f"{{id:\"minecraft:{enchant}\",lvl:{lvl}}}" for (enchant, lvl) in enchants])
        ENCHANT_DESCS = ', '.join([f"{basic_prettify(enchant)} {lvl}" if lvl > 1 else basic_prettify(enchant) for (enchant, lvl) in enchants])
        self.spec = f"minecraft:{item}{{Enchantments:[{ENCHANT_SPECS}]}}"
        self.desc = f"Gives {basic_prettify(self.item, title=False)} enchanted with {ENCHANT_DESCS}"

    @override
    def onload(self, user: str) -> str:
        return f"give {user} {self.spec}"

    @override
    def description(self) -> str:
        return self.desc


class SimpleMultiCriteria(Datapack):
    def __init__(
        self,
        advancement: str,
        criteria: list[str],
        prefix="minecraft",
        specifier="only",
        player: str | None = None,
    ):
        self.criteria: list[AdvancementGranter] = list()
        for crit in criteria:
            self.criteria.append(
                AdvancementGranter(advancement, crit, None, prefix, specifier, player)
            )
        self.adv = prettify_advancement(advancement)

    @override
    def onload(self, user: str) -> str:
        return self.build(user)

    def build(self, user: str) -> str:
        return "\n".join([c.build(user) for c in self.criteria])

    def description(self) -> str:
        # this is just to placate, they're guaranteed valid :) never buggy!!!
        criteriaes = ", ".join(
            [prettify_advancement(c.criteria or "") for c in self.criteria]
        )
        return f"Grants {criteriaes} from {self.adv}"


DRAFTABLES: dict[str, Draftable] = {}
DATAPACK: dict[str, list[Datapack]] = dict()
_draftable_file = "draftables.json"


def _add_draftable(d: Draftable, datapack: None | list[Datapack] = None):
    DRAFTABLES[d.key] = d
    if datapack is not None:
        DATAPACK[d.key] = datapack


def _add_advancement(
    key: str,
    image: str,
    advs: list[str | tuple[str, list[str]]],
    advancement: str | None="challenge-incomplete.png",
):
    l: list[Datapack] = list()
    for adv in advs:
        if isinstance(adv, str):
            l.append(AdvancementGranter(advancement=adv))
        else:
            l.append(SimpleMultiCriteria(adv[0], adv[1]))
    desc = "\n".join([x.description() for x in l])
    _add_draftable(Draftable.basic(key, desc, image, advancement=advancement), l)

def _add_multi(
    key: str,
    image: str,
    gens: list[Datapack],
    description: str | None = None):
    if description is None:
        description = "\n".join([x.description() for x in gens])
    _add_draftable(Draftable.basic(key, description, image), gens)


# Armour
_add_multi("bucket", "bucket.png", [ItemGranter("bucket{Enchantments:[{}]}")], description="A fully-enchanted, max-tier bucket.")
_add_multi("helmet", "helmet.gif", [EnchantedItemGranter("diamond_helmet", [("protection", 5), ("unbreaking", 3), ("aqua_affinity", 1), ("respiration", 3)])])
_add_multi("chestplate", "chestplate.gif", [EnchantedItemGranter("diamond_chestplate", [("protection", 5), ("unbreaking", 3)])])
_add_multi("leggings", "leggings.gif", [EnchantedItemGranter("diamond_leggings", [("protection", 5), ("unbreaking", 3)])])
_add_multi("boots", "boots.gif", [EnchantedItemGranter("diamond_boots", [("protection", 5), ("unbreaking", 3), ("depth_strider", 3)])])

# Tools
_add_multi("sword", "sword.gif", [EnchantedItemGranter("diamond_sword", [("smite", 5), ("looting", 3), ("unbreaking", 3)])])
_add_multi("pickaxe", "pickaxe.gif", [EnchantedItemGranter("diamond_pickaxe", [("fortune", 3), ("efficiency", 4), ("unbreaking", 3)])])
_add_multi("axe", "axe.gif", [EnchantedItemGranter("diamond_axe", [("efficiency", 5), ("silk_touch", 1), ("unbreaking", 3)])])
_add_multi("shovel", "shovel.gif", [EnchantedItemGranter("diamond_shovel", [("efficiency", 5), ("fortune", 3), ("unbreaking", 3)])])
_add_multi("hoe", "netherite_hoe.gif", [EnchantedItemGranter("netherite_hoe", [("efficiency", 5), ("silk_touch", 1), ("unbreaking", 3)])])
_add_multi("trident", "trident.gif", [EnchantedItemGranter("trident", [("channeling", 1), ("loyalty", 3), ("unbreaking", 3)])])

# Biomes
_add_advancement(
    key="badlands",
    image="badlands.png",
    advs=[
        (
            "adventure/adventuring_time",
            ["badlands", "badlands_plateau", "wooded_badlands_plateau"],
        ),
        ("adventure/kill_all_mobs", ["cave_spider"]),
    ],
    advancement=None,
)

_add_advancement(
    key="jungle",
    image="bamboo_jungle.png",
    advs=[
        (
            "adventure/adventuring_time",
            [
                "bamboo_jungle",
                "bamboo_jungle_hills",
                "jungle_hills",
                "jungle_edge",
                "jungle",
            ],
        ),
        ("husbandry/bred_all_animals", ["minecraft:panda", "minecraft:ocelot"]),
        ("husbandry/balanced_diet", ["melon_slice", "cookie"]),
    ],
    advancement=None,
)

_add_advancement(
    key="snowy",
    image="snowy_taiga.png",
    advs=[
        (
            "adventure/adventuring_time",
            [
                "snowy_tundra",
                "snowy_taiga",
                "snowy_taiga_hills",
                "snowy_mountains",
                "snowy_beach",
                "frozen_river",
            ],
        ),
        ("adventure/kill_all_mobs", ["stray"]),
        "story/cure_zombie_villager",
    ],
    advancement=None,
)

_add_advancement(
    key="mega_taiga",
    image="giant_tree_taiga.png",
    advs=[
        ("adventure/adventuring_time", ["giant_tree_taiga", "giant_tree_taiga_hills"]),
        ("husbandry/balanced_diet", ["sweet_berries"]),
        ("husbandry/bred_all_animals", ["fox"]),
    ],
    advancement=None,
)

_add_advancement(
    key="mushroom_island",
    image="mushroom_field_shore.png",
    advs=[
        ("adventure/adventuring_time", ["mushroom_fields", "mushroom_field_shore"]),
        ("husbandry/bred_all_animals", ["mooshroom"]),
    ],
    advancement=None,
)

_add_advancement( key="complete_catalogue", image="raw_cod.png", advs=["husbandry/complete_catalogue"])
_add_advancement(key="adventuring_time", image="diamond_boots.png", advs=["adventure/adventuring_time"])
_add_advancement(key="two_by_two", image="golden_carrot.png", advs=["husbandry/bred_all_animals"])
_add_advancement(key="monsters_hunted", image="diamond_sword.png", advs=["adventure/kill_all_mobs"])
_add_advancement(key="a_balanced_diet", image="apple.png", advs=["husbandry/balanced_diet"])

_add_draftable(Draftable.basic(key="fireres", image="fire_resistance.png", description="Grants permanent Fire Resistance.", name="Fire Resistance"), datapack=[CustomGranter(ontick="effect give @{USERNAME} minecraft:fire_resistance 3600")])

_add_multi(key="leads", image="lead.png", gens=[ItemGranter("lead", 23), AdvancementGranter(advancement="adventure/kill_all_mobs", criteria="slime")])

_add_advancement(key="breeds", image="haybale.png", advs=[("husbandry/bred_all_animals", ["horse", "donkey", "mule", "llama", "wolf", "fox", "turtle"])], advancement=None)

_add_multi(key="hives", image="beenest.png", gens=[ItemGranter('bee_nest{BlockEntityTag:{Bees:[{MinOccupationTicks:600,TicksInHive:500,EntityData:{Brain:{memories:{}},HurtByTimestamp:0,HasStung:0b,Attributes:[],Invulnerable:0b,FallFlying:0b,ForcedAge:0,PortalCooldown:0,AbsorptionAmount:0.0f,FallDistance:0.0f,InLove:0,DeathTime:0s,HandDropChances:[0.085f,0.085f],CannotEnterHiveTicks:0,PersistenceRequired:0b,id:"minecraft:bee",Age:0,TicksSincePollination:0,AngerTime:0,Motion:[0.0d,0.0d,0.0d],Health:10.0f,HasNectar:0b,LeftHanded:0b,Air:300s,OnGround:0b,Rotation:[1.2499212f,0.0f],HandItems:[{},{}],ArmorDropChances:[0.085f,0.085f,0.085f,0.085f],Pos:[0.0d,0.0d,0.0d],Fire:-1s,ArmorItems:[{},{},{},{}],CropsGrownSincePollination:0,CanPickUpLoot:0b,HurtTime:0s}},{MinOccupationTicks:600,TicksInHive:500,EntityData:{Brain:{memories:{}},HurtByTimestamp:0,HasStung:0b,Attributes:[],Invulnerable:0b,FallFlying:0b,ForcedAge:0,PortalCooldown:0,AbsorptionAmount:0.0f,FallDistance:0.0f,InLove:0,DeathTime:0s,HandDropChances:[0.085f,0.085f],CannotEnterHiveTicks:0,PersistenceRequired:0b,id:"minecraft:bee",Age:0,TicksSincePollination:0,AngerTime:0,Motion:[0.0d,0.0d,0.0d],Health:10.0f,HasNectar:0b,LeftHanded:0b,Air:300s,OnGround:0b,Rotation:[1.2499212f,0.0f],HandItems:[{},{}],ArmorDropChances:[0.085f,0.085f,0.085f,0.085f],Pos:[0.0d,0.0d,0.0d],Fire:-1s,ArmorItems:[{},{},{},{}],CropsGrownSincePollination:0,CanPickUpLoot:0b,HurtTime:0s}},{MinOccupationTicks:600,TicksInHive:500,EntityData:{Brain:{memories:{}},HurtByTimestamp:0,HasStung:0b,Attributes:[],Invulnerable:0b,FallFlying:0b,ForcedAge:0,PortalCooldown:0,AbsorptionAmount:0.0f,FallDistance:0.0f,InLove:0,DeathTime:0s,HandDropChances:[0.085f,0.085f],CannotEnterHiveTicks:0,PersistenceRequired:0b,id:"minecraft:bee",Age:0,TicksSincePollination:0,AngerTime:0,Motion:[0.0d,0.0d,0.0d],Health:10.0f,HasNectar:0b,LeftHanded:0b,Air:300s,OnGround:0b,Rotation:[1.2499212f,0.0f],HandItems:[{},{}],ArmorDropChances:[0.085f,0.085f,0.085f,0.085f],Pos:[0.0d,0.0d,0.0d],Fire:-1s,ArmorItems:[{},{},{},{}],CropsGrownSincePollination:0,CanPickUpLoot:0b,HurtTime:0s}}]}}', 2, desc_name="filled bee nest")])

_add_multi(key="crossbow", image="crossbow.gif", gens=[EnchantedItemGranter("crossbow", [("piercing", 4)])])

def shulker_granter(user: str) -> str:
    import random
    colour = random.randint(0, 16)

    return f"execute at {user} run summon minecraft:boat ~ ~2 ~ {{Passengers:[{{id:shulker,Color:{colour}}}]}}"

_add_multi(key="transport", image="shulkerboat.png", gens=[LambdaGranter(onload=shulker_granter)], description="Spawns a boated shulker on world load.")

_add_multi(key="box", image="shulker_box.png", gens=[ItemGranter("shulker_box", 1)])
_add_multi(key="obsidian", image="obsidian.png", gens=[ItemGranter("obsidian", 10, no_multi=True)])
_add_multi(key="fireworks", image="firework_rocket.png", gens=[ItemGranter("gunpowder", 23, no_multi=True), ItemGranter("paper", 23, no_multi=True)])
_add_multi(key="logs", image="log.png", gens=[ItemGranter("acacia_log", 64)])
_add_multi(key="eyes", image="ender_eye.png", gens=[ItemGranter("ender_eye", 2, desc_name="eyes of ender", no_multi=True)])
_add_multi(key="rates", image="blaze_rod.png", gens=[FileGranter({"draaftpack/data/minecraft/loot_tables/entities/blaze.json": """
{
  "type": "minecraft:entity",
  "pools": [
    {
      "rolls": 1,
      "entries": [
        {
          "type": "minecraft:item",
          "functions": [
            {
              "function": "minecraft:set_count",
              "count": {
                "min": 1.0,
                "max": 1.0,
                "type": "minecraft:uniform"
              }
            },
            {
              "function": "minecraft:looting_enchant",
              "count": {
                "min": 0.0,
                "max": 1.0
              }
            }
          ],
          "name": "minecraft:blaze_rod"
        }
      ],
      "conditions": [
        {
          "condition": "minecraft:killed_by_player"
        }
      ]
    }
  ]
}
"""})], description="Blazes never drop 0 rods.")

# Configurable later, just get it working for now.
POOLS: list[DraftPool] = [
    DraftPool(name=AutoName.make_simple('Armour'), contains=["helmet", "chestplate", "leggings", "boots", "bucket"], kind=PoolTypeEnum.icons),
    DraftPool(name=AutoName.make_simple('Tools'), contains=["sword", "pickaxe", "axe", "shovel", "hoe", "trident"], kind=PoolTypeEnum.icons),
    DraftPool(name=AutoName.make_simple('Biomes'), contains=["badlands", "jungle", "mega_taiga", "mushroom_island", "snowy"], kind=PoolTypeEnum.icons),
    DraftPool(name=AutoName.make_simple('Misc'), contains=["leads", "fireres", "hives", "breeds", "crossbow", "transport"], kind=PoolTypeEnum.icons),
    DraftPool(name=AutoName.make_simple('Advancements'), contains=["complete_catalogue","adventuring_time","two_by_two","monsters_hunted","a_balanced_diet"], kind=PoolTypeEnum.icons),
    DraftPool(name=AutoName.make_simple('Early Game'), contains=["box", "obsidian", "fireworks", "logs", "eyes", "rates"], kind=PoolTypeEnum.icons),
]
 
class DraftPick(BaseModel):
    # Key of the draftable
    key: str
    # UUID of the player who drafted it (for now, I guess)
    player: str
    # Number of the pick
    index: int


class DraftPickUpdate(DraftPick):
    variant: Literal["draftpick"] = "draftpick"
    positions: list[str]
    next_positions: list[str]


class Draft(BaseModel):
    @staticmethod
    def from_players(players: set[str]) -> "Draft":
        import random

        p = list(players)
        random.shuffle(p)

        num_players = len(players)

        # allowed picks per player per pool
        picks_per = 2 if num_players <= 2 else 1
        # total number of picks before we're done
        max_picks = len(POOLS * picks_per * num_players)
        if num_players == 1:
            # idk
            picks_per = 9
            max_picks = sum([len(p.contains) for p in POOLS])

        return Draft(players=p, position=list(p), next_positions=list(reversed(p)), max_picks=max_picks, picks_per_pool=picks_per)

    def serialized(self) -> str:
        from models.ws import serialize

        res = serialize(self)
        if res is None:
            raise RuntimeError("Could not serialize draft object?!")
        return res

    players: list[str] = list()
    draft: list[DraftPick] = list()
    position: list[str] = list()  # Current set of draft picks
    next_positions: list[str] = list()  # next set of draft picks
    picked: set[str] = set()
    complete: bool = False

    # later? configure
    max_picks: int
    picks_per_pool: int


@rt.get("/status")
async def get_status(request: Request) -> Draft:
    from db import get_started_room

    LOG("Getting status of room...")
    ru = get_started_room(request)
    if ru is None:
        raise HTTPException(status_code=404, detail="no valid draft found")
    return ru[2]


@rt.get("/draftables")
async def get_draftables() -> tuple[list[DraftPool], dict[str, Draftable]]:
    return (POOLS, DRAFTABLES)


@rt.post("/pick")
async def do_pick(request: Request, key: str):
    from db_utils import always_get_drafting_player
    from room_manager import mg
    from rooms import update_draft

    user, room, draft = always_get_drafting_player(request)

    if user.uuid != draft.position[0]:
        raise HTTPException(status_code=403, detail="You cannot pick right now.")
    if key not in DRAFTABLES:
        raise HTTPException(
            status_code=404, detail=f"Draft pick {key} could not be found."
        )
    if key not in POOL_MAPPING:
        raise HTTPException(
            status_code=404, detail=f"Draft pick {key} is not in a pool!"
        )
    if key in draft.picked:
        raise HTTPException(
            status_code=403, detail=f"The key {key} has already been picked."
        )

    # key not in draft.picked
    pl = POOL_MAPPING[key]
    picks_per_pool = draft.picks_per_pool
    player_pool_picks = 0
    for pk in draft.draft:
        if POOL_MAPPING[pk.key] == pl and pk.player == user.uuid:
            player_pool_picks += 1
            if player_pool_picks >= picks_per_pool:
                raise HTTPException(
                    status_code=403, detail=f"Player has already picked the maximum number of picks for pool {pl.name.full_name}")

    p = DraftPick(key=key, player=user.uuid, index=len(draft.draft))

    draft.position.pop(0)
    draft.draft.append(p)
    if not draft.position:
        draft.position = draft.next_positions
        draft.next_positions = list(reversed(draft.next_positions))

    draft.picked.add(key)
    if not update_draft(draft, room.code):
        raise HTTPException(
            status_code=500, detail="Could not update draft internally..!"
        )

    await mg.broadcast_room(
        room,
        DraftPickUpdate(
            key=p.key,
            player=p.player,
            index=p.index,
            positions=draft.position,
            next_positions=draft.next_positions,
        ),
    )
