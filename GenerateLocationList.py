from __future__ import annotations
from enum import Enum
from typing import Callable, NamedTuple, Optional

from GetActors import scene_get_actors
from ItemList import item_table
from ItemPool import deku_scrubs_items
from LocationList import business_scrubs
from Rom import Rom
from Scenes import Scenes
from Utils import data_path


class ActorEntry(NamedTuple):
    actor_id: int
    actor_variable: int
    scene: int
    room_id: int
    setup_num: int
    actor_num: int


class LocationCategory(str, Enum):
    CHEST = 'Chest'
    SCRUB = 'Scrub'
    COLLECTABLE = 'Collectable'
    SILVER_RUPEE = 'SilverRupee'
    NPC = 'NPC'
    GS_TOKEN = 'GS Token'
    FREESTANDING = 'Freestanding'
    RUPEE_TOWER = 'RupeeTower'
    POT = 'Pot'
    FLYING_POT = 'FlyingPot'
    CRATE = 'Crate'
    SMALL_CRATE = 'SmallCrate'
    BEEHIVE = 'Beehive'
    WONDERITEM = 'Wonderitem'
    BOSS_HEART = 'BossHeart'
    DROP = 'Drop'


def generate_location_list(rom: Rom, patch_scenes: list, rom_name: str, rom_short_name: str) -> None:
    contents = ''
    contents += 'from __future__ import annotations\n'
    contents += 'from collections import OrderedDict\n'
    contents += 'from typing import Optional, TypeAlias\n'
    contents += '\n'
    contents += 'LocationDefault: TypeAlias = "Optional[int | tuple[int, ...] | list[tuple[int, ...]]]"\n'
    contents += 'LocationAddress: TypeAlias = "Optional[int | list[int]]"\n'
    contents += 'LocationAddresses: TypeAlias = "Optional[tuple[LocationAddress, LocationAddress]]"\n'
    contents += 'LocationFilterTags: TypeAlias = "Optional[tuple[str, ...] | str]"\n'
    contents += '\n'
    contents += '#   Location:                                                        Type             Scene  Default Addresses                      Vanilla Item                             Categories\n'
    contents += 'location_table: dict[str, tuple[str, Optional[int], LocationDefault, LocationAddresses, Optional[str], LocationFilterTags]] = OrderedDict(['
    scene_table = 0x00B71440
    for scene_id in patch_scenes:
        if scene_id in patch_scenes:
            scn = Scenes.for_id(scene_id)
            scene_data = rom.read_int32(scene_table + (scene_id * 0x14))

            # Scene header
            contents += '\n'
            contents += f'    # {scn} {rom_short_name}\n'

            # Helper function for getting actor entries
            def get_actor_entry_if(condition: Callable[[ActorEntry], bool]):
                def get_actor_entry(rom: Rom, actor_id: int, actor: int, scene: int, room_id: int, setup_num: int, actor_num: int) -> Optional[ActorEntry]:
                    actor_variable = rom.read_int16(actor + 0x0E)
                    entry = ActorEntry(
                        actor_id, actor_variable, scene, room_id, setup_num, actor_num)
                    if condition(entry):
                        return entry
                    else:
                        return None
                return get_actor_entry

            # Chests
            def get_chests(rom: Rom, actor_id: int, actor: int, scene: int, room_id: int, setup_num: int, actor_num: int) -> Optional[ActorEntry]:
                actor_variable = rom.read_int16(actor + 0x0E)
                if actor_id == 0x000A:
                    return ActorEntry(actor_id, actor_variable, scene, room_id, setup_num, actor_num)
                elif actor_id == 0x0068 and (actor_variable & 0x8000) == 0 and (actor_variable & 0x4000) == 0:
                    # Forest twisted hallway spawns boss key chest
                    return ActorEntry(0x000A, 0x27EE, scene, room_id, setup_num, actor_num)
                else:
                    return None
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_chests, scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_chest(actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {room_id_count[1]} {name}',
                    category,
                    scene,
                    f'0x{(actor_variable & 0x001F):02X}',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Chests",)',
                    setup_num,
                )

            # Scrubs
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x0195), scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_scrub(actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} {name} Room {room_id} {room_id_count[1]}',
                    category,
                    scene,
                    f'0x{(business_scrubs[actor_variable][0]):02X}',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "{name}",)',
                    setup_num,
                )

            # Collectables
            def get_freestandings(rom: Rom, actor_id: int, actor: int, scene: int, room_id: int, setup_num: int, actor_num: int) -> Optional[ActorEntry]:
                actor_variable = rom.read_int16(actor + 0x0E)
                if actor_id == 0x0015:
                    return ActorEntry(actor_id, actor_variable, scene, room_id, setup_num, actor_num)
                elif actor_id == 0x00BB and room_id != 12:
                    # Shadow pot spawns freestanding key
                    return (0x0015, ((actor_variable & 0x3F) << 8) | 0x0011, scene, room_id, setup_num, actor_num)
                elif actor_id == 0x015C:
                    # Goron pot spawns freestanding PoH
                    return (0x0015, (actor_variable << 8) | 0x0007, scene, room_id, setup_num, actor_num)
                else:
                    return None
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_freestandings, scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_freestanding(
                    actor_variable, scn)
                collectable_flag = (actor_variable & 0x3F00) >> 8
                if vanilla_item is None:
                    continue
                if category != LocationCategory.COLLECTABLE:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'0x{collectable_flag:02X}',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Freestandings",)',
                    setup_num,
                )

            # Cows
            actors: dict[int, ActorEntry] = scene_get_actors(rom, get_actor_entry_if(
                lambda entry: entry.actor_id == 0x01C6), scene_data, scene_id)
            cow_id = 0
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_cow(
                    actor_variable, f'{scn} Room {room_id}')
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {room_id_count[1]} {name}',
                    category,
                    scene,
                    f'0x{(0x15 + cow_id):02X}',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "{name}",)',
                    setup_num,
                )
                cow_id += 1

            # Gold Skulltulas
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x0095 and (entry.actor_variable & 0xE000) != 0x0000), scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_gold_skulltula(
                    actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} {name} Room {room_id} {room_id_count[1]}',
                    category,
                    scene,
                    f'0x{(actor_variable & 0x00FF):02X}',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Gold Skulltulas",)',
                    setup_num,
                )

            # Freestandings
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_freestandings, scene_data, scene_id)
            if len(actors) > 0:
                contents += f'    # {scn} {rom_short_name} Freestanding\n'
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                if actor_id == 0x0015:
                    (name, vanilla_item, category) = get_freestanding(
                        actor_variable, scn)
                elif actor_id == 0x00BB and room_id != 12:
                    # Shadow pot drops freestanding key
                    (name, vanilla_item, category) = get_freestanding(
                        0x0011, scn)
                elif actor_id == 0x015C:
                    # Goron pot drops freestanding PoH
                    (name, vanilla_item, category) = get_freestanding(
                        0x0007, scn)
                if vanilla_item is None:
                    continue
                if category != LocationCategory.FREESTANDING:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Freestandings",)',
                    setup_num,
                )

            # Rupee Towers
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x01AB), scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                rupees = get_rupee_tower(actor_variable, scn)
                for (name, vanilla_item, category) in rupees:
                    if vanilla_item is None:
                        continue
                    if room_id != room_id_count[0]:
                        room_id_count = (room_id, 0)
                    room_id_count = (room_id_count[0], room_id_count[1] + 1)
                    contents += get_location_line(
                        f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count + 1}',
                        category,
                        scene,
                        # TODO.GQ: Update this to be correct
                        f'({room_id},{setup_num},0x{(0x40 + room_id_count):02X})',
                        # TODO.GQ: Update this to be correct
                        'None',
                        vanilla_item,
                        f'("{scn.category} {rom_short_name}", "{rom_name}", "Rupee Towers",)',
                        setup_num,
                    )

            # Shadow Pot Rupees (9 individual rupees that we claim to be a Rupee Tower)
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x00BB and entry.room_id == 12), scene_data, scene_id)
            addresses: list[str] = [f'0x{key:07X}' for key in actors.keys()]
            entries: list[tuple[int, ActorEntry]] = list(actors.values())
            # We are only dealing with room id 12
            rupee_count = 0
            if len(actors) >= 3:
                # Look at 3rd pot for scene and room_id
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entries[2]
                rupees: list[tuple[str, str, LocationCategory]] = [('Rupee', 'Rupee (1)', LocationCategory.RUPEE_TOWER), (
                    'Rupee', 'Rupees (5)', LocationCategory.RUPEE_TOWER), ('Rupee', 'Rupees (20)', LocationCategory.RUPEE_TOWER)] * 3
                for (name, vanilla_item, category) in rupees:
                    contents += get_location_line(
                        f'{scn} {rom_short_name} Room {room_id} {name} {rupee_count + 1}',
                        category,
                        scene,
                        # TODO.GQ: Update this to be correct
                        f'({room_id},{setup_num},{20 + rupee_count})',
                        f'([{", ".join(addresses)}], None)' if rupee_count == 0 else 'None',
                        vanilla_item,
                        f'("{scn.category} {rom_short_name}", "{rom_name}", "Rupee Towers",)',
                        setup_num,
                    )
                    rupee_count += 1

            # Beehives
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x019E), scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_beehive(actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    # TODO.GQ: Update this to be correct
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "{name}",)',
                    setup_num,
                )

            # Pots
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x0111), scene_data, scene_id)
            # TODO.GQ: Include FlyingPots in count
            if len(actors) > 0:
                contents += f'    # {scn} {rom_short_name} Pots\n'
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_pot(actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                if vanilla_item == 'Flexible':
                    contents += '#'
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Pots",)',
                    setup_num,
                )

            # Flying Pots
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x011D), scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_flying_pot(actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                if vanilla_item == 'Flexible':
                    contents += '#'
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Flying Pots",)',
                    setup_num,
                )

            # Crates
            def get_crates(rom: Rom, actor_id: int, actor: int, scene: int, room_id: int, setup_num: int, actor_num: int) -> Optional[ActorEntry]:
                # xxzz, x-rotation xx = drop, z-rotation zz = flag
                actor_variable = (rom.read_int16(actor + 0x08)
                                  << 8) | rom.read_int16(actor + 0x0C)
                if actor_id == 0x01A0:
                    return ActorEntry(actor_id, actor_variable, scene, room_id, setup_num, actor_num)
                else:
                    return None
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_crates, scene_data, scene_id)
            # TODO.GQ: Include SmallCrates in count
            if len(actors) > 0:
                contents += f'    # {scn} {rom_short_name} Crates\n'
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_crate(actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Crates",)',
                    setup_num,
                )

            # Small Crates
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x0110), scene_data, scene_id)
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_small_crate(
                    actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Small Crates",)',
                    setup_num,
                )

            # Wonderitems
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x0112 and ((entry.actor_variable & 0x07C0) >> 6) < len(wonderitems)), scene_data, scene_id)
            if len(actors) > 0:
                contents += f'    # {scn} {rom_short_name} Wonderitems\n'
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_wonderitem(
                    actor_variable, scn)
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "{name}",)',
                    setup_num,
                )

            # Silver Rupees
            actors: dict[int, ActorEntry] = scene_get_actors(
                rom, get_actor_entry_if(lambda entry: entry.actor_id == 0x0117 and ((entry.actor_variable & 0xF000) >> 12) == 0x0001), scene_data, scene_id)
            if len(actors) > 0:
                contents += '\n'
                contents += f'    # {scn} {rom_short_name} Silver Rupees'
            room_id_count: tuple[int, int] = (-1, 0)
            for entry in actors.values():
                (actor_id, actor_variable, scene, room_id,
                 setup_num, actor_num) = entry
                (name, vanilla_item, category) = get_silver_rupee(
                    actor_variable, f'{scn} Room {room_id}')
                if vanilla_item is None:
                    continue
                if room_id != room_id_count[0]:
                    room_id_count = (room_id, 0)
                    contents += '\n'
                room_id_count = (room_id_count[0], room_id_count[1] + 1)
                contents += get_location_line(
                    f'{scn} {rom_short_name} Room {room_id} {name} {room_id_count[1]}',
                    category,
                    scene,
                    f'({room_id},{setup_num},{actor_num + 1})',
                    'None',
                    vanilla_item,
                    f'("{scn.category} {rom_short_name}", "{rom_name}", "Silver Rupees",)',
                    setup_num,
                )

    contents += '])\n'

    with open(data_path(f'Temp{rom_short_name}LocationList.py'), 'w') as stream:
        stream.write(contents)


item_conversion_table: dict[int, int] = {
    0x04: 0x83,  # Fairy Bow
    0x05: 0x84,  # Fairy Slingshot
    0x08: 0x80,  # Hookshot
    0x09: 0x80,  # Longshot
    0x0C: 0x8B,  # Ocarina of Time
    0x10: 0x8C,  # Red Potion
    0x11: 0x8D,  # Green Potion
    0x12: 0x8E,  # Blue Potion
    0x13: 0x8F,  # Bottled Fairy
    0x30: 0x83,  # Big Quiver
    0x31: 0x83,  # Biggest Quiver
    0x32: 0x82,  # Bomb Bag
    0x33: 0x82,  # Big Bomb Bag
    0x34: 0x82,  # Biggest Bomb Bag
    0x35: 0x81,  # Silver Gauntlets
    0x36: 0x81,  # Golden Gauntlets
    0x37: 0x86,  # Silver Scale
    0x38: 0x86,  # Golden Scale
    0x3B: 0x8B,  # Fairy Ocarina
    0x3C: 0x4D,  # Blue (5) rupee
    0x43: 0x43,  # Small Magic Jar
    0x44: 0x44,  # Large Magic Jar
    0x45: 0x85,  # Adult Wallet
    0x46: 0x85,  # Giant Wallet
    0x4F: 0x3D,  # Heart Container
    0x54: 0x81,  # Goron Bracelet
    0x5F: 0x84,  # Bullet Bag (40)
    0x60: 0x84,  # Bullet Bag (40)
    0x61: 0x07,  # Deku Stick
    0x62: 0x07,  # Deku Stick
    0x63: 0x02,  # Deku Nuts
    0x65: 0x65,  # Bombs (1)
    0x6C: 0x90,  # Bottled Fish
    0x6D: 0x92,  # Bottled Bug
    0x6E: 0x91,  # Blue Fire
    0x6F: 0x94,  # Bottled Poe
    0x70: 0x93,  # Bottled Big Poe
    0x77: 0x88,  # Deku Stick Upgrade (20)
    0x78: 0x88,  # Deku Stick Upgrade (30)
    0x79: 0x87,  # Deku Nut Upgrade (30)
    0x7A: 0x87,  # Deku Nut Upgrade (40)
    0x7B: 0x84,  # Bullet Bag (50)
}


freestandings: tuple[str, str, LocationCategory] = [
    ("Green Rupee", "Rupee (1)", LocationCategory.FREESTANDING),
    ("Blue Rupee", "Rupees (5)", LocationCategory.FREESTANDING),
    ("Red Rupee", "Rupees (20)", LocationCategory.FREESTANDING),
    ("Recovery Heart", "Recovery Heart", LocationCategory.FREESTANDING),
    ("Bomb", "Bomb (1)", LocationCategory.FREESTANDING),
    ("Arrow", "Arrow (1)", LocationCategory.FREESTANDING),
    ("Freestanding PoH", "Piece of Heart", LocationCategory.COLLECTABLE),
    ("Heart", "Heart Container", LocationCategory.BOSS_HEART),
    ("Arrows", "Arrows (5)", LocationCategory.FREESTANDING),
    ("Arrows", "Arrows (10)", LocationCategory.FREESTANDING),
    ("Arrows", "Arrows (30)", LocationCategory.FREESTANDING),
    ("Bombs", "Bombs (5)", LocationCategory.FREESTANDING),
    ("Nuts", "Deku Nuts (5)", LocationCategory.FREESTANDING),
    ("Freestanding Deku Stick", "Deku Stick (1)", LocationCategory.DROP),
    ("Large Magic Jar", "Large Magic Jar", LocationCategory.FREESTANDING),
    ("Small Magic Jar", "Small Magic Jar", LocationCategory.FREESTANDING),
    ("Seeds", "Deku Seeds (5)", LocationCategory.FREESTANDING),
    ("Freestanding Key", "Small Key", LocationCategory.COLLECTABLE),
    ("Flex Drop", "Flexible", LocationCategory.FREESTANDING),
    ("Gold Rupee", "Rupees (200)", LocationCategory.FREESTANDING),
    ("Purple Rupee", "Rupees (50)", LocationCategory.FREESTANDING),
    ("Deku Shield", "Deku Shield", LocationCategory.FREESTANDING),
    ("Hylian Shield", "Hylian Shield", LocationCategory.FREESTANDING),
    ("Zora Tunic", "Zora Tunic", LocationCategory.FREESTANDING),
    ("Goron Tunic", "Goron Tunic", LocationCategory.FREESTANDING),
    ("Bombs", "Bombs (5)", LocationCategory.FREESTANDING),
]


flying_pot_drops: list[str] = [
    "Recovery Heart",
    "Bombs (5)",
    "Deku Seeds (5)",
    "Deku Nuts (5)",
    "Deku Seeds (5)",
    "Rupees (50)",
    "Goron Tunic",
]


wonderitems: list[str] = [
    "Deku Nuts (5)",
    "Piece of Heart",
    "Large Magic Jar",
    "Small Magic Jar",
    "Recovery Heart",
    "Arrows (5)",
    "Arrows (10)",
    "Deku Seeds (30)",
    "Rupee (1)",
    "Rupees (5)",
    "Rupees (20)",
    "Flexible",
]


def get_item_name_for_region(item_id: int, item_name: str, region_name: str) -> str:
    if item_id == 0x3F or item_id == 0x40 or item_id == 0x41 or item_id == 0x42:
        # Boss key, compass, map, small key
        return f'{item_name} ({region_name})'
    else:
        return item_name


def get_chest_contents_by_id(item_id: int, region_name: str) -> str:
    rando_item_id = item_conversion_table[item_id] if item_id in item_conversion_table else item_id

    for item_name, value in item_table.items():
        if value[2] == rando_item_id:
            return get_item_name_for_region(rando_item_id, item_name, region_name)

    raise RuntimeError(f'Could not find item name for id 0x{item_id:02X}')


def get_chest(actor_variable: int, region_name: str) -> tuple[str, str, LocationCategory]:
    return ('Chest', get_chest_contents_by_id((actor_variable & 0x0FE0) >> 5, region_name), LocationCategory.CHEST)


def get_freestanding(actor_variable: int, region_name: str) -> tuple[str, str, LocationCategory]:
    id = (actor_variable & 0x00FF)

    # Add region_name as needed
    if id == 0x0011:
        (name, vanilla_item, category) = freestandings[id]
        return (name, f"{vanilla_item} ({region_name})", category)

    return freestandings[id]


def get_rupee_tower(actor_variable: int, region_name: str) -> list[tuple[str, str, LocationCategory]]:
    id = (actor_variable & 0xE000) >> 13
    if id == 0x00:
        return [('Blue Rupee', 'Rupees (5)', LocationCategory.RUPEE_TOWER) for i in range(5)]
    elif id == 0x01:
        return [('Green Rupee', 'Rupee (1)', LocationCategory.RUPEE_TOWER) for i in range(5)]
    elif id == 0x02:
        return [('Green Rupee', 'Rupee (1)', LocationCategory.RUPEE_TOWER) for i in range(5)] + [('Red Rupee', 'Rupees (20)', LocationCategory.RUPEE_TOWER)]
    raise RuntimeError(f'Unknown rupee tower type 0x{id:02X}')


def get_shadow_pot_rupees() -> list[tuple[str, str, LocationCategory]]:
    # The third shadow pot drops 3 green, 3 blue, and 3 red rupees
    return [('Green Rupee', 'Rupee (1)', LocationCategory.RUPEE_TOWER), ('Blue Rupee', 'Rupees (5)', LocationCategory.RUPEE_TOWER), ('Red Rupee', 'Rupees (20)', LocationCategory.RUPEE_TOWER)] * 3


def get_scrub(actor_variable: int, region_name: str) -> str:
    return ('Deku Scrub', list(deku_scrubs_items.keys())[actor_variable], LocationCategory.SCRUB)


def get_silver_rupee(actor_variable: int, region_name: str) -> str:
    return ('Silver Rupee', f'Silver Rupee ({region_name})', LocationCategory.SILVER_RUPEE)


def get_cow(actor_variable: int, region_name: str) -> str:
    return ('Cow', 'Milk', LocationCategory.NPC)


def get_gold_skulltula(actor_variable: int, region_name: str) -> str:
    return ('GS', 'Gold Skulltula Token', LocationCategory.GS_TOKEN)


def get_pot(actor_variable: int, region_name: str) -> str:
    id = (actor_variable & 0x00FF)

    # Pot drops nothing
    if id >= 0x3F:
        return ('Pot', None, LocationCategory.POT)

    # TODO.GQ: Why does this happen?
    if id >= len(freestandings):
        return ('Pot', f'TODO 0x{id:02X}', LocationCategory.POT)

    (name, vanilla_item, category) = freestandings[id]
    return ('Pot', vanilla_item, LocationCategory.POT)


def get_flying_pot(actor_variable: int, region_name: str) -> str:
    id = (actor_variable & 0xFF00) >> 8

    if id == 0xFF:
        return ('Flying Pot', None, LocationCategory.FLYING_POT)

    vanilla_item = flying_pot_drops[id]
    return ('Flying Pot', vanilla_item, LocationCategory.FLYING_POT)


def get_crate(actor_variable: int, region_name: str) -> str:
    id = (actor_variable & 0xFF00) >> 8

    if id >= len(freestandings):
        # TODO.GQ: Why does this happen?
        return ('Crate', f'TODO 0x{id:02X}', LocationCategory.CRATE)

    (name, vanilla_item, category) = freestandings[id]
    return ('Crate', vanilla_item, LocationCategory.CRATE)


def get_small_crate(actor_variable: int, region_name: str) -> str:
    id = (actor_variable & 0xFF)

    if id == 0xFF:
        return ('Small Wooden Crate', None, LocationCategory.SMALL_CRATE)

    (name, vanilla_item, category) = freestandings[id]
    return ('Small Wooden Crate', vanilla_item, LocationCategory.SMALL_CRATE)


def get_beehive(actor_variable: int, region_name: str) -> str:
    id = (actor_variable & 0x00FF)
    # TODO.GQ: Update this to be correct
    return ('Beehive', f'TODO 0x{id:02X}', LocationCategory.BEEHIVE)


def get_wonderitem(actor_variable: int, region_name: str) -> str:
    id = ((actor_variable & 0x07C0) >> 6)
    vanilla_item = wonderitems[id]
    return ('Wonderitem', vanilla_item, LocationCategory.WONDERITEM)


def get_location_line(location: str, type: str, scene: int, default: str, addresses: str, vanilla_item: str, categories: str, setup_num: int) -> str:
    contents = f'    ("{location}",'.ljust(69)
    contents += f'("{type}",'.ljust(17)
    contents += f'0x{scene:02X},  {default}, {addresses},'.ljust(42)
    contents += f'\'{vanilla_item}\','.ljust(41)
    contents += f'{categories})),'
    contents += f' # Setup {setup_num}\n' if setup_num > 0 else '\n'
    return contents
