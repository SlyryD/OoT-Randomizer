from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from json import dump
from typing import Any, Optional, TypeVar

from MQ import align4
from Rom import Rom
from Utils import data_path


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
    SetZImg = 'SetZImg'
    SetCImg = 'SetCImg'
    Backgrounds = 'Backgrounds'
    Background = 'Background'
    BackgroundSource = 'BackgroundSource'
    BackgroundTlut = 'BackgroundTlut'
    CullableEntries = 'CullableEntries'
    CullableEntry = 'CullableEntry'
    Cullable = 'Cullable'

    # Unknown data not referenced in scene and room files
    Unknown = 'Unknown'


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
            'start': f'0x{self.start:08X}',
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


T = TypeVar('T', DataRecord, PointerRecord)


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

        # Add unknown data record from last referenced data record to end of file
        self.add_unknown_record_at_file_end()

        # Fix missing lengths
        self.fix_missing_lengths()

        # Add unknown data records between sorted records
        self.add_unknown_records()

    @abstractmethod
    def parse_file_header(self, alternate: Optional[int] = None) -> DataRecord:
        return NotImplemented

    @abstractmethod
    def get_offset(self, cursor: int) -> tuple[int, Optional[FileDataRelocator]]:
        return NotImplemented

    def expect_file_at_cursor(self, file: FileDataRelocator, cursor: int) -> None:
        if file is None:
            raise Exception(
                f'Unexpected offset at 0x{cursor - self.start:08X} in {self.name}')

    def sort_records(self) -> None:
        self.data_records.sort(key=lambda x: x.offset)
        self.pointer_records.sort(key=lambda x: x.offset)

    def check_for_overlapping_records(self) -> None:
        count = len(self.data_records)
        for i in range(0, count - 1):
            record = self.data_records[i]
            next_record = self.data_records[i + 1]
            if record.offset + record.length > next_record.offset:
                if record.type == RecordType.Vtx and next_record.type == RecordType.Vtx:
                    # Vtx records can overlap, e.g.,
                    # gsSPVertex(&spot00_room_0Vtx_0043E0[43], 32, 0)
                    # gsSPVertex(&spot00_room_0Vtx_0043E0[73], 14, 0)
                    continue
                else:
                    raise Exception(
                        f'Overlapping records: {record.type.value} at offset 0x{record.offset:08X} and {next_record.type.value} at offset 0x{next_record.offset:08X}')

    # Add unknown record at file end
    def add_unknown_record_at_file_end(self) -> None:
        # Handle data at the end of the file
        last_record = self.data_records[-1]
        if last_record.length == -1:
            last_record_end_offset = last_record.offset
            last_record_end = self.start + last_record_end_offset
            data_record = DataRecord(self.rom, RecordType.Unknown, self.start,
                                     last_record_end_offset, self.end - last_record_end)
            self.data_records.pop()
            self.data_records.append(data_record)
        else:
            last_record_end_offset = last_record.offset + last_record.length
            last_record_end = self.start + last_record_end_offset
            data_record = DataRecord(self.rom, RecordType.Unknown, self.start,
                                     last_record_end_offset, self.end - last_record_end)
            self.data_records.append(data_record)

    def fix_missing_lengths(self) -> None:
        # Iterate data records in reverse in case we have multiple missing lengths in a row
        index: int = len(self.data_records) - 1
        if self.data_records[index].type != RecordType.Unknown:
            raise Exception(
                'Expected unknown record at the end of the scene file')
        if self.data_records[index].length == -1:
            raise Exception('Cannot determine length of last record')
        index -= 1
        while index >= 0:
            record = self.data_records[index]
            next_record = self.data_records[index + 1]
            if record.length == -1:
                record.length = next_record.offset - record.offset
            index -= 1

    # Add unknown records between sorted records
    def add_unknown_records(self) -> None:
        # Handle data between records
        index: int = len(self.data_records) - 1
        while index > 0:
            record = self.data_records[index]
            previous_record = self.data_records[index - 1]
            previous_record_end = previous_record.offset + previous_record.length
            if record.offset > previous_record_end:
                data_record = DataRecord(self.rom, RecordType.Unknown, self.start,
                                         previous_record_end, record.offset - previous_record_end)
                self.data_records.insert(index, data_record)
            index -= 1

    # Add data record to the given file and pointer record to this file
    def add_records(self, file: FileDataRelocator, data_record: DataRecord, cursor: int) -> None:
        data_record = self.add_record(file.data_records, data_record)
        pointer_record = PointerRecord(
            self.rom, data_record.type, self.start, cursor - self.start, data_record)
        self.add_record(self.pointer_records, pointer_record)

    # Add and return the given record or return the existing one
    def add_record(self, records: list[T], record: T) -> T:
        existing_record: Optional[T] = self.get_existing_record(
            records, record)
        if existing_record is not None:
            return existing_record
        records.append(record)
        return record

    # Return the existing record matching the given record or None
    def get_existing_record(self, records: list[T], record: T) -> Optional[T]:
        existing_record: Optional[T] = next(
            (x for x in records if x.offset == record.offset), None)
        if existing_record is not None and existing_record != record:
            raise Exception(
                f'Existing {self.name} {existing_record.type} {type(existing_record).__name__} at 0x{existing_record.offset:08X} does not match new {record.type} {type(record).__name__} at 0x{record.offset:08X}')
        return existing_record

    # Parse alternate headers found in scenes and rooms
    def parse_alternate_headers(self, offset: int) -> DataRecord:
        alternate_start = self.start + offset
        cursor = alternate_start
        while True:
            (header_offset, header_file) = self.get_offset(cursor)
            if header_offset == -1:
                break
            # Parse file header
            if header_file is not None:
                record = header_file.parse_file_header(
                    header_file.start + header_offset)
                self.add_records(header_file, record, cursor)
            cursor += 0x04
        return DataRecord(self.rom, RecordType.AlternateHeaders, self.start, offset, cursor - alternate_start)

    # Parse data referenced by scenes

    def parse_path_list(self, offset: int) -> DataRecord:
        paths_start = self.start + offset
        cursor = paths_start
        while True:
            points_count = self.rom.read_byte(cursor)
            (points_offset, points_file) = self.get_offset(cursor + 0x04)
            if points_file is None:
                break
            points_length = align4(points_count * 0x06)
            points_record = DataRecord(
                self.rom, RecordType.Points, points_file.start, points_offset, points_length)
            self.add_records(points_file, points_record, cursor)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.PathList, self.start, offset, cursor - paths_start)

    def parse_collision_header(self, offset: int) -> DataRecord:
        # Vertices
        cursor = self.start + offset + 0x0C
        vertices_count = self.rom.read_int16(cursor)
        (vertices_offset, vertices_file) = self.get_offset(cursor + 0x04)
        self.expect_file_at_cursor(vertices_file, cursor + 0x04)
        vertices_length = align4(vertices_count * 0x06)
        vertices_record = DataRecord(
            self.rom, RecordType.Vertices, vertices_file.start, vertices_offset, vertices_length)
        self.add_records(vertices_file, vertices_record, cursor)
        # Polys
        cursor = self.start + offset + 0x14
        polys_count = self.rom.read_int16(cursor)
        (polys_offset, polys_file) = self.get_offset(cursor + 0x04)
        self.expect_file_at_cursor(polys_file, cursor + 0x04)
        polys_length = polys_count * 0x10
        polys_record = DataRecord(
            self.rom, RecordType.Polys, polys_file.start, polys_offset, polys_length)
        self.add_records(polys_file, polys_record, cursor)
        # Polytypes
        cursor = self.start + offset + 0x1C
        (polytypes_offset, polytypes_file) = self.get_offset(cursor)
        self.expect_file_at_cursor(polytypes_file, cursor)
        polytypes_length = -1
        polytypes_record = DataRecord(
            self.rom, RecordType.Polytypes, polytypes_file.start, polytypes_offset, polytypes_length)
        self.add_records(polytypes_file, polytypes_record, cursor)
        # Cams
        # TODO.Sly: Cam Pos Data
        cursor = self.start + offset + 0x20
        (cams_offset, cams_file) = self.get_offset(cursor)
        cams_length = -1
        if cams_file is not None:
            cams_record = DataRecord(
                self.rom, RecordType.Cams, cams_file.start, cams_offset, cams_length)
            self.add_records(cams_file, cams_record, cursor)
        # Waterboxes
        cursor = self.start + offset + 0x24
        waterboxes_count = self.rom.read_int16(cursor)
        (waterboxes_offset, waterboxes_file) = self.get_offset(cursor + 0x04)
        waterboxes_length = waterboxes_count * 0x10
        if waterboxes_file is not None:
            waterboxes_record = DataRecord(
                self.rom, RecordType.Waterboxes, waterboxes_file.start, waterboxes_offset, waterboxes_length)
            self.add_records(waterboxes_file, waterboxes_record, cursor)
        # Return data record for the collision header
        return DataRecord(self.rom, RecordType.CollisionHeader, self.start, offset, 0x2C)

    # Parse data referenced by rooms

    def parse_room_mesh(self, offset: int) -> DataRecord:
        mesh_start = self.start + offset
        cursor = mesh_start
        mesh_type = self.rom.read_byte(cursor)
        if mesh_type == 1:  # image
            mesh_format = self.rom.read_byte(cursor + 0x01)
            (dlist_entry_offset, dlist_entry_file) = self.get_offset(cursor + 0x04)
            self.expect_file_at_cursor(dlist_entry_file, cursor + 0x04)
            dlist_entry_record = dlist_entry_file.parse_dlist_entry(
                dlist_entry_offset)
            self.add_records(dlist_entry_file,
                             dlist_entry_record, cursor + 0x04)
            if mesh_format == 0x01:  # single
                # single 0x08-0x20 matches background entry 0x04-0x1C
                self.parse_background(cursor - self.start + 0x04)
                cursor += 0x20
            else:  # multi
                count = self.rom.read_byte(cursor + 0x08)
                (backgrounds_offset, backgrounds_file) = self.get_offset(cursor + 0x0C)
                self.expect_file_at_cursor(backgrounds_file, cursor + 0x0C)
                backgrounds_record = backgrounds_file.parse_backgrounds(
                    backgrounds_offset, count)
                self.add_records(backgrounds_file,
                                 backgrounds_record, cursor + 0x0C)
                cursor += 0x10
        else:  # normal or cullable
            count = self.rom.read_byte(cursor + 0x01)
            (start_offset, start_file) = self.get_offset(cursor + 0x04)
            self.expect_file_at_cursor(start_file, cursor + 0x04)
            start_record = start_file.parse_dlist_entries(
                start_offset, count) if mesh_type == 0 else start_file.parse_cullable_entries(start_offset, count)
            self.add_records(start_file, start_record, cursor + 0x04)
            (end_offset, end_file) = self.get_offset(cursor + 0x08)
            self.expect_file_at_cursor(end_file, cursor + 0x08)
            end_type = RecordType.DlistEntry if mesh_type == 0 else RecordType.CullableEntries
            end_record = DataRecord(
                self.rom, end_type, end_file.start, end_offset, 0)
            self.add_records(end_file, end_record, cursor + 0x08)
            cursor += 0x0C
        return DataRecord(self.rom, RecordType.RoomMesh, self.start, offset, cursor - mesh_start)

    def parse_dlist_entries(self, offset: int, count: int) -> DataRecord:
        dlist_entries_start = self.start + offset
        cursor = dlist_entries_start
        for _ in range(count):
            # Do not add individual dlist entry as a record since entries should stay contiguous
            self.parse_dlist_entry(cursor - self.start)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.DlistEntries, self.start, offset, cursor - dlist_entries_start)

    def parse_dlist_entry(self, offset: int) -> DataRecord:
        dlist_entry_start = self.start + offset
        cursor = dlist_entry_start
        (opa_offset, opa_file) = self.get_offset(cursor)
        if opa_file is not None:
            opa_record = opa_file.parse_dlist(opa_offset)
            self.add_records(opa_file, opa_record, cursor)
        (xlu_offset, xlu_file) = self.get_offset(cursor + 0x04)
        if xlu_file is not None:
            xlu_record = xlu_file.parse_dlist(xlu_offset)
            self.add_records(xlu_file, xlu_record, cursor + 0x04)
        return DataRecord(self.rom, RecordType.DlistEntry, self.start, offset, 0x08)

    def parse_dlist(self, offset: int) -> DataRecord:
        dlist_start = self.start + offset
        cursor = dlist_start
        while True:
            op = self.rom.read_byte(cursor)
            if op == 0xDF:  # G_ENDDL
                cursor += 0x08
                break
            (op_offset, op_file) = self.get_offset(cursor + 0x04)
            if op_file is None:  # Ops without pointers to data
                cursor += 0x08
                continue
            if op == 0x01:  # G_VTX
                vtx_count = self.rom.read_int24(cursor + 0x01) >> 12
                record = DataRecord(
                    self.rom, RecordType.Vtx, op_file.start, op_offset, vtx_count * 0x10)
            elif op == 0x04:  # G_BRANCH_Z
                record = op_file.parse_dlist(op_offset)
            elif op == 0xDA:  # G_MTX
                record = DataRecord(
                    self.rom, RecordType.Mtx, op_file.start, op_offset, 0x40)
            elif op == 0xDE:  # G_DL
                record = op_file.parse_dlist(op_offset)
            elif op == 0xFD:  # G_SETTIMG
                record = DataRecord(
                    self.rom, RecordType.SetTImg, op_file.start, op_offset, -1)
            elif op == 0xFE:  # G_SETZIMG
                record = DataRecord(
                    self.rom, RecordType.SetZImg, op_file.start, op_offset, -1)
            elif op == 0xFF:  # G_SETCIMG
                record = DataRecord(
                    self.rom, RecordType.SetCImg, op_file.start, op_offset, -1)
            else:
                raise Exception(
                    f'Unexpected op 0x{op:02X} at 0x{cursor - self.start:08X} in {self.name}')
            self.add_records(op_file, record, cursor + 0x04)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.Dlist, self.start, offset, cursor - dlist_start)

    def parse_backgrounds(self, offset: int, count: int) -> DataRecord:
        backgrounds_start = self.start + offset
        cursor = backgrounds_start
        for _ in range(count):
            # Do not add individual background as a record since backgrounds should stay contiguous
            self.parse_background(cursor - self.start)
            cursor += 0x1C
        return DataRecord(self.rom, RecordType.Backgrounds, self.start, offset, cursor - backgrounds_start)

    def parse_background(self, offset: int) -> DataRecord:
        background_start = self.start + offset
        cursor = background_start
        (source_offset, source_file) = self.get_offset(cursor + 0x04)
        self.expect_file_at_cursor(source_file, cursor + 0x04)
        source_record = DataRecord(
            self.rom, RecordType.BackgroundSource, source_file.start, source_offset, -1)  # TODO.Sly size
        self.add_records(source_file, source_record, cursor + 0x04)
        (tlut_offset, tlut_file) = self.get_offset(cursor + 0x0C)
        if tlut_file is not None:
            tlut_record = DataRecord(
                self.rom, RecordType.BackgroundTlut, tlut_file.start, tlut_offset, -1)  # TODO.Sly size
            self.add_records(tlut_file, tlut_record, cursor + 0x0C)
        return DataRecord(self.rom, RecordType.Background, self.start, offset, 0x1C)

    def parse_cullable_entries(self, offset: int, count: int) -> DataRecord:
        cullable_entries_start = self.start + offset
        cursor = cullable_entries_start
        for _ in range(count):
            # Do not add individual cullable entry as a record since entries should stay contiguous
            self.parse_cullable_entry(cursor - self.start)
            cursor += 0x10
        return DataRecord(self.rom, RecordType.CullableEntries, self.start, offset, cursor - cullable_entries_start)

    def parse_cullable_entry(self, offset: int) -> DataRecord:
        # CullableEntry 0x08-0x10 matches DlistEntry 0x00-0x08
        self.parse_dlist_entry(offset + 0x08)
        return DataRecord(self.rom, RecordType.CullableEntry, self.start, offset, 0x10)

    # Return the file data as a serializable dict
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
            if command == 0x14:  # Terminator
                cursor += 0x08
                break
            count = self.rom.read_byte(cursor + 0x01)
            (offset, file) = self.get_offset(cursor + 0x04)
            if file is None:  # Commands without pointers to data
                cursor += 0x08
                continue
            if command == 0x18:  # AlternateHeaders
                record = file.parse_alternate_headers(offset)
            elif command == 0x04:  # RoomList
                record = file.parse_room_list(offset, count)
            elif command == 0x0E:  # TransitionActorList
                record = DataRecord(
                    self.rom, RecordType.TransitionActorList, file.start, offset, count * 0x10)
            elif command == 0x03:  # CollisionHeader
                record = file.parse_collision_header(offset)
            elif command == 0x06:  # EntranceList
                record = DataRecord(
                    self.rom, RecordType.EntranceList, file.start, offset, -1)
            elif command == 0x0D:  # PathList
                record = file.parse_path_list(offset)
            elif command == 0x00:  # SpawnList
                record = DataRecord(
                    self.rom, RecordType.SpawnList, file.start, offset, count * 0x10)
            elif command == 0x13:  # ExitList
                record = DataRecord(
                    self.rom, RecordType.ExitList, file.start, offset, -1)
            elif command == 0x0F:  # LightSettings
                record = DataRecord(
                    self.rom, RecordType.LightSettings, file.start, offset, -1)
            elif command == 0x17:  # CutsceneData
                record = DataRecord(
                    self.rom, RecordType.CutsceneData, file.start, offset, -1)
            else:
                raise Exception(
                    f'Unexpected command 0x{command:02X} at 0x{cursor - self.start:08X} in {self.name}')
            self.add_records(file, record, cursor)
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
            existing_room: Optional[RoomDataRelocator] = next(
                (x for x in self.rooms if x.start == room_start), None)
            if existing_room is None:
                self.rooms.append(RoomDataRelocator(
                    self.rom, f'{self.name.replace("_scene", "_room")}_{i}', room_start, room_end, self))
            elif existing_room.end != room_end:
                raise Exception(
                    f'Existing room {existing_room.name} at 0x{existing_room.start:08X} does not match new room at 0x{room_start:08X}')
            cursor += 0x08
        return DataRecord(self.rom, RecordType.RoomList, self.start, offset, cursor - rooms_start)

    def get_offset(self, cursor: int) -> tuple[int, Optional[FileDataRelocator]]:
        segment = self.rom.read_byte(cursor)
        offset = self.rom.read_int24(cursor + 1)
        if segment == 0x00 and offset == 0:
            return (0, None)  # null
        if segment == 0x02:
            return (offset, self)  # scene
        return (-1, None)  # unknown

    def to_json(self) -> dict[str, Any]:
        return {
            **super().to_json(),
            'rooms': [x.to_json() for x in self.rooms],
        }


class RoomDataRelocator(FileDataRelocator):
    def __init__(self, rom: Rom, name: str, start: int, end: int, scene: SceneDataRelocator) -> None:
        self.scene = scene
        super().__init__(rom, name, start, end)

    def parse_file_header(self, alternate: Optional[int] = None) -> DataRecord:
        room_start: int = alternate if alternate is not None else self.start
        cursor: int = room_start
        while True:
            command = self.rom.read_byte(cursor)
            if command == 0x14:  # Terminator
                cursor += 0x08
                break
            count = self.rom.read_byte(cursor + 0x01)
            (offset, file) = self.get_offset(cursor + 0x04)
            if file is None:  # Commands without pointers to data
                cursor += 0x08
                continue
            if command == 0x18:  # AlternateHeaders
                record = file.parse_alternate_headers(offset)
            elif command == 0x0A:  # RoomMesh
                record = file.parse_room_mesh(offset)
            elif command == 0x0B:  # ObjectList
                record = DataRecord(
                    self.rom, RecordType.ObjectList, file.start, offset, align4(count * 0x02))
            elif command == 0x01:  # ActorList
                record = DataRecord(
                    self.rom, RecordType.ActorList, file.start, offset, count * 0x10)
            else:
                raise Exception(
                    f'Unexpected command 0x{command:02X} at 0x{cursor - self.start:08X} in {self.name}')
            self.add_records(file, record, cursor)
            cursor += 0x08
        # Return data record for the room header
        return DataRecord(self.rom, RecordType.RoomHeader, self.start, room_start - self.start, cursor - room_start)

    def get_offset(self, cursor: int) -> tuple[int, Optional[FileDataRelocator]]:
        segment = self.rom.read_byte(cursor)
        offset = self.rom.read_int24(cursor + 1)
        if segment == 0x00 and offset == 0:
            return (0, None)  # null
        if segment == 0x02:
            return (offset, self.scene)  # scene
        if segment == 0x03:
            return (offset, self)  # room
        return (-1, None)  # unknown


# rom = Rom('ZOOTDEC.z64')
# fully_mix_skulls(rom)
rom = Rom('zeloot_mqdebug.z64')

scene_data_relocator = SceneDataRelocator(
    rom, 'market_alley_n_scene', 0x02A28000, 0x02A292F0)
# rom, 'spot00_scene', 0x01FB8000, 0x01FE2220)
# rom, 'ddan_scene', 0x01F12000, 0x01F27140)

with open(data_path(f'scenes/{scene_data_relocator.name}.json'), 'w') as outfile:
    dump(scene_data_relocator, outfile, default=lambda x: x.to_json(), indent=4)
