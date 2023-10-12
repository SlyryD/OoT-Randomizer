from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from json import dump
from typing import Optional, Any

from MQ import align4
from Rom import Rom


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
    RoomHeader = 'RoomHeader'
    RoomMesh = 'RoomMesh'
    ObjectList = 'ObjectList'
    ActorList = 'ActorList'

    # Mesh header record types
    MeshHeader = 'MeshHeader'
    DlistEntries = 'DlistEntries'
    DlistEntry = 'DlistEntry'
    Dlist = 'Dlist'
    Vtx = 'Vtx'
    Mtx = 'Mtx'
    SetTImg = 'SetTImg'
    Backgrounds = 'Backgrounds'
    Background = 'Background'
    BackgroundSource = 'BackgroundSource'
    BackgroundTlut = 'BackgroundTlut'
    CullableEntries = 'CullableEntries'
    CullableEntry = 'CullableEntry'
    Cullable = 'Cullable'

    # Data at the end of the file not referenced by a header
    Unreferenced = 'Unreferenced'


class DataRecord:
    def __init__(self, rom: Rom, type: RecordType, start: int, offset: int, length: int) -> None:
        if offset == -1:
            raise Exception(
                f'Invalid offset {offset} for {type.value} data record')

        self.rom: Rom = rom
        self.type: RecordType = type
        self.start: int = start
        self.offset: int = offset
        self.length: int = length

        self.data: bytearray = self.rom.read_bytes(start + offset, length)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DataRecord):
            return NotImplemented
        return self.type == other.type and self.offset == other.offset and self.length == other.length

    def __hash__(self) -> int:
        return hash((self.type, self.offset, self.length))

    def to_json(self) -> dict[str, Any]:
        return {
            'type': self.type.value,
            'start_offset': f'0x{self.offset:08X}',
            'end_offset': f'0x{self.offset + self.length:08X}'
        }


class PointerRecord:
    def __init__(self, rom: Rom, type: RecordType, start: int, offset: int, record: DataRecord) -> None:
        if offset == -1:
            raise Exception(
                f'Invalid offset {offset} for {type.value} pointer record')

        self.rom: Rom = rom
        self.type: RecordType = type
        self.start: int = start
        self.offset: int = offset
        self.record: DataRecord = record

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PointerRecord):
            return NotImplemented
        return self.type == other.type and self.offset == other.offset and self.record == other.record

    def __hash__(self) -> int:
        return hash((self.type, self.offset, self.record))

    def to_json(self) -> dict[str, Any]:
        return {
            'type': self.type.value,
            'offset': f'0x{self.offset:08X}',
            'record': self.record.to_json()
        }


class FileDataRelocator(ABC):
    def __init__(self, rom: Rom, name: str, start: int, end: int) -> None:
        self.rom: Rom = rom
        self.name: str = name
        self.start: int = start
        self.end: int = end

        self.data_records: list[DataRecord] = []
        self.pointer_records: list[PointerRecord] = []

        # Parse file header
        header_data_record = self.parse_file_header()
        self.data_records.append(header_data_record)

        # Sort records by offset
        self.sort_records()

        # Check for overlapping records
        self.check_for_overlapping_records()

        # Add unreferenced data record from last referenced data record to end of file
        self.add_unreferenced_record()

        # Fix missing lengths
        self.fix_missing_lengths()

    @abstractmethod
    def parse_file_header(self, alternate: Optional[int] = None) -> DataRecord:
        return NotImplemented

    @abstractmethod
    def get_offset(self, cursor: int) -> int:
        return NotImplemented

    def add_records(self, data_record: DataRecord, cursor: int) -> None:
        # Get existing data record or append a new one
        existing_data_record: Optional[DataRecord] = next(
            (x for x in self.data_records if x.offset == data_record.offset), None)
        if existing_data_record is not None:
            if existing_data_record != data_record:
                raise Exception(
                    f'Existing {self.name} {existing_data_record.type} data record at 0x{existing_data_record.offset:08X} does not match new {data_record.type} data record at 0x{data_record.offset:08X}')
            data_record = existing_data_record
        else:
            self.data_records.append(data_record)
        # Get existing pointer record or append a new one
        pointer_record = PointerRecord(
            self.rom, data_record.type, self.start, cursor - self.start, data_record)
        existing_pointer_record: Optional[PointerRecord] = next(
            (x for x in self.pointer_records if x.offset == pointer_record.offset), None)
        if existing_pointer_record is not None:
            if existing_pointer_record != pointer_record:
                raise Exception(
                    f'Existing {self.name} {existing_pointer_record.type} pointer record at 0x{existing_pointer_record.offset:08X} does not match new {pointer_record.type} pointer record at 0x{pointer_record.offset:08X}')
        else:
            self.pointer_records.append(pointer_record)

    def parse_alternate_headers(self, offset: int) -> DataRecord:
        alternate_start = self.start + offset
        cursor = alternate_start
        while True:
            header_offset = self.get_offset(cursor)
            if header_offset == -1:
                break
            # Parse file header
            if header_offset != 0:
                record = self.parse_file_header(self.start + header_offset)
                self.add_records(record, cursor)
            cursor += 0x04
        return DataRecord(self.rom, RecordType.AlternateHeaders, self.start, offset, cursor - alternate_start)

    def sort_records(self) -> None:
        self.data_records.sort(key=lambda x: x.offset)
        self.pointer_records.sort(key=lambda x: x.offset)

    def check_for_overlapping_records(self) -> None:
        count = len(self.data_records)
        for i in range(0, count - 1):
            record = self.data_records[i]
            next_record = self.data_records[i + 1]
            if record.offset + record.length > next_record.offset:
                raise Exception(
                    f'Overlapping records: {record.type.value} at offset 0x{record.offset:08X} and {next_record.type.value} at offset 0x{next_record.offset:08X}')

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
        }


class SceneDataRelocator(FileDataRelocator):
    def __init__(self, rom: Rom, name: str, start: int, end: int) -> None:
        self.rooms: list[RoomDataRelocator] = []
        super().__init__(rom, name, start, end)

    def parse_file_header(self, alternate: Optional[int] = None) -> DataRecord:
        scene_start: int = alternate if alternate is not None else self.start
        cursor: int = scene_start
        while True:
            command = self.rom.read_byte(cursor)
            count = self.rom.read_byte(cursor + 0x01)
            offset = self.get_offset(cursor + 0x04)
            if command == 0x18:  # AlternateHeaders
                record = self.parse_alternate_headers(offset)
            elif command == 0x04:  # RoomList
                record = self.parse_room_list(offset, count)
            elif command == 0x0E:  # TransitionActorList
                record = DataRecord(
                    self.rom, RecordType.TransitionActorList, self.start, offset, count * 0x10)
            elif command == 0x03:  # CollisionHeader
                record = self.parse_collision_header(offset)
            elif command == 0x06:  # EntranceList
                record = DataRecord(
                    self.rom, RecordType.EntranceList, self.start, offset, -1)
            elif command == 0x0D:  # PathList
                record = self.parse_path_list(offset)
            elif command == 0x00:  # SpawnList
                record = DataRecord(
                    self.rom, RecordType.SpawnList, self.start, offset, count * 0x10)
            elif command == 0x13:  # ExitList
                record = DataRecord(
                    self.rom, RecordType.ExitList, self.start, offset, -1)
            elif command == 0x0F:  # LightSettings
                record = DataRecord(
                    self.rom, RecordType.LightSettings, self.start, offset, -1)
            elif command == 0x17:  # CutsceneData
                record = DataRecord(
                    self.rom, RecordType.CutsceneData, self.start, offset, -1)
            elif command == 0x14:  # Terminator
                cursor += 0x08
                break
            else:  # Commands without pointers to data
                cursor += 0x08
                continue
            self.add_records(record, cursor)
            cursor += 0x08
        # Return data record for the scene header
        return DataRecord(self.rom, RecordType.SceneHeader, self.start, scene_start - self.start, cursor - scene_start)

    def parse_room_list(self, offset: int, count: int) -> DataRecord:
        rooms_start = self.start + offset
        cursor = rooms_start
        for i in range(count):
            room_start = self.rom.read_int32(cursor)
            room_end = self.rom.read_int32(cursor + 0x04)
            # Handle the room file
            self.rooms.append(RoomDataRelocator(
                self.rom, f'{self.name.replace("_scene", "_room")}_{i}', room_start, room_end))
            cursor += 0x08
        return DataRecord(self.rom, RecordType.RoomList, self.start, offset, cursor - rooms_start)

    def parse_path_list(self, offset: int) -> DataRecord:
        paths_start = self.start + offset
        cursor = paths_start
        while True:
            points_count = self.rom.read_byte(cursor)
            points_offset = self.get_offset(cursor + 0x04)
            if points_count == 0 or points_offset == -1 or points_offset == 0:
                break
            points_length = align4(points_count * 0x06)
            points_record = DataRecord(
                self.rom, RecordType.Points, self.start, points_offset, points_length)
            self.add_records(points_record, cursor)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.PathList, self.start, offset, cursor - paths_start)

    def parse_collision_header(self, offset: int) -> DataRecord:
        # Vertices
        cursor = self.start + offset + 0x0C
        vertices_count = self.rom.read_int16(cursor)
        vertices_offset = self.get_offset(cursor + 0x04)
        vertices_length = align4(vertices_count * 0x06)
        vertices_record = DataRecord(
            self.rom, RecordType.Vertices, self.start, vertices_offset, vertices_length)
        self.add_records(vertices_record, cursor)
        # Polys
        cursor = self.start + offset + 0x14
        polys_count = self.rom.read_int16(cursor)
        polys_offset = self.get_offset(cursor + 0x04)
        polys_length = polys_count * 0x10
        polys_record = DataRecord(
            self.rom, RecordType.Polys, self.start, polys_offset, polys_length)
        self.add_records(polys_record, cursor)
        # Polytypes
        cursor = self.start + offset + 0x1C
        polytypes_offset = self.get_offset(cursor)
        polytypes_length = -1
        polytypes_record = DataRecord(
            self.rom, RecordType.Polytypes, self.start, polytypes_offset, polytypes_length)
        self.add_records(polytypes_record, cursor)
        # Cams
        cursor = self.start + offset + 0x20
        cams_offset = self.get_offset(cursor)
        cams_length = -1
        if cams_offset != 0:
            cams_record = DataRecord(
                self.rom, RecordType.Cams, self.start, cams_offset, cams_length)
            self.add_records(cams_record, cursor)
        # Waterboxes
        cursor = self.start + offset + 0x24
        waterboxes_count = self.rom.read_int16(cursor)
        waterboxes_offset = self.get_offset(cursor + 0x04)
        waterboxes_length = waterboxes_count * 0x10
        if waterboxes_count != 0 and waterboxes_offset != 0:
            waterboxes_record = DataRecord(
                self.rom, RecordType.Waterboxes, self.start, waterboxes_offset, waterboxes_length)
            self.add_records(waterboxes_record, cursor)
        # Return data record for the collision header
        return DataRecord(self.rom, RecordType.CollisionHeader, self.start, offset, 0x2C)

    def get_offset(self, cursor: int) -> int:
        segment = self.rom.read_byte(cursor)
        offset = self.rom.read_int24(cursor + 1)
        if segment == 0x00 or segment == 0x02:
            return offset
        return -1

    def to_json(self) -> dict[str, Any]:
        return {
            **super().to_json(),
            'rooms': [x.to_json() for x in self.rooms],
        }


class RoomDataRelocator(FileDataRelocator):
    def __init__(self, rom: Rom, name: str, start: int, end: int) -> None:
        super().__init__(rom, name, start, end)

    def parse_file_header(self, alternate: Optional[int] = None) -> DataRecord:
        room_start: int = alternate if alternate is not None else self.start
        cursor: int = room_start
        while True:
            command = self.rom.read_byte(cursor)
            count = self.rom.read_byte(cursor + 0x01)
            offset = self.get_offset(cursor + 0x04)
            if command == 0x18:  # AlternateHeaders
                record = self.parse_alternate_headers(offset)
            elif command == 0x0A:  # RoomMesh
                record = self.parse_room_mesh(offset)
            elif command == 0x0B:  # ObjectList
                record = DataRecord(
                    self.rom, RecordType.ObjectList, self.start, offset, count * 0x02)
            elif command == 0x01:  # ActorList
                record = DataRecord(
                    self.rom, RecordType.ActorList, self.start, offset, count * 0x10)
            elif command == 0x14:  # Terminator
                cursor += 0x08
                break
            else:  # Commands without pointers to data
                cursor += 0x08
                continue
            self.add_records(record, cursor)
            cursor += 0x08
        # Return data record for the room header
        return DataRecord(self.rom, RecordType.RoomHeader, self.start, room_start - self.start, cursor - room_start)

    def parse_room_mesh(self, offset: int) -> DataRecord:
        mesh_start = self.start + offset
        cursor = mesh_start
        mesh_type = self.rom.read_byte(cursor)
        if mesh_type == 1:  # image
            mesh_format = self.rom.read_byte(cursor + 0x01)
            dlist_entry_offset = self.get_offset(cursor + 0x04)
            dlist_entry_record = self.parse_dlist_entry(dlist_entry_offset)
            self.add_records(dlist_entry_record, cursor + 0x04)
            if mesh_format == 0x01:  # single
                # single 0x08-0x20 matches background entry 0x04-0x1C
                self.parse_background(cursor - self.start + 0x04)
                cursor += 0x20
            else:  # multi
                count = self.rom.read_byte(cursor + 0x08)
                backgrounds_offset = self.get_offset(cursor + 0x0C)
                backgrounds_record = self.parse_backgrounds(
                    backgrounds_offset, count)
                self.add_records(backgrounds_record, cursor + 0x0C)
                cursor += 0x10
        else:  # normal or cullable
            count = self.rom.read_byte(cursor + 0x01)
            start_offset = self.get_offset(cursor + 0x04)
            start_record = self.parse_dlist_entries(
                start_offset, count) if mesh_type == 0 else self.parse_cullable_entries(start_offset, count)
            self.add_records(start_record, cursor + 0x04)
            end_offset = self.get_offset(cursor + 0x08)
            end_type = RecordType.DlistEntry if mesh_type == 0 else RecordType.CullableEntries
            end_record = DataRecord(
                self.rom, end_type, self.start, end_offset, 0)
            self.add_records(end_record, cursor + 0x08)
            cursor += 0x0C
        return DataRecord(self.rom, RecordType.RoomMesh, self.start, offset, cursor - mesh_start)

    def parse_dlist_entries(self, offset: int, count: int) -> DataRecord:
        dlist_entries_start = self.start + offset
        cursor = dlist_entries_start
        for _ in range(count):
            # Do not add individual dlist entry records since they should be contiguous
            self.parse_dlist_entry(cursor - self.start)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.DlistEntries, self.start, offset, cursor - dlist_entries_start)

    def parse_dlist_entry(self, offset: int) -> DataRecord:
        dlist_entry_start = self.start + offset
        cursor = dlist_entry_start
        opa_offset = self.get_offset(cursor)
        if opa_offset != -1 and opa_offset != 0:
            opa_record = self.parse_dlist(opa_offset)
            self.add_records(opa_record, cursor)
        xlu_offset = self.get_offset(cursor + 0x04)
        if xlu_offset != -1 and xlu_offset != 0:
            xlu_record = self.parse_dlist(xlu_offset)
            self.add_records(xlu_record, cursor + 0x04)
        return DataRecord(self.rom, RecordType.DlistEntry, self.start, offset, 0x08)

    def parse_dlist(self, offset: int) -> DataRecord:
        dlist_start = self.start + offset
        cursor = dlist_start
        while True:
            op = self.rom.read_byte(cursor)
            offset = self.get_offset(cursor + 0x04)
            if op == 0x01:  # G_VTX
                vtx_count = self.rom.read_int24(cursor + 0x01) >> 12
                record = DataRecord(
                    self.rom, RecordType.Vtx, self.start, offset, vtx_count * 0x10)
            elif op == 0x04:  # G_BRANCH_Z
                record = self.parse_dlist(offset)
            elif op == 0xD6:  # G_DMA_IO
                raise Exception('G_DMA_IO not supported')
            elif op == 0xDA:  # G_MTX
                record = DataRecord(
                    self.rom, RecordType.Mtx, self.start, offset, 0x40)
            elif op == 0xDB:  # G_MOVEWORD
                raise Exception('G_MOVEWORD not supported')
            elif op == 0xDC:  # G_MOVEMEM
                raise Exception('G_MOVEMEM not supported')
            elif op == 0xDE:  # G_DL
                record = self.parse_dlist(offset)
            elif op == 0xFD:  # G_SETTIMG
                record = DataRecord(
                    self.rom, RecordType.SetTImg, self.start, offset, -1)
            elif op == 0xFE:  # G_SETZIMG
                raise Exception('G_SETZIMG not supported')
            elif op == 0xFF:  # G_SETCIMG
                raise Exception('G_SETCIMG not supported')
            elif op == 0xDF:  # G_ENDDL
                cursor += 0x08
                break
            else:  # Ops without pointers to data
                cursor += 0x08
                continue
            self.add_records(record, cursor + 0x04)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.Dlist, self.start, offset, cursor - dlist_start)

    def parse_backgrounds(self, offset: int, count: int) -> DataRecord:
        backgrounds_start = self.start + offset
        cursor = backgrounds_start
        for _ in range(count):
            background_record = self.parse_background(cursor - self.start)
            self.add_records(background_record, cursor)
            cursor += 0x1C
        return DataRecord(self.rom, RecordType.Backgrounds, self.start, offset, cursor - backgrounds_start)

    def parse_background(self, offset: int) -> DataRecord:
        background_start = self.start + offset
        cursor = background_start
        source_offset = self.get_offset(cursor + 0x04)
        source_record = DataRecord(
            self.rom, RecordType.BackgroundSource, self.start, source_offset, -1)  # TODO.Sly size
        self.add_records(source_record, cursor)
        tlut_offset = self.get_offset(cursor + 0x0C)
        if tlut_offset != -1 and tlut_offset != 0:
            tlut_record = DataRecord(
                self.rom, RecordType.BackgroundTlut, self.start, tlut_offset, -1)  # TODO.Sly size
            self.add_records(tlut_record, cursor)
        return DataRecord(self.rom, RecordType.Background, self.start, offset, 0x1C)

    def parse_cullable_entries(self, offset: int, count: int) -> DataRecord:
        cullable_entries_start = self.start + offset
        cursor = cullable_entries_start
        for _ in range(count):
            # Do not add individual cullable entry records since they should be contiguous
            self.parse_cullable_entry(cursor - self.start)
            cursor += 0x10
        return DataRecord(self.rom, RecordType.CullableEntries, self.start, offset, cursor - cullable_entries_start)

    def parse_cullable_entry(self, offset: int) -> DataRecord:
        # CullableEntry 0x08-0x10 matches DlistEntry 0x00-0x08
        self.parse_dlist_entry(offset + 0x08)
        return DataRecord(self.rom, RecordType.CullableEntry, self.start, offset, 0x10)

    def get_offset(self, cursor: int) -> int:
        segment = self.rom.read_byte(cursor)
        offset = self.rom.read_int24(cursor + 1)
        if segment == 0x00 or segment == 0x03:
            return offset
        return -1


# rom = Rom("ZOOTDEC.z64")
# fully_mix_skulls(rom)
rom = Rom("zeloot_mqdebug.z64")

scene_data_relocator = SceneDataRelocator(
    rom, 'spot00_scene', 0x01FB8000, 0x01FE2220)
# rom, 'ddan_scene', 0x01F12000, 0x01F27140)
with open('scene_data_relocator.json', 'w') as outfile:
    dump(scene_data_relocator, outfile, default=lambda x: x.to_json(), indent=4)
