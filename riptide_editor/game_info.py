from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MapInfo:
    title: str = "unknown"
    password: str = ""
    music: str = ""


MAP_INFO: dict[str, MapInfo] = {
    "1-1.m": MapInfo("Shallow Sea", "1", "1.cmf"),
    "1-2.m": MapInfo("Micro Menace", "UR2GD", "2.cmf"),
    "1-3.m": MapInfo("Tulip Tango", "URGR8", "3.cmf"),
    "1-4.m": MapInfo("Red Tide", "4GOOD", "1.cmf"),
    "1-5.m": MapInfo("Fathoms of Teeth", "2MUCH4U", "2.cmf"),
    "1-6.m": MapInfo("Think Tank", "ACE", "3.cmf"),
    "bs1.m": MapInfo("Oscar's Lair", "BS1", "5.cmf"),
    "2-1.m": MapInfo("Atlantis", "DNUNDR", "oxygen.cmf"),
    "2-2.m": MapInfo("Aqua Tremendom", "OUT2GTU", "4.cmf"),
    "2-3.m": MapInfo("Spawning Waters", "AIC", "bossa.cmf"),
    "2-4.m": MapInfo("JASON Quest", "HANG10", "1.cmf"),
    "2-5.m": MapInfo("Frantic Attack", "RUN4IT", "weerd.cmf"),
    "bs2.m": MapInfo("Enter Otis", "BS2", "chaos.cmf"),
    "3-1.m": MapInfo("Sea Escape", "GETIT", "1.cmf"),
    "3-2.m": MapInfo("Deep Enigma", "URINDE", "oxygen.cmf"),
    "3-3.m": MapInfo("Sink or Swim", "SOS", "4.cmf"),
    "3-4.m": MapInfo("Marathon", "RUN2ME", "3.cmf"),
    "3-5.m": MapInfo("Lab Rynth", "512TR", "chaos.cmf"),
    "3-6.m": MapInfo("Abyss of Peril", "2B4UDY", "turn.cmf"),
    "3-7.m": MapInfo("Halls of Hell", "HOH", "2.cmf"),
    "3-8.m": MapInfo("Mysterious Maze", "RIP", "oxygen.cmf"),
    "bs3.m": MapInfo("Confrontation", "BS3", "5.cmf"),
    "sec1.m": MapInfo("Outpost Enigma", "SEC1", "4.cmf"),
    "sec2.m": MapInfo("??????", "SEC2", "weerd.cmf"),
}


ENTITY_SPRITES = {
    1: "DOOR.L", 2: "DOOR.L", 3: "DOOR.L", 4: "COIN.L",
    8: "MINE.L", 12: "ZAP_UD.L", 16: ("POD1.L", "POD2.L"),
    20: ("FISH1R.L", "FISH2R.L"), 24: "WEED1.L", 28: "TULIPL.L",
    32: "CHEST.L", 36: "PIRANAL.L", 40: "GEM.L", 44: ("DUCT_R.L", "DUCT_L.L"),
    48: "DUCT_D.L", 52: "BLOCK.L", 56: "FACE_R.L", 60: "SERP_R.L",
    64: "CRAB.L", 68: "PIECE_1.L", 72: "JELLY.L", 76: "SHARKL.L",
    80: "BONUS1.L", 84: "TENT_IN.L", 88: "SPIKES_U.L", 92: "STATUE.L",
    96: "FIRE_PIT.L", 100: "SHUTL_L.L", 104: "CLAM.L", 108: "CANNONL.L",
    112: "FACE_L.L", 116: "SHIPL.L",
}

ENTITY_INFO = {
    1: "door 1", 2: "door 2", 3: "door 3", 28: "spitting tulip",
    32: "chest spawning many coins", 44: "pushing player subs right/left",
    48: "pushing player subs up/down", 68: "piece of pulse cannon",
    84: "tentacle in hole", 100: "shooting rockets", 104: "spawning a gem",
    108: "always looking to player side", 116: "dropping bombs (SHPBMB.L)",
}

SHOOTABLE_SPRITES = {
    1: "BARREL2.L", 2: "BARREL2.L", 3: "BARREL2.L", 4: "BARREL2.L",
    5: "BARREL2.L", 6: "BARREL2.L", 7: "BARREL2.L", 8: "BARREL2.L",
    9: "BARREL2.L", 16: ("BARREL3.L", "BARREL1.L"), 32: "BARREL1.L",
    64: "SWITCH.L", 128: "SWITCH.L", 192: "SWITCH.L",
}

SHOOTABLE_INFO = {
    1: "spawning extra air", 2: "spawning extra shield", 3: "spawning extra fire power item",
    4: "spawning PU_TOP item (unknown effect)", 5: "spawning extra 1-up item", 6: "spawning green key",
    7: "spawning auto-fire", 8: "spawning Jason sub", 9: "spawning Jason sub",
    16: "spawning a coin", 32: "spawning POD1/POD2 depending on parity",
    64: "opens door 1", 128: "opens door 2", 192: "opens door 3",
}

SHOOTABLE_DROPS = {
    1: "extra air",
    2: "extra shield",
    3: "extra fire power",
    4: "PU_TOP item (unknown effect)",
    5: "extra 1-up",
    6: "green key",
    7: "auto-fire",
    8: "Jason sub",
    9: "Jason sub",
    16: "coin",
    32: "POD1/POD2 by cell parity",
}

MESSAGES = {
    0: "You need a key for this door.",
    1: "You got the key!",
    2: "Think!",
    3: "Extra fire power added!",
    4: "Auto-fire added!",
    5: "WARNING: Air is low.",
    6: "Watch out for those piranas!",
    7: "Auto Pilot ON.",
    8: "WARNING: JASON power low.",
    9: "WARNING: Shield is low.",
    10: "SHOOT THE BARRELS infobox",
    12: "PULSE CANNON infobox",
    13: "CAVES infobox",
    14: "JASON SUB infobox",
}


def map_info(filename: str) -> MapInfo:
    return MAP_INFO.get(filename.lower(), MapInfo())


def message_by_id(value: int) -> str:
    return MESSAGES.get(value, "invalid")


def trigger_name(index: int, value: int) -> str:
    if index == 0:
        return "player spawn"
    if index == 1:
        return "level exit"
    if index == 2:
        return 'message: "You need a key for this door."'
    if index == 3:
        return "key gate"
    if index == 4:
        return "level exit left"
    if 10 <= index <= 29:
        pair = (index - 10) // 2 + 1
        return f"teleport {pair} {'IN' if index % 2 == 0 else 'OUT'}"
    if index in (30, 32, 34, 36):
        return f"message {(index - 30) // 2 + 1} position"
    if index in (31, 33, 35, 37):
        return f"message {(index - 31) // 2 + 1}: {message_by_id(value)}"
    return "unknown"


def _choose_even_odd(value, even: bool) -> str:
    if isinstance(value, tuple):
        return value[0] if even else value[1]
    return value


def entity_sprite_name(entity_id: int, even_pos: bool) -> str:
    return _choose_even_odd(ENTITY_SPRITES.get(entity_id, ""), even_pos)


def shootable_sprite_name(shootable_id: int, even_pos: bool) -> str:
    return _choose_even_odd(SHOOTABLE_SPRITES.get(shootable_id, ""), even_pos)


def shootable_drop_name(shootable_id: int) -> str:
    return SHOOTABLE_DROPS.get(shootable_id, "")
