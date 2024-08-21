# In order to patch Gold Quest to the existing data...
#
# Scenes:
#
# Transition actors will be patched over the old data, as the number of records is the same
# Path data will be appended to the end of the scene file.
#
# The size of a single path on file is NUM_POINTS * 6, rounded up to the nearest 4 byte boundary
# The total size consumed by the path data is NUM_PATHS * 8, plus the sum of all path file sizes
# padded to the nearest 0x10 bytes
#
# Collision:
# OoT's collision data consists of these elements: vertices, surface types, water boxes,
# camera behavior data, and polys. GQ's vertex and polygon geometry data is identical.
# However, the surface types and the collision exclusion flags bound to the polys have changed
# for some polygons, as well as the number of surface type records and camera type records.
#
# To patch collision, a flag denotes whether collision data cannot be written in place without
# expanding the size of the scene file. If true, the camera data is relocated to the end
# of the scene file, and the surface types are shifted down into where the camera types
# were situated. If false, the camera data isn't moved, but rather the surface type list
# will be shifted to the end of the camera data
#
# Rooms:
#
# Object file initialization data will be appended to the end of the room file.
# The total size consumed by the object file data is NUM_OBJECTS * 0x02, aligned to
# the nearest 0x04 bytes
#
# Actor spawn data will be appended to the end of the room file, after the objects.
# The total size consumed by the actor spawn data is NUM_ACTORS * 0x10
#
# Finally:
#
# Scene and room files will be padded to the nearest 0x10 bytes

from __future__ import annotations
import json
from typing import Any

from Dungeon import DungeonType
from MQ import Room, Scene
from Rom import Rom
from Utils import data_path
from World import World


def get_gq_scenes(world: World) -> list[int]:
    # patch gq scenes
    gq_scenes: list[int] = []
    if world.dungeon_mq['Deku Tree'] == DungeonType.GQ:
        gq_scenes.append(0)
    if world.dungeon_mq['Dodongos Cavern'] == DungeonType.GQ:
        gq_scenes.append(1)
    if world.dungeon_mq['Jabu Jabus Belly'] == DungeonType.GQ:
        gq_scenes.append(2)
    if world.dungeon_mq['Forest Temple'] == DungeonType.GQ:
        gq_scenes.append(3)
    if world.dungeon_mq['Fire Temple'] == DungeonType.GQ:
        gq_scenes.append(4)
    if world.dungeon_mq['Water Temple'] == DungeonType.GQ:
        gq_scenes.append(5)
    if world.dungeon_mq['Spirit Temple'] == DungeonType.GQ:
        gq_scenes.append(6)
    if world.dungeon_mq['Shadow Temple'] == DungeonType.GQ:
        gq_scenes.append(7)
    if world.dungeon_mq['Bottom of the Well'] == DungeonType.GQ:
        gq_scenes.append(8)
    if world.dungeon_mq['Ice Cavern'] == DungeonType.GQ:
        gq_scenes.append(9)
    if world.dungeon_mq['Ganons Castle'] == DungeonType.GQ:
        gq_scenes.append(10) # Ganons Tower
    if world.dungeon_mq['Gerudo Training Ground'] == DungeonType.GQ:
        gq_scenes.append(11)
    if world.dungeon_mq['Ganons Castle'] == DungeonType.GQ:
        gq_scenes.append(13)
    return gq_scenes


def get_gq_json() -> Any:
    with open(data_path('gqu.json'), 'r') as stream:
        data = json.load(stream)
    return data


# TODO.GQ:
# - Water box in deku vanilla slingshot room not working, stingers missing?
def fix_gq_scene_data(rom: Rom, scene: Scene) -> None:
    if scene.id == 9:
        # patch_ice_cavern_scene_header(rom)
        print(rom, scene)


def fix_gq_room_data(rom: Rom, scene: Scene, room: Room) -> None:
    if scene.id == 6 and room.id == 6:
        # patch_spirit_temple_gq_room_6(rom, room.file.start)
        print(rom, scene, room)
