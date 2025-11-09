from collections import defaultdict
from enum import Enum
from typing import DefaultDict, Literal
from typing_extensions import override
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Response

from utils import LOG

rt = APIRouter(prefix='/draft')

class AutoName(BaseModel):
    @staticmethod
    def make_simple(name: str) -> 'AutoName':
        return AutoName(full_name=name, short_name=name)

    full_name: str
    short_name: str

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
    def basic(key: str, description: str, image: str | None = None, name: str | None = None, advancement: str | None = None) -> "Draftable":
        if image is None:
            image = f'{key}.png'
        if name is None:
            name = key
        return Draftable(key=key, name=AutoName.make_simple(name), description=description, image_uri=image, advancement=advancement)

class PoolTypeEnum(str, Enum):
    icons = 'icons'
    auto_names = 'auto_names'

class DraftPool(BaseModel):
    name: AutoName

    # Draftables (keys)
    contains: list[str]

    # Pool type
    kind: PoolTypeEnum


class Datapack:
    def __init__(self):
        pass

    def onload(self, user: str) -> str:
        return ""

    def ontick(self, user: str) -> str:
        return ""

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


PRETTY_ADVANCEMENTS = { "adventure/adventuring_time": "Adventuring Time",
                       "adventure/kill_all_mobs": "Monsters Hunted",
                       "husbandry/bred_all_animals": "Two by Two" }
def prettify_advancement(advancement: str):
    if advancement in PRETTY_ADVANCEMENTS:
        return PRETTY_ADVANCEMENTS[advancement]
    return ((advancement.split(':')[-1]).split('/')[-1]).replace('_', ' ').capitalize()


class AdvancementGranter(Datapack):
    def __init__(self, advancement: str, criteria: str | None = None, pretty: str | None=None, prefix="minecraft", specifier="only", player: str | None = None):
        self.advancement = advancement
        self.criteria=criteria
        self.pretty = pretty if pretty is not None else prettify_advancement(advancement)
        self.player = player
        self.prefix=prefix
        self.specifier = specifier

    @override
    def onload(self, user: str) -> str:
        return self.build(user)

    def build(self, user: str) -> str:
        user = self.player or user
        crit = "" if self.criteria is None else f" {self.prefix}:{self.criteria}"
        return f"advancement grant {user} {self.specifier} {self.prefix}:{self.advancement}{crit}"

    def description(self) -> str:
        if self.criteria is not None:
            return f"Grants the criteria {prettify_advancement(self.criteria)} from {self.pretty}"
        return f"Grants the advancement {self.pretty}"

class SimpleMultiCriteria(Datapack):
    def __init__(self, advancement: str, criteria: list[str], prefix="minecraft", specifier="only", player: str | None = None):
        self.criteria: list[AdvancementGranter] = list()
        for crit in criteria:
            self.criteria.append(AdvancementGranter(advancement, crit, None, prefix, specifier, player))
        self.adv = prettify_advancement(advancement) 

    @override
    def onload(self, user: str) -> str:
        return self.build(user)

    def build(self, user: str) -> str:
        return "\n".join([c.build(user) for c in self.criteria])

    def description(self) -> str:
        # this is just to placate, they're guaranteed valid :) never buggy!!!
        criteriaes = ', '.join([prettify_advancement(c.criteria or "") for c in self.criteria])
        return f"Grants the criteria {criteriaes} from {self.adv}"


DRAFTABLES: dict[str, Draftable] = {}
DATAPACK: dict[str, list[Datapack]] = dict()
_draftable_file = "draftables.json"
def _add_draftable(d: Draftable, datapack: None | list[Datapack] = None):
    DRAFTABLES[d.key] = d
    if datapack is not None:
        DATAPACK[d.key] = datapack

def _add_advancement(key: str, image: str, advs: list[str | tuple[str, list[str]]], advancement="challenge.png"):
    l: list[Datapack] = list()
    for adv in advs:
        if isinstance(adv, str):
            l.append(AdvancementGranter(advancement=adv))
        else:
            l.append(SimpleMultiCriteria(adv[0], adv[1]))
    desc = "\n".join([x.description() for x in l])
    _add_draftable(Draftable.basic(key, desc, image, advancement=advancement), l)


# Armour
_add_draftable(Draftable.basic(key="bucket", description="A fully-enchanted, max-tier bucket.", image="bucket.png"))
_add_draftable(Draftable.basic(key="helmet", description="Gives fully enchanted diamond helmet", image="helmet.gif"))
_add_draftable(Draftable.basic(key="chestplate", description="Gives fully enchanted diamond chestplate", image="chestplate.gif"))
_add_draftable(Draftable.basic(key="leggings", description="Gives fully enchanted diamond leggings", image="leggings.gif"))
_add_draftable(Draftable.basic(key="boots", description="Gives fully enchanted diamond boots", image="boots.gif"))

# Tools
_add_draftable(Draftable.basic(key="sword", description="Gives fully enchanted diamond sword", image="sword.gif"))
_add_draftable(Draftable.basic(key="pickaxe", description="Gives fully enchanted diamond pickaxe", image="pickaxe.gif"))
_add_draftable(Draftable.basic(key="axe", description="Gives fully enchanted diamond axe", image="axe.gif"))
_add_draftable(Draftable.basic(key="shovel", description="Gives fully enchanted diamond shovel", image="shovel.gif"))
_add_draftable(Draftable.basic(key="hoe", description="Gives fully enchanted netherite hoe", image="netherite_hoe.gif"))
_add_draftable(Draftable.basic(key="trident", description="Gives fully enchanted netherite trident", image="trident.gif"))

# Biomes
_add_advancement(key="badlands", image="badlands.png", advs=[("adventure/adventuring_time", ["badlands", "badlands_plateau", "wooded_badlands_plateau"]), ("adventure/kill_all_mobs", ["cave_spider"])])
  
_add_advancement(key="jungle", image="bamboo_jungle.png", advs=[
("adventure/adventuring_time", ["minecraft:bamboo_jungle",
 "minecraft:bamboo_jungle_hills",
 "minecraft:jungle_hills",
 "minecraft:jungle_edge",
 "minecraft:jungle"]),
("husbandry/bred_all_animals", ["minecraft:panda",
 "minecraft:ocelot"]),
("husbandry/balanced_diet", ["melon_slice",
 "cookie"])])

_add_advancement(key="snowy", image="snowy_taiga.png", advs=[
("adventure/adventuring_time", ["snowy_tundra",
"snowy_taiga",
"snowy_taiga_hills",
"snowy_mountains",
"snowy_beach",
"frozen_river"]),
("adventure/kill_all_mobs", ["stray"]),
"story/cure_zombie_villager"])

_add_advancement(key="mega_taiga", image="giant_tree_taiga.png", advs=[
    ("adventure/adventuring_time", ["giant_tree_taiga", "giant_tree_taiga_hills"]),
("husbandry/balanced_diet", ["sweet_berries"]),
("husbandry/bred_all_animals", ["fox"])])

_add_advancement(key="mushroom_island", image="mushroom_field_shore.png", 
advs=[("adventure/adventuring_time", ["mushroom_fields", "mushroom_field_shore"]),
("husbandry/bred_all_animals", ["mooshroom"])])

"""
// Pool: Armour
let dHelmet = new DraftItem(
    "Helmet",
    "Gives fully enchanted diamond helmet",
    "helmet.png",
    (file) => {
        file += `
give @a minecraft:diamond_helmet{Enchantments:[{id:"minecraft:protection",lvl:5},{id:"minecraft:unbreaking",lvl:3},{id:"minecraft:respiration",lvl:3},{id:"minecraft:aqua_affinity",lvl:1}]}
        `;
        return file;
    }
);
let dChestplate = new DraftItem(
    "Chestplate",
    "Gives fully enchanted diamond chestplate",
    "chestplate.png",
    (file) => {
        file += `
give @a minecraft:diamond_chestplate{Enchantments:[{id:"minecraft:protection",lvl:5},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dLeggings = new DraftItem(
    "Leggings",
    "Gives fully enchanted diamond leggings",
    "leggings.png",
    (file) => {
        file += `
give @a minecraft:diamond_leggings{Enchantments:[{id:"minecraft:protection",lvl:5},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dBoots = new DraftItem(
    "Boots",
    "Gives fully enchanted diamond boots",
    "boots.png",
    (file) => {
        file += `
give @a minecraft:diamond_boots{Enchantments:[{id:"minecraft:protection",lvl:5},{id:"minecraft:unbreaking",lvl:3},{id:"minecraft:depth_strider",lvl:3}]}
        `;
        return file;
    }
);
let dBucket = new DraftItem(
    "Bucket",
    "Gives a fully enchanted, max-tier bucket",
    "bucket.png",
    (file) => {
        file += `
give @a minecraft:bucket{Enchantments:[{}]}
        `;
        return file;
    }
);

// Pool: Tools
let dSword = new DraftItem(
    "Sword",
    "Gives fully enchanted diamond sword",
    "sword.png",
    (file) => {
        file += `
give @a minecraft:diamond_sword{Enchantments:[{id:"minecraft:smite",lvl:5},{id:"minecraft:looting",lvl:3},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dPickaxe = new DraftItem(
    "Pickaxe",
    "Gives fully enchanted diamond pickaxe",
    "pickaxe.png",
    (file) => {
        file += `
give @a minecraft:diamond_pickaxe{Enchantments:[{id:"minecraft:efficiency",lvl:5},{id:"minecraft:fortune",lvl:3},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dShovel = new DraftItem(
    "Shovel",
    "Gives fully enchanted diamond shovel",
    "shovel.png",
    (file) => {
        file += `
give @a minecraft:diamond_shovel{Enchantments:[{id:"minecraft:efficiency",lvl:5},{id:"minecraft:fortune",lvl:3},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dHoe = new DraftItem(
    "Hoe",
    "Gives fully enchanted netherite hoe",
    "hoe.png",
    (file) => {
        file += `
give @a minecraft:netherite_hoe{Enchantments:[{id:"minecraft:efficiency",lvl:5},{id:"minecraft:silk_touch",lvl:1},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dAxe = new DraftItem(
    "Axe",
    "Gives fully enchanted diamond axe",
    "axe.png",
    (file) => {
        file += `
give @a minecraft:diamond_axe{Enchantments:[{id:"minecraft:efficiency",lvl:5},{id:"minecraft:silk_touch",lvl:1},{id:"minecraft:unbreaking",lvl:3}]}
        `;
        return file;
    }
);
let dTrident = new DraftItem(
    "Trident",
    "Gives fully enchanted netherite trident",
    "trident.png",
    (file) => {
        file += `
give @a minecraft:trident{Enchantments:[{id:"minecraft:channeling",lvl:1},{id:"minecraft:loyalty",lvl:3},{id:"minecraft:impaling",lvl:5}]}
        `;
        return file;
    }
);

// Pool: Big
let dACC = new DraftItem(
    "A Complete Catalogue",
    "Gives a complete catalogue",
    "acc.png",
    (file) => {
        file += `
advancement grant @a only minecraft:husbandry/complete_catalogue
        `;
        return file;
    }
);
dACC.boxName = "Catalogue";
let dAT = new DraftItem(
    "Adventuring Time",
    "Gives adventuring time",
    "at.png",
    (file) => {
        file += `
advancement grant @a only minecraft:adventure/adventuring_time
        `;
        return file;
    }
);
dAT.boxName = "Adventuring";
dAT.smallName = "AT";
let d2b2 = new DraftItem(
    "Two by Two",
    "Gives two by two",
    "2b2.png",
    (file) => {
        file += `
advancement grant @a only minecraft:husbandry/bred_all_animals
        `;
        return file;
    }
);
let dMH = new DraftItem(
    "Monsters Hunted",
    "Gives monsters hunted",
    "mh.png",
    (file) => {
        file += `
advancement grant @a only minecraft:adventure/kill_all_mobs
        `;
        return file;
    }
);
dMH.boxName = "Monsters";
let dABD = new DraftItem(
    "A Balanced Diet",
    "Gives a balanced diet",
    "abd.png",
    (file) => {
        file += `
advancement grant @a only minecraft:husbandry/balanced_diet
        `;
        return file;
    }
);
dABD.boxName = "Balanced Diet";
dABD.smallName = "Balanced";

// Pool: Collectors
let dNetherite = new DraftItem(
    "Netherite",
    "Gives 4 netherite ingots",
    "netherite.png",
    (file) => {
        file += `
give @a minecraft:netherite_ingot 4
        `;
        return file;
    }
);
let dShells = new DraftItem(
    "Shells",
    "Gives 7 nautilus shells",
    "shell.png",
    (file) => {
        file += `
give @a minecraft:nautilus_shell 7
        `;
        return file;
    }
);
let dSkulls = new DraftItem(
    "Skulls",
    "Gives 2 wither skeleton skulls",
    "skull.png",
    (file) => {
        file += `
give @a minecraft:wither_skeleton_skull 2
        `;
        return file;
    }
);
let dBreeds = new DraftItem(
    "Breeds",
    "Gives breed for horse, donkey, mule, llama, wolf, fox, & turtle",
    "breeds.png",
    (file) => {
        file += `
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:horse
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:donkey
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:mule
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:llama
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:wolf
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:fox
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:turtle
        `;
        return file;
    }
);
let dShulker = new DraftItem(
    "Shulker Box",
    "Gives a shulker box",
    "shulker.png",
    (file) => {
        file += `
give @a minecraft:shulker_box
        `;
        return file;
    }
);
dShulker.smallName = "Box";
let dBees = new DraftItem(
    "Bees",
    "Gives all bee-related requirements",
    "bees.png",
    (file) => {
        file += `
advancement grant @a only minecraft:husbandry/safely_harvest_honey
advancement grant @a only minecraft:husbandry/silk_touch_nest
advancement grant @a only minecraft:adventure/honey_block_slide
advancement grant @a only minecraft:husbandry/bred_all_animals minecraft:bee
advancement grant @a only minecraft:husbandry/balanced_diet honey_bottle
        `;
        return file;
    }
);
let dHives = new DraftItem(
    "Hives",
    "Gives the user two 3-bee hives",
    "hive.png",
    itemGiver('bee_nest{BlockEntityTag:{Bees:[{MinOccupationTicks:600,TicksInHive:500,EntityData:{Brain:{memories:{}},HurtByTimestamp:0,HasStung:0b,Attributes:[],Invulnerable:0b,FallFlying:0b,ForcedAge:0,PortalCooldown:0,AbsorptionAmount:0.0f,FallDistance:0.0f,InLove:0,DeathTime:0s,HandDropChances:[0.085f,0.085f],CannotEnterHiveTicks:0,PersistenceRequired:0b,id:"minecraft:bee",Age:0,TicksSincePollination:0,AngerTime:0,Motion:[0.0d,0.0d,0.0d],Health:10.0f,HasNectar:0b,LeftHanded:0b,Air:300s,OnGround:0b,Rotation:[1.2499212f,0.0f],HandItems:[{},{}],ArmorDropChances:[0.085f,0.085f,0.085f,0.085f],Pos:[0.0d,0.0d,0.0d],Fire:-1s,ArmorItems:[{},{},{},{}],CropsGrownSincePollination:0,CanPickUpLoot:0b,HurtTime:0s}},{MinOccupationTicks:600,TicksInHive:500,EntityData:{Brain:{memories:{}},HurtByTimestamp:0,HasStung:0b,Attributes:[],Invulnerable:0b,FallFlying:0b,ForcedAge:0,PortalCooldown:0,AbsorptionAmount:0.0f,FallDistance:0.0f,InLove:0,DeathTime:0s,HandDropChances:[0.085f,0.085f],CannotEnterHiveTicks:0,PersistenceRequired:0b,id:"minecraft:bee",Age:0,TicksSincePollination:0,AngerTime:0,Motion:[0.0d,0.0d,0.0d],Health:10.0f,HasNectar:0b,LeftHanded:0b,Air:300s,OnGround:0b,Rotation:[1.2499212f,0.0f],HandItems:[{},{}],ArmorDropChances:[0.085f,0.085f,0.085f,0.085f],Pos:[0.0d,0.0d,0.0d],Fire:-1s,ArmorItems:[{},{},{},{}],CropsGrownSincePollination:0,CanPickUpLoot:0b,HurtTime:0s}},{MinOccupationTicks:600,TicksInHive:500,EntityData:{Brain:{memories:{}},HurtByTimestamp:0,HasStung:0b,Attributes:[],Invulnerable:0b,FallFlying:0b,ForcedAge:0,PortalCooldown:0,AbsorptionAmount:0.0f,FallDistance:0.0f,InLove:0,DeathTime:0s,HandDropChances:[0.085f,0.085f],CannotEnterHiveTicks:0,PersistenceRequired:0b,id:"minecraft:bee",Age:0,TicksSincePollination:0,AngerTime:0,Motion:[0.0d,0.0d,0.0d],Health:10.0f,HasNectar:0b,LeftHanded:0b,Air:300s,OnGround:0b,Rotation:[1.2499212f,0.0f],HandItems:[{},{}],ArmorDropChances:[0.085f,0.085f,0.085f,0.085f],Pos:[0.0d,0.0d,0.0d],Fire:-1s,ArmorItems:[{},{},{},{}],CropsGrownSincePollination:0,CanPickUpLoot:0b,HurtTime:0s}}]}}', 2)
);

// Pool: misc
let dTotem = new DraftItem(
    "Totem",
    "Gives totem of undying and evoker & vex kill credit",
    "skull.png",
    (file) => {
        file += `
give @a minecraft:totem_of_undying
advancement grant @a only minecraft:adventure/kill_all_mobs minecraft:evoker
advancement grant @a only minecraft:adventure/kill_all_mobs minecraft:vex
        `;
        return file;
    }
);
let dFireworks = new DraftItem(
    "Fireworks",
    "Gives 23 gunpowder / paper",
    "firework.png",
    itemGiver("gunpowder", 23, "paper", 23),
);
let dGrace = new DraftItem(
    "Dolphin's Grace",
    "Gives dolphin's grace",
    "firework.png",
    (file) => {
        file += `
effect give @a minecraft:dolphins_grace 3600
        `;
        return file;
    }
);
dGrace.simpleName = "Grace";
dGrace.boxName = "Grace";
dGrace.fileQuery = "tick.mcfunction";
let dLeads = new DraftItem(
    "Leads",
    "Gives 23 leads & slime kill",
    "leads.png",
    (file) => {
        file += `
advancement grant @a only minecraft:adventure/kill_all_mobs minecraft:slime
give @a minecraft:lead 23
        `;
        return file;
    }
);

let dFireRes = new DraftItem(
    "Fire Resistance",
    "Gives permanent fire resistance.",
    "fres.png",
    (file) => {
        file += `
effect give @a minecraft:fire_resistance 3600
        `;
        return file;
    }
);
dFireRes.fileQuery = "tick.mcfunction";
dFireRes.boxName = "Fire Res";
dFireRes.simpleName = "Fire Res";
let dObi = new DraftItem(
    "Obsidian",
    "Gives 10 obsidian.",
    "obi.png",
    itemGiver("obsidian", 10),
);
let dLogs = new DraftItem(
    "Logs",
    "Gives 64 oak logs.",
    "logs.png",
    itemGiver("acacia_log", 64),
);
let dEyes = new DraftItem(
    "Eyes",
    "Gives 2 eyes of ender.",
    "eyes.png",
    itemGiver("ender_eye", 2),
);
let dCrossbow = new DraftItem(
    "Crossbow",
    "Gives a Piercing IV crossbow.",
    "crossbow.png",
    itemGiver('crossbow{Enchantments:[{id:"minecraft:piercing",lvl:4s}]}', 1),
);
let SHULKER_COLOUR=Math.floor(Math.random() * 17)
let dShulkerBoat = new DraftItem(
    "Transport",
    "Grants a boated shulker at your spawn location.",
    "shulker.png",
    (file) => {
        file += `
execute at @a run summon minecraft:boat ~ ~2 ~ {Passengers:[{id:shulker,Color:${SHULKER_COLOUR}}]}
        `;
        return file;
    }
)

let dRods = new DraftItem(
    "Rod Rates",
    "Blazes never drop 0 rods.",
    "blaze.png",
    (file) => {
        file += `
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
        `;
        return file;
    }


# Configurable later, just get it working for now.
POOLS: list[DraftPool] = [
    DraftPool(name=AutoName.make_simple('Armour'), contains=["helmet", "chestplate", "leggings", "boots", "bucket"], kind=PoolTypeEnum.icons),
    DraftPool(name=AutoName.make_simple('Tools'), contains=["sword", "pickaxe", "shovel", "hoe", "axe", "trident"], kind=PoolTypeEnum.icons),
]
"""


class DraftPick(BaseModel):
    # Key of the draftable
    key: str
    # UUID of the player who drafted it (for now, I guess)
    player: str
    # Number of the pick
    index: int


class DraftPickUpdate(DraftPick):
    variant: Literal['draftpick'] = 'draftpick'
    positions: list[str]
    next_positions: list[str]


class Draft(BaseModel):
    @staticmethod
    def from_players(players: set[str]) -> 'Draft':
        import random
        p = list(players)
        random.shuffle(p)
        return Draft(players=p, position=list(p), next_positions=list(reversed(p)))

    def serialized(self) -> str:
        from models.ws import serialize
        res = serialize(self)
        if res is None:
            raise RuntimeError('Could not serialize draft object?!')
        return res

    players: list[str] = list()
    draft: list[DraftPick] = list()
    position: list[str] = list() # Current set of draft picks
    next_positions: list[str] = list() # next set of draft picks
    picked: set[str] = set()
    complete: bool = False

@rt.get('/status')
async def get_status(request: Request) -> Draft:
    from db import get_started_room
    LOG("Getting status of room...")
    ru = get_started_room(request)
    if ru is None:
        raise HTTPException(status_code=404, detail="no valid draft found")
    return ru[2]

@rt.get('/draftables')
async def get_draftables() -> tuple[list[DraftPool], dict[str, Draftable]]:
    return (POOLS, DRAFTABLES)

@rt.post('/pick')
async def do_pick(request: Request, key: str):
    from db_utils import always_get_drafting_player
    from room_manager import mg
    from rooms import update_draft
    user, room, draft = always_get_drafting_player(request)
    
    if user.uuid != draft.position[0]:
        raise HTTPException(status_code=403, detail="You cannot pick right now.")
    if key not in DRAFTABLES:
        raise HTTPException(status_code=404, detail=f"Draft pick {key} could not be found.")
    if key in draft.picked:
        raise HTTPException(status_code=403, detail=f"The key {key} has already been picked.")

    p = DraftPick(key=key, player=user.uuid, index=len(draft.draft))

    draft.position.pop(0)
    draft.draft.append(p)
    if not draft.position:
        draft.position = draft.next_positions
        draft.next_positions = list(reversed(draft.next_positions))

    draft.picked.add(key)
    if not update_draft(draft, room.code):
        raise HTTPException(status_code=500, detail='Could not update draft internally..!')

    await mg.broadcast_room(room, DraftPickUpdate(key=p.key, player=p.player, index=p.index, positions=draft.position, next_positions=draft.next_positions))
