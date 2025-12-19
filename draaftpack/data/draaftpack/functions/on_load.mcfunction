tellraw @a {"text": "drAAftpack is enabled.", "color": "#00aa00"}

execute as @e[type=cat,sort=nearest,limit=1] run data merge entity @s {CatType:10}
advancement grant @a only minecraft:nether/create_full_beacon
advancement grant @a only minecraft:adventure/adventuring_time minecraft:deep_frozen_ocean
advancement grant @a only minecraft:adventure/adventuring_time minecraft:warm_ocean
