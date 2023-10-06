# mzxrules 2018
# In order to patch MQ to the existing data...
#
# Scenes:
#
# Ice Cavern (Scene 9) needs to have its header altered to support MQ's path list. This
# expansion will delete the otherwise unused alternate headers command
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
# camera behavior data, and polys. MQ's vertice and polygon geometry data is identical.
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
#
# Maps:
# Jabu Jabu's B1 map contains no chests in the vanilla layout. Because of this,
# the floor map data is missing a vertex pointer that would point within kaleido_scope.
# As such, if the file moves, the patch will break.

from __future__ import annotations
from enum import Enum
import json
from struct import pack, unpack
from typing import Optional, Any

from ProcessActors import get_gold_skulls
from Rom import Rom
from Utils import data_path

SCENE_TABLE: int = 0xB71440


class File:
    def __init__(self, name: str, start: int = 0, end: Optional[int] = None, remap: Optional[int] = None) -> None:
        self.name: str = name
        self.start: int = start
        self.end: int = end if end is not None else self.start
        self.remap: Optional[int] = remap
        self.from_file: int = self.start

        # used to update the file's associated dmadata record
        self.dma_key: int = self.start

    @classmethod
    def from_json(cls, file: dict[str, Optional[str]]) -> File:
        return cls(
            file['Name'],
            int(file['Start'], 16) if file.get(
                'Start', None) is not None else 0,
            int(file['End'], 16) if file.get(
                'End', None) is not None else None,
            int(file['RemapStart'], 16) if file.get(
                'RemapStart', None) is not None else None
        )

    def __repr__(self) -> str:
        remap = "None"
        if self.remap is not None:
            remap = "{0:x}".format(self.remap)
        return "{0}: {1:x} {2:x}, remap {3}".format(self.name, self.start, self.end, remap)

    def relocate(self, rom: Rom) -> None:
        if self.remap is None:
            self.remap = rom.dma.free_space()

        new_start = self.remap

        offset = new_start - self.start
        new_end = self.end + offset

        rom.buffer[new_start:new_end] = rom.buffer[self.start:self.end]
        self.start = new_start
        self.end = new_end
        update_dmadata(rom, self)

    # The file will now refer to the new copy of the file
    def copy(self, rom: Rom) -> None:
        self.dma_key = None
        self.relocate(rom)


class CollisionMesh:
    def __init__(self, rom: Rom, start: int, offset: int) -> None:
        self.offset = offset
        self.poly_addr = rom.read_int32(start + offset + 0x18)
        self.polytypes_addr = rom.read_int32(start + offset + 0x1C)
        self.camera_data_addr = rom.read_int32(start + offset + 0x20)
        self.polytypes = (self.poly_addr - self.polytypes_addr) // 8

    def write_to_scene(self, rom: Rom, start: int) -> None:
        addr = start + self.offset + 0x18
        rom.write_int32s(
            addr, [self.poly_addr, self.polytypes_addr, self.camera_data_addr])


class ColDelta:
    def __init__(self, delta: dict[str, bool | list[dict[str, int]]]) -> None:
        self.is_larger: bool = delta['IsLarger']
        self.polys: list[dict[str, int]] = delta['Polys']
        self.polytypes: list[dict[str, int]] = delta['PolyTypes']
        self.cams: list[dict[str, int]] = delta['Cams']


class Icon:
    def __init__(self, data: dict[str, int | list[dict[str, int]]]) -> None:
        self.icon: int = data["Icon"]
        self.count: int = data["Count"]
        self.points: list[IconPoint] = [
            IconPoint(x) for x in data["IconPoints"]]

    def write_to_minimap(self, rom: Rom, addr: int) -> None:
        rom.write_sbyte(addr, self.icon)
        rom.write_byte(addr + 1,  self.count)
        cur = 2
        for p in self.points:
            p.write_to_minimap(rom, addr + cur)
            cur += 0x03

    def write_to_floormap(self, rom: Rom, addr: int) -> None:
        rom.write_int16(addr, self.icon)
        rom.write_int32(addr + 0x10, self.count)

        cur = 0x14
        for p in self.points:
            p.write_to_floormap(rom, addr + cur)
            cur += 0x0C


class IconPoint:
    def __init__(self, point: dict[str, int]) -> None:
        self.flag = point["Flag"]
        self.x = point["x"]
        self.y = point["y"]

    def write_to_minimap(self, rom: Rom, addr: int) -> None:
        rom.write_sbyte(addr, self.flag)
        rom.write_byte(addr+1, self.x)
        rom.write_byte(addr+2, self.y)

    def write_to_floormap(self, rom: Rom, addr: int) -> None:
        rom.write_int16(addr, self.flag)
        rom.write_f32(addr + 4, float(self.x))
        rom.write_f32(addr + 8, float(self.y))


class Scene:
    def __init__(self, scene: dict[str, Any]) -> None:
        self.file: File = File.from_json(scene['File'])
        self.id: int = scene['Id']
        self.transition_actors: list[list[int]] = [
            convert_actor_data(x) for x in scene['TActors']]
        self.rooms: list[Room] = [Room(x) for x in scene['Rooms']]
        self.paths: list[list[list[int]]] = []
        self.coldelta: ColDelta = ColDelta(scene["ColDelta"])
        self.minimaps: list[list[Icon]] = [
            [Icon(icon) for icon in minimap['Icons']] for minimap in scene['Minimaps']]
        self.floormaps: list[list[Icon]] = [
            [Icon(icon) for icon in floormap['Icons']] for floormap in scene['Floormaps']]
        temp_paths = scene['Paths']
        for item in temp_paths:
            self.paths.append(item['Points'])

    def write_data(self, rom: Rom) -> None:
        # write floormap and minimap data
        self.write_map_data(rom)

        # move file to remap address
        if self.file.remap is not None:
            self.file.relocate(rom)

        start = self.file.start
        headcur = self.file.start

        room_list_offset = 0

        code = rom.read_byte(headcur)
        loop = 0x20
        while loop > 0 and code != 0x14:  # terminator
            loop -= 1

            if code == 0x03:  # collision
                col_mesh_offset = rom.read_int24(headcur + 5)
                col_mesh = CollisionMesh(rom, start, col_mesh_offset)
                self.patch_mesh(rom, col_mesh)

            elif code == 0x04:  # rooms
                room_list_offset = rom.read_int24(headcur + 5)

            elif code == 0x0D:  # paths
                path_offset = self.append_path_data(rom)
                rom.write_int32(headcur + 4, path_offset)

            elif code == 0x0E:  # transition actors
                t_offset = rom.read_int24(headcur + 5)
                addr = self.file.start + t_offset
                write_actor_data(rom, addr, self.transition_actors)

            headcur += 8
            code = rom.read_byte(headcur)

        # update file references
        self.file.end = align16(self.file.end)
        update_dmadata(rom, self.file)
        update_scene_table(rom, self.id, self.file.start, self.file.end)

        # write room file data
        for room in self.rooms:
            room.write_data(rom)
            if self.id == 6 and room.id == 6:
                patch_spirit_temple_mq_room_6(rom, room.file.start)

        cur = self.file.start + room_list_offset
        for room in self.rooms:
            rom.write_int32s(cur, [room.file.start, room.file.end])
            cur += 0x08

    def write_map_data(self, rom: Rom) -> None:
        if self.id >= 10:
            return

        # write floormap
        floormap_indices = 0xB6C934
        floormap_vrom = 0xBC7E00
        floormap_index = rom.read_int16(floormap_indices + (self.id * 2))
        floormap_index //= 2  # game uses texture index, where two textures are used per floor

        cur = floormap_vrom + (floormap_index * 0x1EC)
        for floormap in self.floormaps:
            for icon in floormap:
                Icon.write_to_floormap(icon, rom, cur)
                cur += 0xA4

        # fixes jabu jabu floor B1 having no chest data
        if self.id == 2:
            cur = floormap_vrom + (0x08 * 0x1EC + 4)
            kaleido_scope_chest_verts = 0x803A3DA0  # hax, should be vram 0x8082EA00
            rom.write_int32s(cur, [0x17, kaleido_scope_chest_verts, 0x04])

        # write minimaps
        map_mark_vrom = 0xBF40D0
        map_mark_vram = 0x808567F0
        map_mark_array_vram = 0x8085D2DC  # ptr array in map_mark_data to minimap "marks"

        array_vrom = map_mark_array_vram - map_mark_vram + map_mark_vrom
        map_mark_scene_vram = rom.read_int32(self.id * 4 + array_vrom)
        mark_vrom = map_mark_scene_vram - map_mark_vram + map_mark_vrom

        cur = mark_vrom
        for minimap in self.minimaps:
            for icon in minimap:
                Icon.write_to_minimap(icon, rom, cur)
                cur += 0x26

    def patch_mesh(self, rom: Rom, mesh: CollisionMesh) -> None:
        start = self.file.start

        final_cams = []

        # build final camera data
        for cam in self.coldelta.cams:
            data = cam['Data']
            pos = cam['PositionIndex']
            if pos < 0:
                final_cams.append((data, 0))
            else:
                addr = start + (mesh.camera_data_addr & 0xFFFFFF)
                seg_off = rom.read_int32(addr + (pos * 8) + 4)
                final_cams.append((data, seg_off))

        types_move_addr = 0

        # if data can't fit within the old mesh space, append camera data
        if self.coldelta.is_larger:
            types_move_addr = mesh.camera_data_addr

            # append to end of file
            self.write_cam_data(rom, self.file.end, final_cams)
            mesh.camera_data_addr = get_segment_address(
                2, self.file.end - self.file.start)
            self.file.end += len(final_cams) * 8

        else:
            types_move_addr = mesh.camera_data_addr + (len(final_cams) * 8)

            # append in place
            addr = self.file.start + (mesh.camera_data_addr & 0xFFFFFF)
            self.write_cam_data(rom, addr, final_cams)

        # if polytypes needs to be moved, do so
        if types_move_addr != mesh.polytypes_addr:
            a_start = self.file.start + (mesh.polytypes_addr & 0xFFFFFF)
            b_start = self.file.start + (types_move_addr & 0xFFFFFF)
            size = mesh.polytypes * 8

            rom.buffer[b_start:b_start +
                       size] = rom.buffer[a_start:a_start + size]
            mesh.polytypes_addr = types_move_addr

        # patch polytypes
        for item in self.coldelta.polytypes:
            id = item['Id']
            high = item['High']
            low = item['Low']
            addr = self.file.start + \
                (mesh.polytypes_addr & 0xFFFFFF) + (id * 8)
            rom.write_int32s(addr, [high, low])

        # patch poly data
        for item in self.coldelta.polys:
            id = item['Id']
            t = item['Type']
            flags = item['Flags']

            addr = self.file.start + (mesh.poly_addr & 0xFFFFFF) + (id * 0x10)
            vert_bit = rom.read_byte(addr + 0x02) & 0x1F  # VertexA id data
            rom.write_int16(addr, t)
            rom.write_byte(addr + 0x02, (flags << 5) + vert_bit)

        # Write Mesh to Scene
        mesh.write_to_scene(rom, self.file.start)

    @staticmethod
    def write_cam_data(rom: Rom, addr: int, cam_data: list[tuple[int, int]]) -> None:
        for item in cam_data:
            data, pos = item
            rom.write_int32s(addr, [data, pos])
            addr += 8

    # appends path data to the end of the rom
    # returns segment address to path data
    def append_path_data(self, rom: Rom) -> int:
        start = self.file.start
        cur = self.file.end
        records = []

        for path in self.paths:
            nodes = len(path)
            offset = get_segment_address(2, cur - start)
            records.append((nodes, offset))

            # flatten
            points = [x for points in path for x in points]
            rom.write_int16s(cur, points)
            path_size = align4(len(path) * 6)
            cur += path_size

        records_offset = get_segment_address(2, cur - start)
        for node, offset in records:
            rom.write_byte(cur, node)
            rom.write_int32(cur + 4, offset)
            cur += 8

        self.file.end = cur
        return records_offset


class Room:
    def __init__(self, room: dict[str, int | list[str] | dict[str, Optional[str]]]):
        self.file: File = File.from_json(room['File'])
        self.id: int = room['Id']
        self.objects: list[int] = [int(x, 16) for x in room['Objects']]
        self.actors: list[list[int]] = [
            convert_actor_data(x) for x in room['Actors']]

    def write_data(self, rom: Rom) -> None:
        # move file to remap address
        if self.file.remap is not None:
            self.file.relocate(rom)

        headcur = self.file.start

        code = rom.read_byte(headcur)
        loop = 0x20

        while loop != 0 and code != 0x14:  # terminator
            loop -= 1

            if code == 0x01:  # actors
                offset = self.file.end - self.file.start
                write_actor_data(rom, self.file.end, self.actors)
                self.file.end += len(self.actors) * 0x10

                rom.write_byte(headcur + 1, len(self.actors))
                rom.write_int32(headcur + 4, get_segment_address(3, offset))

            elif code == 0x0B:  # objects
                offset = self.append_object_data(rom, self.objects)

                rom.write_byte(headcur + 1, len(self.objects))
                rom.write_int32(headcur + 4, get_segment_address(3, offset))

            headcur += 8
            code = rom.read_byte(headcur)

        # update file reference
        self.file.end = align16(self.file.end)
        update_dmadata(rom, self.file)

    def append_object_data(self, rom: Rom, objects: list[int]) -> int:
        offset = self.file.end - self.file.start
        cur = self.file.end
        rom.write_int16s(cur, objects)

        objects_size = align4(len(objects) * 2)
        self.file.end += objects_size
        return offset


def patch_files(rom: Rom, mq_scenes: list[int]) -> None:
    data = get_json()
    scenes = [Scene(x) for x in data]
    for scene in scenes:
        if scene.id in mq_scenes:
            if scene.id == 9:
                patch_ice_cavern_scene_header(rom)
            scene.write_data(rom)


def get_json() -> Any:
    with open(data_path('mqu.json'), 'r') as stream:
        data = json.load(stream)
    return data


def convert_actor_data(string: str) -> list[int]:
    spawn_args = string.split(" ")
    return [int(x, 16) for x in spawn_args]


def get_segment_address(base: int, offset: int) -> int:
    offset &= 0xFFFFFF
    base *= 0x01000000
    return base + offset


def patch_ice_cavern_scene_header(rom: Rom) -> None:
    rom.buffer[0x2BEB000:0x2BEB038] = rom.buffer[0x2BEB008:0x2BEB040]
    rom.write_int32s(0x2BEB038, [0x0D000000, 0x02000000])


def patch_spirit_temple_mq_room_6(rom: Rom, room_addr: int) -> None:
    cur = room_addr

    actor_list_addr = 0
    cmd_actors_offset = 0

    # scan for actor list and header end
    code = rom.read_byte(cur)
    while code != 0x14:  # terminator
        if code == 0x01:  # actors
            actor_list_addr = rom.read_int32(cur + 4)
            cmd_actors_offset = cur - room_addr

        cur += 8
        code = rom.read_byte(cur)

    cur += 8

    # original header size
    header_size = cur - room_addr

    # set alternate header data location
    alt_data_off = header_size + 8

    # set new alternate header offset
    # alt header record size * num records
    alt_header_off = align16(alt_data_off + (4 * 3))

    # write alternate header data
    # the first 3 words are mandatory. the last 3 are just to make the binary
    # cleaner to read
    rom.write_int32s(room_addr + alt_data_off,
                     [0, get_segment_address(3, alt_header_off), 0, 0, 0, 0])

    # clone header
    a_start = room_addr
    a_end = a_start + header_size
    b_start = room_addr + alt_header_off
    b_end = b_start + header_size

    rom.buffer[b_start:b_end] = rom.buffer[a_start:a_end]

    # make the child header skip the first actor,
    # which avoids the spawning of the block while in the hole
    cmd_addr = room_addr + cmd_actors_offset
    actor_list_addr += 0x10
    actors = rom.read_byte(cmd_addr + 1)
    rom.write_byte(cmd_addr+1, actors - 1)
    rom.write_int32(cmd_addr + 4, actor_list_addr)

    # move header
    rom.buffer[a_start + 8:a_end + 8] = rom.buffer[a_start:a_end]

    # write alternate header command
    seg = get_segment_address(3, alt_data_off)
    rom.write_int32s(room_addr, [0x18000000, seg])


def verify_remap(scenes: list[Scene]) -> None:
    def test_remap(file: File) -> bool:
        if file.remap is not None:
            if file.start < file.remap:
                return False
        return True
    print("test code: verify remap won't corrupt data")

    for scene in scenes:
        file = scene.file
        result = test_remap(file)
        print("{0} - {1}".format(result, file))

        for room in scene.rooms:
            file = room.file
            result = test_remap(file)
            print("{0} - {1}".format(result, file))


def update_dmadata(rom: Rom, file: File) -> None:
    key, start, end, from_file = file.dma_key, file.start, file.end, file.from_file
    rom.update_dmadata_record_by_key(key, start, end, from_file)
    file.dma_key = file.start


def update_scene_table(rom: Rom, scene_id: int, start: int, end: int) -> None:
    cur = scene_id * 0x14 + SCENE_TABLE
    rom.write_int32s(cur, [start, end])


def write_actor_data(rom: Rom, cur: int, actors: list[list[int]]) -> None:
    for actor in actors:
        rom.write_int16s(cur, actor)
        cur += 0x10


def align4(value: int) -> int:
    return ((value + 3) // 4) * 4


def align16(value: int) -> int:
    return ((value + 0xF) // 0x10) * 0x10


# This function inserts space in a ovl section at the section's offset
# The section size is expanded
# Every relocation entry in the section after the offset is moved accordingly
# Every relocation value that is after the inserted space is increased accordingly
def insert_space(rom: Rom, file: File, vram_start: int, insert_section: int, insert_offset: int, insert_size: int) -> None:
    sections = []
    val_hi = {}
    adr_hi = {}

    # get the ovl header
    cur = file.end - rom.read_int32(file.end - 4)
    section_total = 0
    for i in range(0, 4):
        # build the section offsets
        section_size = rom.read_int32(cur)
        sections.append(section_total)
        section_total += section_size

        # increase the section to be expanded
        if insert_section == i:
            rom.write_int32(cur, section_size + insert_size)

        cur += 4

    # calculate the insert address in vram
    insert_vram = sections[insert_section] + insert_offset + vram_start
    insert_rom = sections[insert_section] + insert_offset + file.start

    # iterate over the relocation table
    relocate_count = rom.read_int32(cur)
    cur += 4
    for i in range(0, relocate_count):
        entry = rom.read_int32(cur)

        # parse relocation entry
        section = ((entry & 0xC0000000) >> 30) - 1
        type = (entry & 0x3F000000) >> 24
        offset = entry & 0x00FFFFFF

        # calculate relocation address in rom
        address = file.start + sections[section] + offset

        # move relocation if section is increased and it's after the insert
        if insert_section == section and offset >= insert_offset:
            # rebuild new relocation entry
            rom.write_int32(cur,
                            ((section + 1) << 30) |
                            (type << 24) |
                            (offset + insert_size))

        # value contains the vram address
        value = rom.read_int32(address)
        reg = None
        if type == 2:
            # Data entry: value is the raw vram address
            pass
        elif type == 4:
            # Jump OP: Get the address from a Jump instruction
            value = 0x80000000 | (value & 0x03FFFFFF) << 2
        elif type == 5:
            # Load High: Upper half of an address load
            reg = (value >> 16) & 0x1F
            val_hi[reg] = (value & 0x0000FFFF) << 16
            adr_hi[reg] = address
            # Do not process, wait until the lower half is read
            value = None
        elif type == 6:
            # Load Low: Lower half of the address load
            reg = (value >> 21) & 0x1F
            val_low = value & 0x0000FFFF
            val_low = unpack('h', pack('H', val_low))[0]
            # combine with previous load high
            value = val_hi[reg] + val_low
        else:
            # unknown. OoT does not use any other types
            value = None

        # update the vram values if it's been moved
        if value is not None and value >= insert_vram:
            # value = new vram address
            new_value = value + insert_size

            if type == 2:
                # Data entry: value is the raw vram address
                rom.write_int32(address, new_value)
            elif type == 4:
                # Jump OP: Set the address in the Jump instruction
                op = rom.read_int32(address) & 0xFC000000
                new_value = (new_value & 0x0FFFFFFC) >> 2
                new_value = op | new_value
                rom.write_int32(address, new_value)
            elif type == 6:
                # Load Low: Lower half of the address load
                op = rom.read_int32(address) & 0xFFFF0000
                new_val_low = new_value & 0x0000FFFF
                rom.write_int32(address, op | new_val_low)

                # Load High: Upper half of an address load
                op = rom.read_int32(adr_hi[reg]) & 0xFFFF0000
                new_val_hi = (new_value & 0xFFFF0000) >> 16
                if new_val_low >= 0x8000:
                    # add 1 if the lower part is negative for borrow
                    new_val_hi += 1
                rom.write_int32(adr_hi[reg], op | new_val_hi)

        cur += 4

    # Move rom bytes
    rom.buffer[(insert_rom + insert_size):(file.end + insert_size)
               ] = rom.buffer[insert_rom:file.end]
    rom.buffer[insert_rom:(insert_rom + insert_size)] = [0] * insert_size
    file.end += insert_size


def add_relocations(rom: Rom, file: File, addresses: list[int | tuple[int, int]]) -> None:
    relocations = []
    sections = []
    header_size = rom.read_int32(file.end - 4)
    header = file.end - header_size
    cur = header

    # read section sizes and build offsets
    section_total = 0
    for i in range(0, 4):
        section_size = rom.read_int32(cur)
        sections.append(section_total)
        section_total += section_size
        cur += 4

    # get all entries in relocation table
    relocate_count = rom.read_int32(cur)
    cur += 4
    for i in range(0, relocate_count):
        relocations.append(rom.read_int32(cur))
        cur += 4

    # create new enties
    for address in addresses:
        if isinstance(address, tuple):
            # if type provided use it
            type, address = address
        else:
            # Otherwise, try to infer type from value
            value = rom.read_int32(address)
            op = value >> 26
            type = 2  # default: data
            if op == 0x02 or op == 0x03:  # j or jal
                type = 4
            elif op == 0x0F:  # lui
                type = 5
            elif op == 0x08:  # addi
                type = 6

        # Calculate section and offset
        address = address - file.start
        section = 0
        for section_start in sections:
            if address >= section_start:
                section += 1
            else:
                break
        offset = address - sections[section - 1]

        # generate relocation entry
        relocations.append((section << 30)
                           | (type << 24)
                           | (offset & 0x00FFFFFF))

    # Rebuild Relocation Table
    cur = header + 0x10
    relocations.sort(key=lambda val: val & 0xC0FFFFFF)
    rom.write_int32(cur, len(relocations))
    cur += 4
    for relocation in relocations:
        rom.write_int32(cur, relocation)
        cur += 4

    # Add padded 0?
    rom.write_int32(cur, 0)
    cur += 4

    # Update Header and File size
    new_header_size = (cur + 4) - header
    rom.write_int32(cur, new_header_size)
    file.end += (new_header_size - header_size)


class RecordType(str, Enum):
    # Scene header record types
    SceneHeader = 'SceneHeader'
    AlternateHeaders = 'AlternateHeaders'
    RoomList = 'RoomList'
    TransitionActorList = 'TransitionActorList'
    CollisionHeader = 'CollisionHeader'
    EntranceList = 'EntranceList'
    Points = 'Points'
    PathList = 'PathList'
    SpawnList = 'SpawnList'
    ExitList = 'ExitList'
    LightSettings = 'LightSettings'
    CutsceneData = 'CutsceneData'

    # Collision header record types
    Vertices = 'Vertices'
    Polys = 'Polys'
    Polytypes = 'Polytypes'
    Cams = 'Cams'
    Waterboxes = 'Waterboxes'

    # Room header record types
    RoomMesh = 'RoomMesh'
    ObjectList = 'ObjectList'
    ActorList = 'ActorList'

    # Data at the end of the file not referenced by a header
    Unreferenced = 'Unreferenced'


class DataRecord:
    def __init__(self, rom: Rom, type: RecordType, start: int, offset: int, length: int) -> None:
        self.rom: Rom = rom
        self.type: RecordType = type
        self.start: int = start
        self.offset: int = offset
        self.length: int = length

        self.data: bytearray = self.rom.read_bytes(start + offset, length)

    def to_json(self) -> dict[str, Any]:
        return {
            'type': self.type.value,
            'start_offset': f'0x{self.offset:08X}',
            'end_offset': f'0x{self.offset + self.length:08X}'
        }


class PointerRecord:
    def __init__(self, rom: Rom, type: RecordType, start: int, offset: int, record: DataRecord) -> None:
        self.rom: Rom = rom
        self.type: RecordType = type
        self.start: int = start
        self.offset: int = offset
        self.record: DataRecord = record

    def to_json(self) -> dict[str, Any]:
        return {
            'type': self.type.value,
            'offset': f'0x{self.offset:08X}',
            'record': self.record.to_json()
        }


class SceneDataRelocator:
    def __init__(self, rom: Rom, name: str, start: int, end: int) -> None:
        self.rom: Rom = rom
        self.name: str = name
        self.start: int = start
        self.end: int = end

        self.data_records: list[DataRecord] = []
        self.pointer_records: list[PointerRecord] = []
        self.rooms: list[RoomDataRelocator] = []

        # Parse scene header
        header_length = self.parse_scene_header()
        self.data_records.append(DataRecord(
            self.rom, RecordType.SceneHeader, self.start, 0, header_length))

        # Sort records by offset
        self.sort_records()

        # Add unreferenced data record from last referenced data record to end of file
        self.add_unreferenced_record()

        # Fix missing lengths
        self.fix_missing_lengths()

    def parse_scene_header(self, alternate: Optional[int] = None) -> int:
        scene_start: int = alternate if alternate else self.start
        scene_cursor: int = scene_start
        alternate_headers: list[int] = []
        room_list: list[tuple[int, int]] = []
        collision_header: int = 0
        while True:
            command = self.rom.read_byte(scene_cursor)
            count = self.rom.read_byte(scene_cursor + 1)
            offset = self.rom.read_int24(scene_cursor + 5)
            if command == 0x18:  # AlternateHeaders
                alternate_headers = self.get_alternate_headers(offset)
                record_type = RecordType.AlternateHeaders
                length = len(alternate_headers) * 4
            elif command == 0x04:  # RoomList
                room_list = self.get_room_list(offset, count)
                record_type = RecordType.RoomList
                length = len(room_list) * 8
            elif command == 0x0E:  # TransitionActorList
                record_type = RecordType.TransitionActorList
                length = count * 16
            elif command == 0x03:  # CollisionHeader
                # TODO.Sly: Dedupe data records like this one
                # TODO.Sly: What to do about unreferenced data in the middle of the file?
                collision_header = offset
                record_type = RecordType.CollisionHeader
                length = 0x2C
            elif command == 0x06:  # EntranceList
                record_type = RecordType.EntranceList
                length = -1
            elif command == 0x0D:  # PathList
                path_list = self.get_path_list(offset)
                self.iterate_path_list(path_list)
                record_type = RecordType.PathList
                length = len(path_list) * 8
            elif command == 0x00:  # SpawnList
                record_type = RecordType.SpawnList
                length = count * 16
            elif command == 0x13:  # ExitList
                record_type = RecordType.ExitList
                length = -1
            elif command == 0x0F:  # LightSettings
                record_type = RecordType.LightSettings
                length = -1
            elif command == 0x17:  # CutsceneData
                record_type = RecordType.CutsceneData
                length = -1
            elif command == 0x14:  # Terminator
                scene_cursor += 8
                break
            else:  # Commands without pointers to data
                scene_cursor += 8
                continue
            self.add_records(record_type, offset, length, scene_cursor)
            scene_cursor += 8
        # Assume collision header and room list are the same for all headers
        # Iterate alternate headers just for the main scene header
        if alternate is None:
            self.parse_collision_header(collision_header)
            self.iterate_alternate_headers(alternate_headers)
            self.iterate_room_list(room_list)
        # Return scene header length
        return scene_cursor - scene_start

    def add_records(self, record_type: RecordType, offset: int, length: int, cursor: int) -> None:
        data_record = DataRecord(
            self.rom, record_type, self.start, offset, length)
        self.data_records.append(data_record)
        pointer_record = PointerRecord(
            self.rom, record_type, self.start, cursor - self.start, data_record)
        self.pointer_records.append(pointer_record)

    def get_alternate_headers(self, offset: int) -> list[tuple[int, int]]:
        alternate_headers = []
        alternate_cursor = self.start + offset
        while True:
            segment = self.rom.read_byte(alternate_cursor)
            header_offset = self.rom.read_int24(alternate_cursor + 1)
            if segment != 0x02 and header_offset != 0:
                break
            alternate_headers.append((alternate_cursor, header_offset))
            alternate_cursor += 4
        return alternate_headers

    def get_room_list(self, offset: int, count: int) -> list[tuple[int, int]]:
        room_list = []
        for i in range(count):
            room_start = self.rom.read_int32(self.start + offset + (i * 8))
            room_end = self.rom.read_int32(self.start + offset + (i * 8) + 4)
            room_list.append((room_start, room_end))
        return room_list

    def get_path_list(self, offset: int) -> list[tuple[int, int, int]]:
        path_list = []
        path_cursor = self.start + offset
        while True:
            points_count = self.rom.read_byte(path_cursor)
            segment = self.rom.read_byte(path_cursor + 4)
            points_offset = self.rom.read_int24(path_cursor + 5)
            if points_count == 0 or segment != 0x02 or points_offset == 0:
                break
            path_list.append((path_cursor, points_offset, points_count))
            path_cursor += 8
        return path_list

    def iterate_alternate_headers(self, alternate_headers: list[int]) -> None:
        for (alternate_cursor, header_offset) in alternate_headers:
            if header_offset != 0:
                header_start = self.start + header_offset
                header_length = self.parse_scene_header(header_start)
                self.add_records(RecordType.SceneHeader,
                                 header_offset, header_length, alternate_cursor)

    def iterate_room_list(self, room_list: list[tuple[int, int]]) -> None:
        for (i, (room_start, room_end)) in enumerate(room_list):
            self.rooms.append(RoomDataRelocator(
                self.rom, f'{self.name}, Room {i}', room_start, room_end))

    def iterate_path_list(self, path_list: list[tuple[int, int, int]]) -> None:
        for (path_cursor, points_offset, points_count) in path_list:
            points_length = align4(points_count * 6)
            self.add_records(RecordType.Points, points_offset,
                             points_length, path_cursor)

    def parse_collision_header(self, offset: int) -> None:
        # Vertices
        collision_cursor = self.start + offset + 0x0C
        vertices_count = self.rom.read_int16(collision_cursor)
        vertices_offset = self.rom.read_int24(collision_cursor + 5)
        vertices_length = align4(vertices_count * 6)
        self.add_records(RecordType.Vertices, vertices_offset,
                         vertices_length, collision_cursor)
        # Polys
        collision_cursor = self.start + offset + 0x14
        polys_count = self.rom.read_int16(collision_cursor)
        polys_offset = self.rom.read_int24(collision_cursor + 5)
        polys_length = polys_count * 16
        self.add_records(RecordType.Polys, polys_offset,
                         polys_length, collision_cursor)
        # Polytypes
        collision_cursor = self.start + offset + 0x1C
        polytypes_offset = self.rom.read_int24(collision_cursor + 1)
        polytypes_length = -1
        self.add_records(RecordType.Polytypes, polytypes_offset,
                         polytypes_length, collision_cursor)
        # Cams
        collision_cursor = self.start + offset + 0x20
        cams_offset = self.rom.read_int24(collision_cursor + 1)
        cams_length = -1
        if cams_offset != 0:
            self.add_records(RecordType.Cams, cams_offset,
                             cams_length, collision_cursor)
        # Waterboxes
        collision_cursor = self.start + offset + 0x24
        waterboxes_count = self.rom.read_int16(collision_cursor)
        waterboxes_offset = self.rom.read_int24(collision_cursor + 5)
        waterboxes_length = waterboxes_count * 16
        if waterboxes_count != 0 and waterboxes_offset != 0:
            self.add_records(RecordType.Waterboxes, waterboxes_offset,
                             waterboxes_length, collision_cursor)

    def sort_records(self) -> None:
        self.data_records.sort(key=lambda x: x.offset)
        self.pointer_records.sort(key=lambda x: x.offset)

    def add_unreferenced_record(self) -> None:
        last_record = self.data_records[-1]
        if last_record.length == -1:
            # Cannot determine length of last record
            data_record = DataRecord(self.rom, RecordType.Unreferenced,
                                     self.start, last_record.offset, self.end - last_record.offset)
            self.data_records.pop()
            self.data_records.append(data_record)
        else:
            data_record = DataRecord(self.rom, RecordType.Unreferenced, self.start, last_record.offset +
                                     last_record.length, self.end - (last_record.offset + last_record.length))
            self.data_records.append(data_record)

    def fix_missing_lengths(self) -> None:
        # Iterate data records in reverse in case we have multiple missing lengths in a row
        index: int = len(self.data_records) - 1
        if self.data_records[index].type != RecordType.Unreferenced:
            raise Exception(
                "Expected unreferenced record at the end of the scene file")
        if self.data_records[index].length == -1:
            raise Exception("Cannot determine length of last record")
        index -= 1
        while index >= 0:
            record = self.data_records[index]
            next_record = self.data_records[index + 1]
            if record.length == -1:
                record.length = next_record.offset - record.offset
            index -= 1

    def to_json(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'start': f'{self.start:08X}',
            'end': f'{self.end:08X}',
            'data_records': [x.to_json() for x in self.data_records],
            'pointer_records': [x.to_json() for x in self.pointer_records],
            'rooms': [x.to_json() for x in self.rooms]
        }


class RoomDataRelocator:
    def __init__(self, rom: Rom, name: int, start: int, end: int, alternate: Optional[int] = None) -> None:
        self.name: int = name
        self.start: int = start
        self.end: int = end
        self.alternate: int = alternate if alternate is not None else 0

        self.data_records: list[DataRecord] = []
        self.pointer_records: list[PointerRecord] = []

        self.add_room_header_records()

    def add_room_header_records(self) -> None:
        print(f"Adding room header data_records for {self.name}")

    def to_json(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'start': self.start,
            'end': self.end,
            'alternate': self.alternate,
            'data_records': [x.to_json() for x in self.data_records],
            'pointer_records': [x.to_json() for x in self.pointer_records]
        }


def fully_mix_skulls(rom: Rom):
    gold_skulls = get_gold_skulls(rom)
    for (offset, (scene_num, room_num, setup_num, actor_num, scene_name, gold_skull)) in gold_skulls.items():
        # print(f"Scene {scene_num}, Room {room_num}, Setup {setup_num}, {scene_name}")
        item_id = gold_skull['item_id']
        if item_id == 'Night Gold Skulltula':
            variable = int(gold_skull['variable'], 16)
            updated_variable = 0x8000 | (variable & 0x1FFF)
            rom.write_int16(offset + 14, updated_variable)


# rom = Rom("ZOOTDEC.z64")
# fully_mix_skulls(rom)
rom = Rom("zeloot_mqdebug.z64")
scene_data_relocator = SceneDataRelocator(
    rom, 'spot00_scene', 0x01FB8000, 0x01FE2220)
# rom, 'ddan_scene', 0x01F12000, 0x01F27140)
with open('scene_data_relocator.json', 'w') as outfile:
    json.dump(scene_data_relocator, outfile,
              default=lambda x: x.to_json(), indent=4)

# rooms: list[tuple[int, int, int, str]] = [
#     (0x01F28000, 0x01F438A0, 0x01B8A0, 'ddan_room_0'),
#     (0x01F44000, 0x01F4DB00, 0x009B00, 'ddan_room_1'),
#     (0x01F4E000, 0x01F55DA0, 0x007DA0, 'ddan_room_2'),
#     (0x01F56000, 0x01F63DC0, 0x00DDC0, 'ddan_room_3'),
#     (0x01F64000, 0x01F6D850, 0x009850, 'ddan_room_4'),
#     (0x01F6E000, 0x01F73EE0, 0x005EE0, 'ddan_room_5'),
#     (0x01F74000, 0x01F76400, 0x002400, 'ddan_room_6'),
#     (0x01F77000, 0x01F7E6D0, 0x0076D0, 'ddan_room_7'),
#     (0x01F7F000, 0x01F88400, 0x009400, 'ddan_room_8'),
#     (0x01F89000, 0x01F94550, 0x00B550, 'ddan_room_9'),
#     (0x01F95000, 0x01F9CE50, 0x007E50, 'ddan_room_10'),
#     (0x01F9D000, 0x01F9F080, 0x002080, 'ddan_room_11'),
#     (0x01FA0000, 0x01FA8730, 0x008730, 'ddan_room_12'),
#     (0x01FA9000, 0x01FAB480, 0x002480, 'ddan_room_13'),
#     (0x01FAC000, 0x01FAE490, 0x002490, 'ddan_room_14'),
#     (0x01FAF000, 0x01FB1850, 0x002850, 'ddan_room_15'),
#     (0x01FB2000, 0x01FB7550, 0x005550, 'ddan_room_16'),
#     (0x01FE3000, 0x01FF8230, 0x015230, 'spot00_room_0'),
#     (0x02016000, 0x0201FF20, 0x009F20, 'spot01_room_0'),
#     (0x0202C000, 0x0202E660, 0x002660, 'spot02_room_0'),
#     (0x0202F000, 0x0204CE60, 0x01DE60, 'spot02_room_1'),
#     (0x02059000, 0x02066980, 0x00D980, 'spot03_room_0'),
#     (0x02067000, 0x0206E500, 0x007500, 'spot03_room_1'),
#     (0x02081000, 0x0209C380, 0x01B380, 'spot04_room_0'),
#     (0x0209D000, 0x020A5560, 0x008560, 'spot04_room_1'),
#     (0x020A6000, 0x020AB010, 0x005010, 'spot04_room_2'),
#     (0x020C1000, 0x020CAF00, 0x009F00, 'spot05_room_0'),
#     (0x020E7000, 0x020F1620, 0x00A620, 'spot06_room_0'),
#     (0x020FC000, 0x021022F0, 0x0062F0, 'spot07_room_0'),
#     (0x02103000, 0x0210F9A0, 0x00C9A0, 'spot07_room_1'),
#     (0x02122000, 0x0212A150, 0x008150, 'spot08_room_0'),
#     (0x0213D000, 0x021455D0, 0x0085D0, 'spot09_room_0'),
#     (0x02157000, 0x021595F0, 0x0025F0, 'spot10_room_0'),
#     (0x0215A000, 0x02162430, 0x008430, 'spot10_room_1'),
#     (0x02163000, 0x02167BF0, 0x004BF0, 'spot10_room_2'),
#     (0x02168000, 0x0216DAB0, 0x005AB0, 'spot10_room_3'),
#     (0x0216E000, 0x021704D0, 0x0024D0, 'spot10_room_4'),
#     (0x02171000, 0x02177FF0, 0x006FF0, 'spot10_room_5'),
#     (0x02178000, 0x0217BAF0, 0x003AF0, 'spot10_room_6'),
#     (0x0217C000, 0x0217E5C0, 0x0025C0, 'spot10_room_7'),
#     (0x0217F000, 0x02181670, 0x002670, 'spot10_room_8'),
#     (0x02182000, 0x02185BE0, 0x003BE0, 'spot10_room_9'),
#     (0x021A0000, 0x021AC7C0, 0x00C7C0, 'spot11_room_0'),
#     (0x021BD000, 0x021CE5C0, 0x0115C0, 'spot12_room_0'),
#     (0x021CF000, 0x021DB0A0, 0x00C0A0, 'spot12_room_1'),
#     (0x021E2000, 0x021E2910, 0x000910, 'spot13_room_0'),
#     (0x021E3000, 0x021F5A40, 0x012A40, 'spot13_room_1'),
#     (0x0220F000, 0x0221C1C0, 0x00D1C0, 'spot15_room_0'),
#     (0x0223C000, 0x02246C90, 0x00AC90, 'spot16_room_0'),
#     (0x02257000, 0x0225D880, 0x006880, 'spot17_room_0'),
#     (0x0225E000, 0x02270350, 0x012350, 'spot17_room_1'),
#     (0x0227C000, 0x0228E7D0, 0x0127D0, 'spot18_room_0'),
#     (0x0228F000, 0x02295200, 0x006200, 'spot18_room_1'),
#     (0x02296000, 0x022A79B0, 0x0119B0, 'spot18_room_2'),
#     (0x022A8000, 0x022C5CF0, 0x01DCF0, 'spot18_room_3'),
#     (0x022C9000, 0x022CE870, 0x005870, 'market_day_room_0'),
#     (0x022D2000, 0x022D77A0, 0x0057A0, 'market_night_room_0'),
#     (0x022F3000, 0x022FA2C0, 0x0072C0, 'HIDAN_room_0'),
#     (0x022FB000, 0x023079E0, 0x00C9E0, 'HIDAN_room_1'),
#     (0x02308000, 0x02317FD0, 0x00FFD0, 'HIDAN_room_2'),
#     (0x02318000, 0x0231A4E0, 0x0024E0, 'HIDAN_room_3'),
#     (0x0231B000, 0x02322890, 0x007890, 'HIDAN_room_4'),
#     (0x02323000, 0x0232D230, 0x00A230, 'HIDAN_room_5'),
#     (0x0232E000, 0x02334FA0, 0x006FA0, 'HIDAN_room_6'),
#     (0x02335000, 0x023389E0, 0x0039E0, 'HIDAN_room_7'),
#     (0x02339000, 0x02342AC0, 0x009AC0, 'HIDAN_room_8'),
#     (0x02343000, 0x0234B770, 0x008770, 'HIDAN_room_9'),
#     (0x0234C000, 0x023644A0, 0x0184A0, 'HIDAN_room_10'),
#     (0x02365000, 0x023687C0, 0x0037C0, 'HIDAN_room_11'),
#     (0x02369000, 0x0236BB80, 0x002B80, 'HIDAN_room_12'),
#     (0x0236C000, 0x02378BE0, 0x00CBE0, 'HIDAN_room_13'),
#     (0x02379000, 0x0237B260, 0x002260, 'HIDAN_room_14'),
#     (0x0237C000, 0x0237D1D0, 0x0011D0, 'HIDAN_room_15'),
#     (0x0237E000, 0x02389970, 0x00B970, 'HIDAN_room_16'),
#     (0x0238A000, 0x02393140, 0x009140, 'HIDAN_room_17'),
#     (0x02394000, 0x02397B80, 0x003B80, 'HIDAN_room_18'),
#     (0x02398000, 0x0239C1E0, 0x0041E0, 'HIDAN_room_19'),
#     (0x0239D000, 0x023A3D10, 0x006D10, 'HIDAN_room_20'),
#     (0x023A4000, 0x023AC4C0, 0x0084C0, 'HIDAN_room_21'),
#     (0x023AD000, 0x023B3B00, 0x006B00, 'HIDAN_room_22'),
#     (0x023B4000, 0x023BAD20, 0x006D20, 'HIDAN_room_23'),
#     (0x023BB000, 0x023C0540, 0x005540, 'HIDAN_room_24'),
#     (0x023C1000, 0x023C7AE0, 0x006AE0, 'HIDAN_room_25'),
#     (0x023C8000, 0x023CE8A0, 0x0068A0, 'HIDAN_room_26'),
#     (0x023E5000, 0x023F2BC0, 0x00DBC0, 'Bmori1_room_0'),
#     (0x023F3000, 0x023F8B60, 0x005B60, 'Bmori1_room_1'),
#     (0x023F9000, 0x02408A30, 0x00FA30, 'Bmori1_room_2'),
#     (0x02409000, 0x0240CA10, 0x003A10, 'Bmori1_room_3'),
#     (0x0240D000, 0x024102B0, 0x0032B0, 'Bmori1_room_4'),
#     (0x02411000, 0x024145E0, 0x0035E0, 'Bmori1_room_5'),
#     (0x02415000, 0x0241E4C0, 0x0094C0, 'Bmori1_room_6'),
#     (0x0241F000, 0x02432000, 0x013000, 'Bmori1_room_7'),
#     (0x02432000, 0x02449B70, 0x017B70, 'Bmori1_room_8'),
#     (0x0244A000, 0x02454190, 0x00A190, 'Bmori1_room_9'),
#     (0x02455000, 0x0245A3E0, 0x0053E0, 'Bmori1_room_10'),
#     (0x0245B000, 0x02465BD0, 0x00ABD0, 'Bmori1_room_11'),
#     (0x02466000, 0x0246E3E0, 0x0083E0, 'Bmori1_room_12'),
#     (0x0246F000, 0x02477AB0, 0x008AB0, 'Bmori1_room_13'),
#     (0x02478000, 0x0247DBB0, 0x005BB0, 'Bmori1_room_14'),
#     (0x0247E000, 0x02480690, 0x002690, 'Bmori1_room_15'),
#     (0x02481000, 0x02485FA0, 0x004FA0, 'Bmori1_room_16'),
#     (0x02486000, 0x0248F150, 0x009150, 'Bmori1_room_17'),
#     (0x02490000, 0x02491340, 0x001340, 'Bmori1_room_18'),
#     (0x02492000, 0x02492510, 0x000510, 'Bmori1_room_19'),
#     (0x02493000, 0x02494300, 0x001300, 'Bmori1_room_20'),
#     (0x02495000, 0x02496780, 0x001780, 'Bmori1_room_21'),
#     (0x02497000, 0x02498DE0, 0x001DE0, 'Bmori1_room_22'),
#     (0x024A7000, 0x024BC2F0, 0x0152F0, 'ydan_room_0'),
#     (0x024BD000, 0x024C1150, 0x004150, 'ydan_room_1'),
#     (0x024C2000, 0x024C7E30, 0x005E30, 'ydan_room_2'),
#     (0x024C8000, 0x024DC1A0, 0x0141A0, 'ydan_room_3'),
#     (0x024DD000, 0x024E1BD0, 0x004BD0, 'ydan_room_4'),
#     (0x024E2000, 0x024EA320, 0x008320, 'ydan_room_5'),
#     (0x024EB000, 0x024EFEC0, 0x004EC0, 'ydan_room_6'),
#     (0x024F0000, 0x024F8910, 0x008910, 'ydan_room_7'),
#     (0x024F9000, 0x024F9D00, 0x000D00, 'ydan_room_8'),
#     (0x024FA000, 0x025038A0, 0x0098A0, 'ydan_room_9'),
#     (0x02504000, 0x02508D80, 0x004D80, 'ydan_room_10'),
#     (0x02509000, 0x02510170, 0x007170, 'ydan_room_11'),
#     (0x02515000, 0x02528110, 0x013110, 'kenjyanoma_room_0'),
#     (0x0253C000, 0x025531E0, 0x0171E0, 'tokinoma_room_0'),
#     (0x02554000, 0x0255B0D0, 0x0070D0, 'tokinoma_room_1'),
#     (0x0255E000, 0x02585C80, 0x027C80, 'link_home_room_0'),
#     (0x02587000, 0x025B7C90, 0x030C90, 'kokiri_shop_room_0'),
#     (0x025CE000, 0x025E3C80, 0x015C80, 'MIZUsin_room_0'),
#     (0x025E4000, 0x025EE160, 0x00A160, 'MIZUsin_room_1'),
#     (0x025EF000, 0x025F4B90, 0x005B90, 'MIZUsin_room_2'),
#     (0x025F5000, 0x025FB710, 0x006710, 'MIZUsin_room_3'),
#     (0x025FC000, 0x02601FE0, 0x005FE0, 'MIZUsin_room_4'),
#     (0x02602000, 0x0260C5F0, 0x00A5F0, 'MIZUsin_room_5'),
#     (0x0260D000, 0x026182C0, 0x00B2C0, 'MIZUsin_room_6'),
#     (0x02619000, 0x0261E550, 0x005550, 'MIZUsin_room_7'),
#     (0x0261F000, 0x0262CCD0, 0x00DCD0, 'MIZUsin_room_8'),
#     (0x0262D000, 0x02634FE0, 0x007FE0, 'MIZUsin_room_9'),
#     (0x02635000, 0x0263AFB0, 0x005FB0, 'MIZUsin_room_10'),
#     (0x0263B000, 0x0263F9B0, 0x0049B0, 'MIZUsin_room_11'),
#     (0x02640000, 0x02646D90, 0x006D90, 'MIZUsin_room_12'),
#     (0x02647000, 0x02647A00, 0x000A00, 'MIZUsin_room_13'),
#     (0x02648000, 0x0264EE60, 0x006E60, 'MIZUsin_room_14'),
#     (0x0264F000, 0x02656430, 0x007430, 'MIZUsin_room_15'),
#     (0x02657000, 0x0265AAD0, 0x003AD0, 'MIZUsin_room_16'),
#     (0x0265B000, 0x02663A20, 0x008A20, 'MIZUsin_room_17'),
#     (0x02664000, 0x026680C0, 0x0040C0, 'MIZUsin_room_18'),
#     (0x02669000, 0x0266C930, 0x003930, 'MIZUsin_room_19'),
#     (0x0266D000, 0x02673740, 0x006740, 'MIZUsin_room_20'),
#     (0x02674000, 0x0267B4A0, 0x0074A0, 'MIZUsin_room_21'),
#     (0x0267C000, 0x026850F0, 0x0090F0, 'MIZUsin_room_22'),
#     (0x02687000, 0x026B2C30, 0x02BC30, 'kokiri_home_room_0'),
#     (0x026C1000, 0x026C82A0, 0x0072A0, 'kakusiana_room_0'),
#     (0x026C9000, 0x026CE190, 0x005190, 'kakusiana_room_1'),
#     (0x026CF000, 0x026D18C0, 0x0028C0, 'kakusiana_room_2'),
#     (0x026D2000, 0x026D7130, 0x005130, 'kakusiana_room_3'),
#     (0x026D8000, 0x026DF960, 0x007960, 'kakusiana_room_4'),
#     (0x026E0000, 0x026E46E0, 0x0046E0, 'kakusiana_room_5'),
#     (0x026E5000, 0x026EAA70, 0x005A70, 'kakusiana_room_6'),
#     (0x026EB000, 0x026EEFD0, 0x003FD0, 'kakusiana_room_7'),
#     (0x026EF000, 0x026F2630, 0x003630, 'kakusiana_room_8'),
#     (0x026F3000, 0x026F8AD0, 0x005AD0, 'kakusiana_room_9'),
#     (0x026F9000, 0x026FEA30, 0x005A30, 'kakusiana_room_10'),
#     (0x026FF000, 0x027076B0, 0x0086B0, 'kakusiana_room_11'),
#     (0x02708000, 0x0270FE50, 0x007E50, 'kakusiana_room_12'),
#     (0x02710000, 0x02716ED0, 0x006ED0, 'kakusiana_room_13'),
#     (0x02718000, 0x0273DB70, 0x025B70, 'entra_room_0'),
#     (0x02754000, 0x02758070, 0x004070, 'bdan_room_0'),
#     (0x02759000, 0x0275EE90, 0x005E90, 'bdan_room_1'),
#     (0x0275F000, 0x027681D0, 0x0091D0, 'bdan_room_2'),
#     (0x02769000, 0x02770160, 0x007160, 'bdan_room_3'),
#     (0x02771000, 0x02775050, 0x004050, 'bdan_room_4'),
#     (0x02776000, 0x0277C020, 0x006020, 'bdan_room_5'),
#     (0x0277D000, 0x02781240, 0x004240, 'bdan_room_6'),
#     (0x02782000, 0x02785520, 0x003520, 'bdan_room_7'),
#     (0x02786000, 0x02789880, 0x003880, 'bdan_room_8'),
#     (0x0278A000, 0x0278DC70, 0x003C70, 'bdan_room_9'),
#     (0x0278E000, 0x02791830, 0x003830, 'bdan_room_10'),
#     (0x02792000, 0x02795800, 0x003800, 'bdan_room_11'),
#     (0x02796000, 0x02799CD0, 0x003CD0, 'bdan_room_12'),
#     (0x0279A000, 0x0279CB50, 0x002B50, 'bdan_room_13'),
#     (0x0279D000, 0x027A31E0, 0x0061E0, 'bdan_room_14'),
#     (0x027A4000, 0x027A66E0, 0x0026E0, 'bdan_room_15'),
#     (0x027C0000, 0x027CB0C0, 0x00B0C0, 'HAKAdan_room_0'),
#     (0x027CC000, 0x027CDAC0, 0x001AC0, 'HAKAdan_room_1'),
#     (0x027CE000, 0x027D8910, 0x00A910, 'HAKAdan_room_2'),
#     (0x027D9000, 0x027DB940, 0x002940, 'HAKAdan_room_3'),
#     (0x027DC000, 0x027DDC40, 0x001C40, 'HAKAdan_room_4'),
#     (0x027DE000, 0x027E3A60, 0x005A60, 'HAKAdan_room_5'),
#     (0x027E4000, 0x027EB570, 0x007570, 'HAKAdan_room_6'),
#     (0x027EC000, 0x027EDAB0, 0x001AB0, 'HAKAdan_room_7'),
#     (0x027EE000, 0x027F3060, 0x005060, 'HAKAdan_room_8'),
#     (0x027F4000, 0x02800B60, 0x00CB60, 'HAKAdan_room_9'),
#     (0x02801000, 0x028087A0, 0x0077A0, 'HAKAdan_room_10'),
#     (0x02809000, 0x0280CD40, 0x003D40, 'HAKAdan_room_11'),
#     (0x0280D000, 0x02812720, 0x005720, 'HAKAdan_room_12'),
#     (0x02813000, 0x02813FB0, 0x000FB0, 'HAKAdan_room_13'),
#     (0x02814000, 0x02819940, 0x005940, 'HAKAdan_room_14'),
#     (0x0281A000, 0x02821270, 0x007270, 'HAKAdan_room_15'),
#     (0x02822000, 0x02824880, 0x002880, 'HAKAdan_room_16'),
#     (0x02825000, 0x02827CD0, 0x002CD0, 'HAKAdan_room_17'),
#     (0x02828000, 0x02835280, 0x00D280, 'HAKAdan_room_18'),
#     (0x02836000, 0x02838D20, 0x002D20, 'HAKAdan_room_19'),
#     (0x02839000, 0x0283AE20, 0x001E20, 'HAKAdan_room_20'),
#     (0x0283B000, 0x028464B0, 0x00B4B0, 'HAKAdan_room_21'),
#     (0x02847000, 0x028499A0, 0x0029A0, 'HAKAdan_room_22'),
#     (0x0284C000, 0x02851EC0, 0x005EC0, 'moribossroom_room_0'),
#     (0x02852000, 0x0285FAB0, 0x00DAB0, 'moribossroom_room_1'),
#     (0x0286D000, 0x028746F0, 0x0076F0, 'syatekijyou_room_0'),
#     (0x02887000, 0x02896F90, 0x00FF90, 'men_room_0'),
#     (0x02897000, 0x028A0290, 0x009290, 'men_room_1'),
#     (0x028A1000, 0x028A5F80, 0x004F80, 'men_room_2'),
#     (0x028A6000, 0x028ADC20, 0x007C20, 'men_room_3'),
#     (0x028AE000, 0x028B8150, 0x00A150, 'men_room_4'),
#     (0x028B9000, 0x028BE0E0, 0x0050E0, 'men_room_5'),
#     (0x028BF000, 0x028C6F40, 0x007F40, 'men_room_6'),
#     (0x028C7000, 0x028CF330, 0x008330, 'men_room_7'),
#     (0x028D0000, 0x028D8210, 0x008210, 'men_room_8'),
#     (0x028D9000, 0x028DC8F0, 0x0038F0, 'men_room_9'),
#     (0x028DD000, 0x028E2C60, 0x005C60, 'men_room_10'),
#     (0x028E4000, 0x0290D7B0, 0x0297B0, 'shop1_room_0'),
#     (0x02920000, 0x0292A8E0, 0x00A8E0, 'hairal_niwa_room_0'),
#     (0x02930000, 0x02943AF0, 0x013AF0, 'ganon_tou_room_0'),
#     (0x02946000, 0x029BB700, 0x075700, 'market_alley_room_0'),
#     (0x029CE000, 0x029D46D0, 0x0066D0, 'spot20_room_0'),
#     (0x029D7000, 0x029D9820, 0x002820, 'market_ruins_room_0'),
#     (0x029DB000, 0x02A00B70, 0x025B70, 'entra_n_room_0'),
#     (0x02A02000, 0x02A27B60, 0x025B60, 'enrui_room_0'),
#     (0x02A2A000, 0x02A9F6F0, 0x0756F0, 'market_alley_n_room_0'),
#     (0x02AA4000, 0x02AA4640, 0x000640, 'hiral_demo_room_0'),
#     (0x02AA7000, 0x02ADD610, 0x036610, 'kokiri_home3_room_0'),
#     (0x02AF8000, 0x02B08F40, 0x010F40, 'jyasinzou_room_0'),
#     (0x02B09000, 0x02B12300, 0x009300, 'jyasinzou_room_1'),
#     (0x02B13000, 0x02B18C10, 0x005C10, 'jyasinzou_room_2'),
#     (0x02B19000, 0x02B1CB50, 0x003B50, 'jyasinzou_room_3'),
#     (0x02B1D000, 0x02B24270, 0x007270, 'jyasinzou_room_4'),
#     (0x02B25000, 0x02B3CF40, 0x017F40, 'jyasinzou_room_5'),
#     (0x02B3D000, 0x02B41800, 0x004800, 'jyasinzou_room_6'),
#     (0x02B42000, 0x02B47510, 0x005510, 'jyasinzou_room_7'),
#     (0x02B48000, 0x02B50070, 0x008070, 'jyasinzou_room_8'),
#     (0x02B51000, 0x02B56DF0, 0x005DF0, 'jyasinzou_room_9'),
#     (0x02B57000, 0x02B5F1A0, 0x0081A0, 'jyasinzou_room_10'),
#     (0x02B60000, 0x02B61010, 0x001010, 'jyasinzou_room_11'),
#     (0x02B62000, 0x02B64060, 0x002060, 'jyasinzou_room_12'),
#     (0x02B65000, 0x02B6A850, 0x005850, 'jyasinzou_room_13'),
#     (0x02B6B000, 0x02B6FC90, 0x004C90, 'jyasinzou_room_14'),
#     (0x02B70000, 0x02B78470, 0x008470, 'jyasinzou_room_15'),
#     (0x02B79000, 0x02B7F190, 0x006190, 'jyasinzou_room_16'),
#     (0x02B80000, 0x02B89610, 0x009610, 'jyasinzou_room_17'),
#     (0x02B8A000, 0x02B8FCB0, 0x005CB0, 'jyasinzou_room_18'),
#     (0x02B90000, 0x02B95DE0, 0x005DE0, 'jyasinzou_room_19'),
#     (0x02B96000, 0x02B9E1C0, 0x0081C0, 'jyasinzou_room_20'),
#     (0x02B9F000, 0x02BA3650, 0x004650, 'jyasinzou_room_21'),
#     (0x02BA4000, 0x02BA70D0, 0x0030D0, 'jyasinzou_room_22'),
#     (0x02BA8000, 0x02BB1190, 0x009190, 'jyasinzou_room_23'),
#     (0x02BB2000, 0x02BB84B0, 0x0064B0, 'jyasinzou_room_24'),
#     (0x02BB9000, 0x02BCEB70, 0x015B70, 'jyasinzou_room_25'),
#     (0x02BCF000, 0x02BDBB20, 0x00CB20, 'jyasinzou_room_26'),
#     (0x02BDC000, 0x02BE16C0, 0x0056C0, 'jyasinzou_room_27'),
#     (0x02BE2000, 0x02BEAA20, 0x008A20, 'jyasinzou_room_28'),
#     (0x02BFD000, 0x02C05660, 0x008660, 'ice_doukutu_room_0'),
#     (0x02C06000, 0x02C12540, 0x00C540, 'ice_doukutu_room_1'),
#     (0x02C13000, 0x02C18AF0, 0x005AF0, 'ice_doukutu_room_2'),
#     (0x02C19000, 0x02C21080, 0x008080, 'ice_doukutu_room_3'),
#     (0x02C22000, 0x02C29670, 0x007670, 'ice_doukutu_room_4'),
#     (0x02C2A000, 0x02C32890, 0x008890, 'ice_doukutu_room_5'),
#     (0x02C33000, 0x02C37260, 0x004260, 'ice_doukutu_room_6'),
#     (0x02C38000, 0x02C3D8F0, 0x0058F0, 'ice_doukutu_room_7'),
#     (0x02C3E000, 0x02C3F950, 0x001950, 'ice_doukutu_room_8'),
#     (0x02C40000, 0x02C48650, 0x008650, 'ice_doukutu_room_9'),
#     (0x02C49000, 0x02C4D3E0, 0x0043E0, 'ice_doukutu_room_10'),
#     (0x02C4E000, 0x02C53900, 0x005900, 'ice_doukutu_room_11'),
#     (0x02C55000, 0x02C83250, 0x02E250, 'malon_stable_room_0'),
#     (0x02C85000, 0x02CAFFC0, 0x02AFC0, 'kakariko_room_0'),
#     (0x02CB1000, 0x02CB4020, 0x003020, 'bdan_boss_room_0'),
#     (0x02CB5000, 0x02CBA0C0, 0x0050C0, 'bdan_boss_room_1'),
#     (0x02CC0000, 0x02CC4270, 0x004270, 'FIRE_bs_room_0'),
#     (0x02CC5000, 0x02CCBFE0, 0x006FE0, 'FIRE_bs_room_1'),
#     (0x02CCD000, 0x02CF65A0, 0x0295A0, 'hut_room_0'),
#     (0x02D05000, 0x02D08910, 0x003910, 'daiyousei_izumi_room_0'),
#     (0x02D0A000, 0x02D118D0, 0x0078D0, 'hakaana_room_0'),
#     (0x02D1B000, 0x02D1F2D0, 0x0042D0, 'yousei_izumi_tate_room_0'),
#     (0x02D2D000, 0x02D31010, 0x004010, 'yousei_izumi_yoko_room_0'),
#     (0x02D33000, 0x02D591D0, 0x0261D0, 'golon_room_0'),
#     (0x02D5B000, 0x02D811E0, 0x0261E0, 'zoora_room_0'),
#     (0x02D83000, 0x02DAEE60, 0x02BE60, 'drag_room_0'),
#     (0x02DB0000, 0x02DD6C30, 0x026C30, 'alley_shop_room_0'),
#     (0x02DD8000, 0x02E00960, 0x028960, 'night_shop_room_0'),
#     (0x02E02000, 0x02E28FA0, 0x026FA0, 'impa_room_0'),
#     (0x02E2A000, 0x02E566F0, 0x02C6F0, 'labo_room_0'),
#     (0x02E58000, 0x02E8B6A0, 0x0336A0, 'tent_room_0'),
#     (0x02E90000, 0x02EA7EC0, 0x017EC0, 'nakaniwa_room_0'),
#     (0x02EAB000, 0x02EAFE30, 0x004E30, 'ddan_boss_room_0'),
#     (0x02EB0000, 0x02EB3DD0, 0x003DD0, 'ddan_boss_room_1'),
#     (0x02EB6000, 0x02EBCFF0, 0x006FF0, 'ydan_boss_room_0'),
#     (0x02EBD000, 0x02EC37F0, 0x0067F0, 'ydan_boss_room_1'),
#     (0x02EC7000, 0x02EC99E0, 0x0029E0, 'HAKAdan_bs_room_0'),
#     (0x02ECA000, 0x02ECFF50, 0x005F50, 'HAKAdan_bs_room_1'),
#     (0x02ED2000, 0x02ED6470, 0x004470, 'MIZUsin_bs_room_0'),
#     (0x02ED7000, 0x02EE22F0, 0x00B2F0, 'MIZUsin_bs_room_1'),
#     (0x02EF4000, 0x02EFBED0, 0x007ED0, 'ganon_room_0'),
#     (0x02EFC000, 0x02F03770, 0x007770, 'ganon_room_1'),
#     (0x02F04000, 0x02F0B850, 0x007850, 'ganon_room_2'),
#     (0x02F0C000, 0x02F13730, 0x007730, 'ganon_room_3'),
#     (0x02F14000, 0x02F1D0D0, 0x0090D0, 'ganon_room_4'),
#     (0x02F1E000, 0x02F26B10, 0x008B10, 'ganon_room_5'),
#     (0x02F27000, 0x02F30BA0, 0x009BA0, 'ganon_room_6'),
#     (0x02F31000, 0x02F3B7A0, 0x00A7A0, 'ganon_room_7'),
#     (0x02F3C000, 0x02F42BE0, 0x006BE0, 'ganon_room_8'),
#     (0x02F43000, 0x02F48920, 0x005920, 'ganon_room_9'),
#     (0x02F51000, 0x02F56E80, 0x005E80, 'ganon_boss_room_0'),
#     (0x02F60000, 0x02F60FD0, 0x000FD0, 'jyasinboss_room_0'),
#     (0x02F61000, 0x02F68E40, 0x007E40, 'jyasinboss_room_1'),
#     (0x02F69000, 0x02F6CDC0, 0x003DC0, 'jyasinboss_room_2'),
#     (0x02F6D000, 0x02F78700, 0x00B700, 'jyasinboss_room_3'),
#     (0x02F7B000, 0x02FB3950, 0x038950, 'kokiri_home4_room_0'),
#     (0x02FB6000, 0x02FE6F60, 0x030F60, 'kokiri_home5_room_0'),
#     (0x02FFA000, 0x03006EB0, 0x00CEB0, 'ganon_final_room_0'),
#     (0x03008000, 0x03032580, 0x02A580, 'kakariko3_room_0'),
#     (0x03042000, 0x030492C0, 0x0072C0, 'hakasitarelay_room_0'),
#     (0x0304A000, 0x03050720, 0x006720, 'hakasitarelay_room_1'),
#     (0x03051000, 0x030594B0, 0x0084B0, 'hakasitarelay_room_2'),
#     (0x0305A000, 0x03062CE0, 0x008CE0, 'hakasitarelay_room_3'),
#     (0x03063000, 0x03067480, 0x004480, 'hakasitarelay_room_4'),
#     (0x03068000, 0x0306C450, 0x004450, 'hakasitarelay_room_5'),
#     (0x0306D000, 0x03074AB0, 0x007AB0, 'hakasitarelay_room_6'),
#     (0x03077000, 0x030C9AF0, 0x052AF0, 'shrine_room_0'),
#     (0x030DD000, 0x030E3760, 0x006760, 'turibori_room_0'),
#     (0x030E6000, 0x03138B10, 0x052B10, 'shrine_n_room_0'),
#     (0x0313B000, 0x0318DAF0, 0x052AF0, 'shrine_r_room_0'),
#     (0x031B0000, 0x031B91C0, 0x0091C0, 'ganontika_room_0'),
#     (0x031BA000, 0x031D69B0, 0x01C9B0, 'ganontika_room_1'),
#     (0x031D7000, 0x031DE7E0, 0x0077E0, 'ganontika_room_2'),
#     (0x031DF000, 0x031E8990, 0x009990, 'ganontika_room_3'),
#     (0x031E9000, 0x031F0C90, 0x007C90, 'ganontika_room_4'),
#     (0x031F1000, 0x031F8540, 0x007540, 'ganontika_room_5'),
#     (0x031F9000, 0x03208BF0, 0x00FBF0, 'ganontika_room_6'),
#     (0x03209000, 0x03210C90, 0x007C90, 'ganontika_room_7'),
#     (0x03211000, 0x0321A070, 0x009070, 'ganontika_room_8'),
#     (0x0321B000, 0x03226890, 0x00B890, 'ganontika_room_9'),
#     (0x03227000, 0x0322DB70, 0x006B70, 'ganontika_room_10'),
#     (0x0322E000, 0x03234950, 0x006950, 'ganontika_room_11'),
#     (0x03235000, 0x03240370, 0x00B370, 'ganontika_room_12'),
#     (0x03241000, 0x03248D40, 0x007D40, 'ganontika_room_13'),
#     (0x03249000, 0x032531A0, 0x00A1A0, 'ganontika_room_14'),
#     (0x03254000, 0x0325BD40, 0x007D40, 'ganontika_room_15'),
#     (0x0325C000, 0x0325EE20, 0x002E20, 'ganontika_room_16'),
#     (0x0325F000, 0x032676A0, 0x0086A0, 'ganontika_room_17'),
#     (0x03268000, 0x03274670, 0x00C670, 'ganontika_room_18'),
#     (0x03275000, 0x0327CD40, 0x007D40, 'ganontika_room_19'),
#     (0x0328B000, 0x03291810, 0x006810, 'hakaana2_room_0'),
#     (0x032A0000, 0x032A4D40, 0x004D40, 'gerudoway_room_0'),
#     (0x032A5000, 0x032AC2B0, 0x0072B0, 'gerudoway_room_1'),
#     (0x032AD000, 0x032B0E50, 0x003E50, 'gerudoway_room_2'),
#     (0x032B1000, 0x032BC310, 0x00B310, 'gerudoway_room_3'),
#     (0x032BD000, 0x032C0920, 0x003920, 'gerudoway_room_4'),
#     (0x032C1000, 0x032C5E40, 0x004E40, 'gerudoway_room_5'),
#     (0x032D3000, 0x032E85F0, 0x0155F0, 'HAKAdanCH_room_0'),
#     (0x032E9000, 0x032F42D0, 0x00B2D0, 'HAKAdanCH_room_1'),
#     (0x032F5000, 0x032F8190, 0x003190, 'HAKAdanCH_room_2'),
#     (0x032F9000, 0x032FAC60, 0x001C60, 'HAKAdanCH_room_3'),
#     (0x032FB000, 0x032FD450, 0x002450, 'HAKAdanCH_room_4'),
#     (0x032FE000, 0x03300960, 0x002960, 'HAKAdanCH_room_5'),
#     (0x03301000, 0x03303E80, 0x002E80, 'HAKAdanCH_room_6'),
#     (0x0330E000, 0x03311620, 0x003620, 'hairal_niwa_n_room_0'),
#     (0x03321000, 0x033271E0, 0x0061E0, 'bowling_room_0'),
#     (0x0332D000, 0x03337800, 0x00A800, 'hakaana_ouke_room_0'),
#     (0x03338000, 0x0333C800, 0x004800, 'hakaana_ouke_room_1'),
#     (0x0333D000, 0x03343110, 0x006110, 'hakaana_ouke_room_2'),
#     (0x03356000, 0x0335D5D0, 0x0075D0, 'hylia_labo_room_0'),
#     (0x03365000, 0x0336E540, 0x009540, 'souko_room_0'),
#     (0x0336F000, 0x03379430, 0x00A430, 'souko_room_1'),
#     (0x0337A000, 0x03382180, 0x008180, 'souko_room_2'),
#     (0x03390000, 0x03393DB0, 0x003DB0, 'miharigoya_room_0'),
#     (0x0339F000, 0x033A5A90, 0x006A90, 'mahouya_room_0'),
#     (0x033AE000, 0x033B7DC0, 0x009DC0, 'takaraya_room_0'),
#     (0x033B8000, 0x033BA000, 0x002000, 'takaraya_room_1'),
#     (0x033BA000, 0x033BC030, 0x002030, 'takaraya_room_2'),
#     (0x033BD000, 0x033BF820, 0x002820, 'takaraya_room_3'),
#     (0x033C0000, 0x033C3020, 0x003020, 'takaraya_room_4'),
#     (0x033C4000, 0x033C7000, 0x003000, 'takaraya_room_5'),
#     (0x033C7000, 0x033C9B00, 0x002B00, 'takaraya_room_6'),
#     (0x033D2000, 0x033D9E80, 0x007E80, 'ganon_sonogo_room_0'),
#     (0x033DA000, 0x033E1BB0, 0x007BB0, 'ganon_sonogo_room_1'),
#     (0x033E2000, 0x033EACA0, 0x008CA0, 'ganon_sonogo_room_2'),
#     (0x033EB000, 0x033F0640, 0x005640, 'ganon_sonogo_room_3'),
#     (0x033F1000, 0x033F9CF0, 0x008CF0, 'ganon_sonogo_room_4'),
#     (0x03404000, 0x03408150, 0x004150, 'ganon_demo_room_0'),
#     (0x0340A000, 0x03438640, 0x02E640, 'face_shop_room_0'),
#     (0x0343B000, 0x034490A0, 0x00E0A0, 'kinsuta_room_0'),
#     (0x0344F000, 0x03466B80, 0x017B80, 'ganontikasonogo_room_0'),
#     (0x03467000, 0x03470F20, 0x009F20, 'ganontikasonogo_room_1'),
# ]
