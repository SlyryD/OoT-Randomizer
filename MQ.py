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
# Objects and actor spawn data will be appended to the end of the room file if needed.
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
from collections.abc import Callable
from itertools import chain, combinations
import json
from struct import pack, unpack
from typing import Any, Iterator, Optional

from Dungeon import DungeonType
from ntype import uint16, uint32
from Rom import Rom
from Utils import data_path
from World import World

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


class CollisionDataRecord:
    def __init__(self, num: int, addr: int, size: int, data: bytearray) -> None:
        self.num: int = num
        self.addr: int = addr
        self.size: int = size
        self.data: bytearray = data


class CollisionData:
    def __init__(self, mesh: CollisionMesh, rom: Rom, file_start: int, file_end: int) -> None:
        self.file_start = file_start
        self.file_end = file_end
        self.unused_addr = get_segment_address(
            2, self.file_end - self.file_start)

        # Sorted segment addresses for computing number of data elements
        addresses = sorted([mesh.cams_addr, mesh.polytypes_addr, mesh.polys_addr,
                           mesh.vertices_addr, mesh.waterboxes_addr, self.unused_addr])

        # Cams data record; compute number of cams
        next_addr = [addr for addr in addresses if addr > mesh.cams_addr][0]
        num_cams = (next_addr - mesh.cams_addr) // 8
        cams_size = CollisionData.get_cams_size(num_cams)
        cams_start = get_rom_address(self.file_start, mesh.cams_addr)
        self.cams = CollisionDataRecord(
            num_cams,
            mesh.cams_addr,
            cams_size,
            rom.read_bytes(cams_start, cams_size),
        )

        # Polytypes data record; compute number of cams
        next_addr = [addr for addr in addresses if addr > mesh.polys_addr][0]
        num_polytypes = (next_addr - mesh.polytypes_addr) // 8
        polytypes_size = CollisionData.get_polytypes_size(num_polytypes)
        polytypes_start = get_rom_address(self.file_start, mesh.polytypes_addr)
        self.polytypes = CollisionDataRecord(
            num_polytypes,
            mesh.polytypes_addr,
            polytypes_size,
            rom.read_bytes(polytypes_start, polytypes_size),
        )

        # Polys data record
        polys_size = CollisionData.get_polys_size(mesh.num_polys)
        polys_start = get_rom_address(self.file_start, mesh.polys_addr)
        self.polys = CollisionDataRecord(
            mesh.num_polys,
            mesh.polys_addr,
            polys_size,
            rom.read_bytes(polys_start, polys_size),
        )

        # Vertices data record
        vertices_size = CollisionData.get_vertices_size(mesh.num_vertices)
        vertices_start = get_rom_address(self.file_start, mesh.vertices_addr)
        self.vertices = CollisionDataRecord(
            mesh.num_vertices,
            mesh.vertices_addr,
            vertices_size,
            rom.read_bytes(vertices_start, vertices_size),
        )

        # Waterboxes data record
        waterboxes_size = CollisionData.get_waterboxes_size(
            mesh.num_waterboxes)
        waterboxes_start = get_rom_address(
            self.file_start, mesh.waterboxes_addr)
        self.waterboxes = CollisionDataRecord(
            mesh.num_waterboxes,
            mesh.waterboxes_addr,
            waterboxes_size,
            rom.read_bytes(waterboxes_start, waterboxes_size),
        )

        self.start_addr = min([
            self.cams.addr if self.cams.addr > 0 else 0x02FFFFFF,
            self.polytypes.addr if self.polytypes.addr > 0 else 0x02FFFFFF,
            self.polys.addr if self.polys.addr > 0 else 0x02FFFFFF,
            self.vertices.addr if self.vertices.addr > 0 else 0x02FFFFFF,
            self.waterboxes.addr if self.waterboxes.addr > 0 else 0x02FFFFFF,
        ])
        self.end_addr = max([
            self.cams.addr + self.cams.size,
            self.polytypes.addr + self.polytypes.size,
            self.polys.addr + self.polys.size,
            self.vertices.addr + self.vertices.size,
            self.waterboxes.addr + self.waterboxes.size,
        ])

    @staticmethod
    def get_cams_size(num_cams: int) -> int:
        return num_cams * 0x08

    @staticmethod
    def get_polytypes_size(num_polytypes: int) -> int:
        return num_polytypes * 0x08

    @staticmethod
    def get_polys_size(num_polys: int) -> int:
        return num_polys * 0x10

    @staticmethod
    def get_vertices_size(num_vertices: int) -> int:
        return align4(num_vertices * 0x06)

    @staticmethod
    def get_waterboxes_size(num_waterboxes: int) -> int:
        return num_waterboxes * 0x10

    # TODO.GQ: Remove this debug information
    def print(self) -> None:
        # TODO.GQ: Remove this debug information
        def printAddressLine(name: str, start_addr: int, end_addr: Optional[int] = None) -> None:
            if end_addr is None:
                print(
                    f'{name.ljust(17)} {start_addr:08X}            ({get_rom_address(self.file_start, start_addr):08X})')
            else:
                print(
                    f'{name.ljust(17)} {start_addr:08X} - {end_addr:08X} ({get_rom_address(self.file_start, start_addr):08X} - {get_rom_address(self.file_start, end_addr):08X})')

        def printCameraPositions(cams: bytearray, num_cams: int) -> None:
            print('CameraPositionDataArray:')
            for i in range(num_cams):
                numCameras = uint16.read(cams, (i * 0x08) + 0x02)
                camPosData = uint32.read(cams, (i * 0x08) + 0x04)
                if camPosData == 0:
                    continue
                elif numCameras == 0:
                    printAddressLine(f'    {i}: ({numCameras} cams)'.ljust(
                        16), camPosData, camPosData + 0x12)
                else:
                    printAddressLine(f'    {i}: ({numCameras} cams)'.ljust(
                        16), camPosData, camPosData + (numCameras * 0x06))

        printCameraPositions(self.cams.data, self.cams.num)
        printAddressLine('StartAddress:', self.start_addr)
        printAddressLine('CameraDataArray:', self.cams.addr,
                         self.cams.addr + self.cams.size)
        printAddressLine('PolyTypeArray:', self.polytypes.addr,
                         self.polytypes.addr + self.polytypes.size)
        printAddressLine('PolyArray:', self.polys.addr,
                         self.polys.addr + self.polys.size)
        printAddressLine('VertexArray:', self.vertices.addr,
                         self.vertices.addr + self.vertices.size)
        printAddressLine('WaterBoxesArray:', self.waterboxes.addr,
                         self.waterboxes.addr + self.waterboxes.size)
        printAddressLine('EndAddress:', self.end_addr)
        printAddressLine('UnusedAddress:', self.unused_addr)
        print('')


class CollisionMesh:
    def __init__(self, rom: Rom, start: int, offset: int) -> None:
        self.offset = offset
        self.num_vertices = rom.read_int16(start + offset + 0x0C)
        self.vertices_addr = rom.read_int32(start + offset + 0x10)
        self.num_polys = rom.read_int16(start + offset + 0x14)
        self.polys_addr = rom.read_int32(start + offset + 0x18)
        self.polytypes_addr = rom.read_int32(start + offset + 0x1C)
        self.cams_addr = rom.read_int32(start + offset + 0x20)
        self.num_waterboxes = rom.read_int16(start + offset + 0x24)
        self.waterboxes_addr = rom.read_int32(start + offset + 0x28)

    def write_to_scene(self, rom: Rom, start: int) -> None:
        rom.write_int16(start + self.offset + 0x0C, self.num_vertices)
        rom.write_int32(start + self.offset + 0x10, self.vertices_addr)
        rom.write_int16(start + self.offset + 0x14, self.num_polys)
        rom.write_int32(start + self.offset + 0x18, self.polys_addr)
        rom.write_int32(start + self.offset + 0x1C, self.polytypes_addr)
        rom.write_int32(start + self.offset + 0x20, self.cams_addr)
        rom.write_int16(start + self.offset + 0x24, self.num_waterboxes)
        rom.write_int32(start + self.offset + 0x28, self.waterboxes_addr)


class ColDelta:
    def __init__(self, delta: dict[str, bool | list[dict[str, int]]]) -> None:
        self.is_larger: bool = delta['IsLarger']
        self.num_vertices: int = delta['NumVertices']
        self.vertices: list[dict[str, int]] = delta['Vertices']
        self.num_polys: int = delta['NumPolys']
        self.polys: list[dict[str, int]] = delta['Polys']
        self.num_polytypes: int = delta['NumPolyTypes']
        self.polytypes: list[dict[str, int]] = delta['PolyTypes']
        self.num_cams: int = delta['NumCams']
        self.cams: list[dict[str, int]] = delta['Cams']
        self.num_waterboxes: int = delta['NumWaterBoxes']
        self.waterboxes: list[dict[str, int]] = delta['WaterBoxes']


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
    def __init__(self, scene: dict[str, Any], fix_room_data: Optional[Callable[[Rom, Scene, Room], None]]) -> None:
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
        self.fix_room_data = fix_room_data

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
            if self.fix_room_data:
                self.fix_room_data(rom, self, room)

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

        # TODO.GQ: Put this back
        # # fixes jabu jabu floor B1 having no chest data
        # if self.id == 2:
        #     cur = floormap_vrom + (0x08 * 0x1EC + 4)
        #     kaleido_scope_chest_verts = 0x803A3DA0  # hax, should be vram 0x8082EA00
        #     rom.write_int32s(cur, [0x17, kaleido_scope_chest_verts, 0x04])

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
        # original collision data
        original_data = CollisionData(
            mesh, rom, self.file.start, self.file.end)

        # TODO.GQ: Remove this debug information
        print(f'{self.file.name} ORIGINAL COLLISION DATA')
        original_data.print()

        # determine whether the data will fit into the existing space
        # if not, minimize the file size increase by moving the smallest blocks of data
        new_size_data = {
            'cams': CollisionData.get_cams_size(self.coldelta.num_cams),
            'polytypes': CollisionData.get_polytypes_size(self.coldelta.num_polytypes),
            'polys': CollisionData.get_polys_size(self.coldelta.num_polys),
            'vertices': CollisionData.get_vertices_size(self.coldelta.num_vertices),
            'waterboxes': CollisionData.get_waterboxes_size(self.coldelta.num_waterboxes),
        }
        new_size_total = sum(size for size in new_size_data.values())

        # determine which data to move
        if original_data.start_addr + new_size_total > original_data.end_addr:
            data_to_move: tuple[tuple[str, int]] = tuple(new_size_data.items())
            power_set: chain[tuple[tuple[str, int]]] = chain.from_iterable(combinations(
                new_size_data.items(), r) for r in range(1, len(new_size_data) + 1))
            for size_set in power_set:
                size_set_total = sum(size for (_, size) in list(size_set))
                if original_data.start_addr + new_size_total - size_set_total <= original_data.end_addr:
                    data_to_move_total = sum(
                        size for (_, size) in list(data_to_move))
                    if size_set_total < data_to_move_total:
                        data_to_move = size_set
        else:
            data_to_move = ((),)

        # get next mesh address, in the original mesh space or at the end of the original scene file
        def get_next_mesh_addr(data_to_move: tuple[tuple[str, int]], new_size_data: dict[str, int], key: str, curr_addr: int, curr_unused_addr: int) -> tuple[int, int, int]:
            if any(key in x for x in data_to_move):
                return (curr_unused_addr, curr_addr, curr_unused_addr + new_size_data[key])
            elif new_size_data[key] > 0:
                return (curr_addr, curr_addr + new_size_data[key], curr_unused_addr)
            else:
                return (0, curr_addr, curr_unused_addr)

        # move data
        curr_addr = original_data.start_addr
        curr_unused_addr = original_data.unused_addr

        (move_cams_addr, curr_addr, curr_unused_addr) = get_next_mesh_addr(
            data_to_move, new_size_data, 'cams', curr_addr, curr_unused_addr)
        (move_polytypes_addr, curr_addr, curr_unused_addr) = get_next_mesh_addr(
            data_to_move, new_size_data, 'polytypes', curr_addr, curr_unused_addr)
        (move_polys_addr, curr_addr, curr_unused_addr) = get_next_mesh_addr(
            data_to_move, new_size_data, 'polys', curr_addr, curr_unused_addr)
        (move_vertices_addr, curr_addr, curr_unused_addr) = get_next_mesh_addr(
            data_to_move, new_size_data, 'vertices', curr_addr, curr_unused_addr)
        (move_waterboxes_addr, curr_addr, curr_unused_addr) = get_next_mesh_addr(
            data_to_move, new_size_data, 'waterboxes', curr_addr, curr_unused_addr)

        # increase file size as needed
        self.file.end = align16(get_rom_address(
            self.file.start, curr_unused_addr))

        # patch cams
        if move_cams_addr != mesh.cams_addr:
            # move data
            mesh.cams_addr = move_cams_addr
            rom.write_bytes(get_rom_address(self.file.start,
                            move_cams_addr), original_data.cams.data)
        for index, cam in enumerate(self.coldelta.cams):
            data = cam['Data']
            pos = cam['PositionIndex']

            addr = get_rom_address(
                self.file.start, move_cams_addr) + (index * 0x08)
            if pos < 0:
                rom.write_int32s(addr, [data, 0])
            else:
                seg_off = rom.read_int32(addr + 0x04)
                rom.write_int32s(addr, [data, seg_off])

        # patch polytypes
        if move_polytypes_addr != mesh.polytypes_addr:
            # move data
            mesh.polytypes_addr = move_polytypes_addr
            rom.write_bytes(
                get_rom_address(self.file.start,
                                move_polytypes_addr), original_data.polytypes.data)
        for item in self.coldelta.polytypes:
            id = item['Id']
            high = item['High']
            low = item['Low']

            addr = get_rom_address(
                self.file.start, move_polytypes_addr) + (id * 0x08)
            rom.write_int32s(addr, [high, low])

        # patch poly data
        mesh.num_polys = self.coldelta.num_polys
        if move_polys_addr != mesh.polys_addr:
            # move data
            mesh.polys_addr = move_polys_addr
            rom.write_bytes(get_rom_address(self.file.start,
                            move_polys_addr), original_data.polys.data)
        for item in self.coldelta.polys:
            id = item['Id']
            t = item['Type']
            flags = item['Flags']

            addr = get_rom_address(
                self.file.start, move_polys_addr) + (id * 0x10)
            vert_bit = rom.read_byte(addr + 0x02) & 0x1F  # VertexA id data
            rom.write_int16(addr, t)
            rom.write_byte(addr + 0x02, (flags << 5) + vert_bit)

        # patch vertices
        mesh.num_vertices = self.coldelta.num_vertices
        if move_vertices_addr != mesh.vertices_addr:
            # move data
            mesh.vertices_addr = move_vertices_addr
            rom.write_bytes(get_rom_address(self.file.start,
                            move_vertices_addr), original_data.vertices.data)
        for item in self.coldelta.vertices:
            id = item['Id']
            x = item['X']
            y = item['Y']
            z = item['Z']

            addr = get_rom_address(
                self.file.start, move_vertices_addr) + (id * 0x06)
            rom.write_int16s(addr, [x, y, z])

        # patch waterboxes
        mesh.num_waterboxes = self.coldelta.num_waterboxes
        if move_waterboxes_addr != mesh.waterboxes_addr:
            # move data
            mesh.waterboxes_addr = move_waterboxes_addr
            rom.write_bytes(get_rom_address(self.file.start,
                            move_waterboxes_addr), original_data.waterboxes.data)
        for item in self.coldelta.waterboxes:
            id = item['Id']
            data = item['Data']

            addr = get_rom_address(
                self.file.start, move_waterboxes_addr) + (id * 0x10)
            rom.write_int16s(addr, data)

        # Write Mesh to Scene
        mesh.write_to_scene(rom, self.file.start)

        # TODO.GQ: Remove this debug information
        new_data = CollisionData(mesh, rom, self.file.start, self.file.end)
        print(f'{self.file.name} NEW COLLISION DATA')
        new_data.print()

    # appends path data to the end of the file
    # returns segment address to path data

    def append_path_data(self, rom: Rom) -> int:
        start = self.file.start
        cur = self.file.end
        records = []

        # append paths as points
        for path in self.paths:
            nodes = len(path)
            offset = get_segment_address(2, cur - start)
            records.append((nodes, offset))

            # flatten
            points = [x for points in path for x in points]
            rom.write_int16s(cur, points)
            path_size = align4(len(path) * 6)
            cur += path_size

        # append path lengths and start addresses
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
                num_actors = rom.read_byte(headcur + 1)
                actor_list_offset = rom.read_int24(headcur + 5)

                if len(self.actors) > num_actors:
                    offset = self.file.end - self.file.start
                    write_actor_data(rom, self.file.end, self.actors)
                    self.file.end += len(self.actors) * 0x10

                    rom.write_byte(headcur + 1, len(self.actors))
                    rom.write_int32(
                        headcur + 4, get_segment_address(3, offset))
                else:
                    write_actor_data(rom, self.file.start +
                                     actor_list_offset, self.actors)

                    rom.write_byte(headcur + 1, len(self.actors))

            elif code == 0x0B:  # objects
                num_objects = rom.read_byte(headcur + 1)
                object_list_offset = rom.read_int24(headcur + 5)

                if len(self.objects) > num_objects:
                    offset = self.append_object_data(rom, self.objects)

                    rom.write_byte(headcur + 1, len(self.objects))
                    rom.write_int32(
                        headcur + 4, get_segment_address(3, offset))
                else:
                    rom.write_int16s(self.file.start +
                                     object_list_offset, self.objects)

                    rom.write_byte(headcur + 1, len(self.objects))

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


def patch_files(rom: Rom, patch_scenes: list[int], get_json: Callable[[], Any], fix_scene_data: Optional[Callable[[Rom, Scene], None]], fix_room_data: Optional[Callable[[Rom, Scene, Room], None]]) -> None:
    data = get_json()
    scenes = [Scene(x, fix_room_data) for x in data]
    for scene in scenes:
        if scene.id in patch_scenes:
            if fix_scene_data:
                fix_scene_data(rom, scene)
            scene.write_data(rom)


def get_mq_scenes(world: World) -> list[int]:
    # patch mq scenes
    mq_scenes: list[int] = []
    if world.dungeon_mq['Deku Tree'] == DungeonType.MQ:
        mq_scenes.append(0)
    if world.dungeon_mq['Dodongos Cavern'] == DungeonType.MQ:
        mq_scenes.append(1)
    if world.dungeon_mq['Jabu Jabus Belly'] == DungeonType.MQ:
        mq_scenes.append(2)
    if world.dungeon_mq['Forest Temple'] == DungeonType.MQ:
        mq_scenes.append(3)
    if world.dungeon_mq['Fire Temple'] == DungeonType.MQ:
        mq_scenes.append(4)
    if world.dungeon_mq['Water Temple'] == DungeonType.MQ:
        mq_scenes.append(5)
    if world.dungeon_mq['Spirit Temple'] == DungeonType.MQ:
        mq_scenes.append(6)
    if world.dungeon_mq['Shadow Temple'] == DungeonType.MQ:
        mq_scenes.append(7)
    if world.dungeon_mq['Bottom of the Well'] == DungeonType.MQ:
        mq_scenes.append(8)
    if world.dungeon_mq['Ice Cavern'] == DungeonType.MQ:
        mq_scenes.append(9)
    # Scene 10 has no layout changes, so it doesn't need to be patched
    if world.dungeon_mq['Gerudo Training Ground'] == DungeonType.MQ:
        mq_scenes.append(11)
    if world.dungeon_mq['Ganons Castle'] == DungeonType.MQ:
        mq_scenes.append(13)
    return mq_scenes


def get_mq_json() -> Any:
    with open(data_path('mqu.json'), 'r') as stream:
        data = json.load(stream)
    return data


def fix_mq_scene_data(rom: Rom, scene: Scene) -> None:
    if scene.id == 9:
        patch_ice_cavern_scene_header(rom)


def fix_mq_room_data(rom: Rom, scene: Scene, room: Room) -> None:
    if scene.id == 6 and room.id == 6:
        patch_spirit_temple_mq_room_6(rom, room.file.start)


def convert_actor_data(string: str) -> list[int]:
    spawn_args = string.split(" ")
    return [int(x, 16) for x in spawn_args]


def get_rom_address(file_start: int, segment_address: int) -> int:
    return file_start + (segment_address & 0xFFFFFF) if segment_address > 0 else 0


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

    # create new entries
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
