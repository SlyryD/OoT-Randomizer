from __future__ import annotations
from collections.abc import Callable
from typing import Optional, Any

from Rom import Rom

def room_get_actors(rom: Rom, actor_func: Callable[[Rom, int, int, int, int, int, int], Any], room_data: int, scene: int, room_id: int, setup_num: int, alternate: Optional[int] = None) -> dict[int, Any]:
    actors: dict[int, Any] = {}
    room_start: int = alternate if alternate else room_data
    command: int = 0
    while command != 0x14: # 0x14 = end header
        command = rom.read_byte(room_data)
        if command == 0x01: # actor list
            actor_count = rom.read_byte(room_data + 1)
            actor_list = room_start + (rom.read_int32(room_data + 4) & 0x00FFFFFF)
            for actor_num in range(0, actor_count):
                actor_id = rom.read_int16(actor_list)
                entry = actor_func(rom, actor_id, actor_list, scene, room_id, setup_num, actor_num)
                if entry:
                    actors[actor_list] = entry
                actor_list = actor_list + 16
        if command == 0x18: # Alternate header list
            header_list = room_start + (rom.read_int32(room_data + 4) & 0x00FFFFFF)
            for alt_id in range(0,3):
                header_data = room_start + (rom.read_int32(header_list) & 0x00FFFFFF)
                if header_data != 0 and not alternate:
                    actors.update(room_get_actors(rom, actor_func, header_data, scene, room_id, alt_id + 1, room_start))
                header_list = header_list + 4
        room_data = room_data + 8
    return actors


def scene_get_actors(rom: Rom, actor_func: Callable[[Rom, int, int, int, int, int, int], Any], scene_data: int, scene: int, alternate: Optional[int] = None, processed_rooms: Optional[list[int]] = None, setup_num: int = 0) -> dict[int, Any]:
    if processed_rooms is None:
        processed_rooms = []
    actors: dict[int, Any] = {}
    scene_start: int = alternate if alternate else scene_data
    command: int = 0
    while command != 0x14: # 0x14 = end header
        command = rom.read_byte(scene_data)
        if command == 0x04: #room list
            room_count = rom.read_byte(scene_data + 1)
            room_list = scene_start + (rom.read_int32(scene_data + 4) & 0x00FFFFFF)
            for room_id in range(0, room_count):
                room_data = rom.read_int32(room_list)

                if not room_data in processed_rooms:
                    actors.update(room_get_actors(rom, actor_func, room_data, scene, room_id, setup_num))
                    processed_rooms.append(room_data)
                room_list = room_list + 8
        if command == 0x0E: #transition actor list
            actor_count = rom.read_byte(scene_data + 1)
            actor_list = scene_start + (rom.read_int32(scene_data + 4) & 0x00FFFFFF)
            for actor_num in range(0, actor_count):
                actor_id = rom.read_int16(actor_list + 4)
                entry = actor_func(rom, actor_id, actor_list, scene, None, None, actor_num)
                if entry:
                    actors[actor_list] = entry
                actor_list = actor_list + 16
        if command == 0x18: # Alternate header list
            header_list = scene_start + (rom.read_int32(scene_data + 4) & 0x00FFFFFF)
            for alt_id in range(0,3):
                header_data = scene_start + (rom.read_int32(header_list) & 0x00FFFFFF)
                if header_data != 0 and not alternate:
                    actors.update(scene_get_actors(rom, actor_func, header_data, scene, scene_start, processed_rooms, alt_id + 1))
                header_list = header_list + 4

        scene_data = scene_data + 8
    return actors


def get_actor_list(rom: Rom, actor_func: Callable[[Rom, int, int, int], Any]) -> dict[int, Any]:
    actors: dict[int, Any] = {}
    scene_table = 0x00B71440
    for scene in range(0x00, 0x65):
        scene_data = rom.read_int32(scene_table + (scene * 0x14))
        actors.update(scene_get_actors(rom, actor_func, scene_data, scene))
    return actors
