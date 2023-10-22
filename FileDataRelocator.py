from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from json import dump, dumps
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
    CamPosData = 'CamPosData'

    # Room header record types
    RoomHeader = 'RoomHeader'
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
    BackgroundImage = 'BackgroundImage'
    BackgroundTlut = 'BackgroundTlut'
    CullableEntries = 'CullableEntries'
    CullableEntry = 'CullableEntry'
    Cullable = 'Cullable'

    # Unknown data not referenced in scene and room files
    Unknown = 'Unknown'


class DataRecord:
    def __init__(self, rom: Rom, type: RecordType, start: int, offset: int, length: int) -> None:
        assert offset != -1

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

    def __str__(self) -> str:
        return dumps(self.to_json(), default=lambda x: x.to_json(), indent=2)

    def to_json(self) -> dict[str, Any]:
        return {
            'type': self.type.value,
            'start': f'0x{self.start:08X}',
            'start_offset': f'0x{self.offset:08X}',
            'end_offset': f'0x{self.offset + self.length:08X}'
        }


class PointerRecord:
    def __init__(self, rom: Rom, type: RecordType, start: int, offset: int, pointer: int, record: DataRecord) -> None:
        assert offset != -1

        self.rom: Rom = rom
        self.type: RecordType = type
        self.start: int = start
        self.offset: int = offset
        # pointer can differ from record.offset by pointing to the middle of the data record
        # gsSPVertex(&spot00_room_0Vtx_0043E0[43], 32, 0)
        self.pointer: int = pointer
        self.record: DataRecord = record

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PointerRecord):
            return NotImplemented
        return self.type == other.type and self.offset == other.offset and self.record == other.record

    def __hash__(self) -> int:
        return hash((self.type, self.offset, self.record))

    def __str__(self) -> str:
        return dumps(self.to_json(), default=lambda x: x.to_json(), indent=2)

    def to_json(self) -> dict[str, Any]:
        return {
            'type': self.type.value,
            'offset': f'0x{self.offset:08X}',
            'pointer': f'0x{self.pointer:08X}',
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

        # Merge records where the pointers don't necessarily point to the start of the data record
        self.merge_records()

        # Add unknown data record from last referenced data record to end of file
        self.add_unknown_record_at_file_end()

        # Fix missing lengths
        self.fix_missing_lengths()

        # Check for overlapping records
        self.check_for_overlapping_records()

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

    def merge_records(self) -> None:
        # Iterate data records in order
        index: int = 0
        tracked_record: Optional[DataRecord] = None
        while index < len(self.data_records) - 1:
            record: DataRecord = self.data_records[index]
            next_record: DataRecord = self.data_records[index + 1]
            if self.can_merge(record, next_record):
                # Merge next data record into current data record
                record.length = next_record.offset + next_record.length - record.offset
                removed_record = self.data_records.pop(index + 1)
                assert removed_record == next_record
                # Update pointer record to point to current data record
                pointer_record: Optional[PointerRecord] = next(
                    (x for x in self.pointer_records if x.record == next_record), None)
                assert pointer_record is not None
                pointer_record.record = record
                # Track record to align and read later
                tracked_record = record
            else:
                # Align and adjust record
                if tracked_record is not None:
                    self.adjust_record(
                        tracked_record, tracked_record.offset, align4(tracked_record.length))
                    tracked_record = None
                index += 1
        # Align and adjust record
        if tracked_record is not None:
            self.adjust_record(
                tracked_record, tracked_record.offset, align4(tracked_record.length))
            tracked_record = None

    def can_merge(self, record: DataRecord, next_record: DataRecord) -> bool:
        if record.type == RecordType.CamPosData and next_record.type == RecordType.CamPosData:
            return True
        if record.type == RecordType.Vtx and next_record.type == RecordType.Vtx:
            return True
        return False

    def adjust_record(self, record: DataRecord, offset: int, length: int) -> None:
        record.offset = offset
        record.length = length
        record.data = record.rom.read_bytes(
            record.start + record.offset, record.length)

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
        assert self.data_records[index].type == RecordType.Unknown
        assert self.data_records[index].length != -1
        index -= 1
        while index >= 0:
            record = self.data_records[index]
            next_record = self.data_records[index + 1]
            if record.length == -1:
                record.length = next_record.offset - record.offset
            index -= 1

    def check_for_overlapping_records(self) -> None:
        count = len(self.data_records)
        for i in range(0, count - 1):
            record = self.data_records[i]
            next_record = self.data_records[i + 1]
            if record.offset + record.length > next_record.offset:
                if self.is_record_of_unknown_count(record):
                    # We might parse records without count incorrectly depending on the data that comes next
                    print(
                        f'Warning: Overlapping records: {record.type.value} at offset 0x{record.offset:08X} and {next_record.type.value} at offset 0x{next_record.offset:08X} in {self.name}')
                    self.adjust_record(record, record.offset, next_record.offset - record.offset)
                else:
                    raise Exception(
                        f'Overlapping records: {record.type.value} at offset 0x{record.offset:08X} and {next_record.type.value} at offset 0x{next_record.offset:08X} in {self.name}')

    # Record types referenced by header commands without count
    def is_record_of_unknown_count(self, record: DataRecord) -> bool:
        if record.type == RecordType.CollisionHeader:  # 0x03
            return True
        if record.type == RecordType.EntranceList:  # 0x06
            return True
        if record.type == RecordType.MeshHeader:  # 0x0A
            return True
        if record.type == RecordType.PathList:  # 0x0D
            return True
        if record.type == RecordType.ExitList:  # 0x13
            return True
        if record.type == RecordType.CutsceneData:  # 0x17
            return True
        if record.type == RecordType.AlternateHeaders:  # 0x18
            return True
        if record.type == RecordType.Polytypes:
            return True
        if record.type == RecordType.Cams:
            return True
        if record.type == RecordType.SetTImg:
            return True
        if record.type == RecordType.SetZImg:
            return True
        if record.type == RecordType.SetCImg:
            return True
        return False

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
            self.rom, data_record.type, self.start, cursor - self.start, data_record.offset, data_record)
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
                f'Existing {existing_record.type} {type(existing_record).__name__} at 0x{existing_record.offset:08X} does not match new {record.type} {type(record).__name__} at 0x{record.offset:08X} in {self.name}')
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
        polytypes_record = DataRecord(
            self.rom, RecordType.Polytypes, polytypes_file.start, polytypes_offset, -1)
        self.add_records(polytypes_file, polytypes_record, cursor)
        # Cams
        cursor = self.start + offset + 0x20
        (cams_offset, cams_file) = self.get_offset(cursor)
        if cams_file is not None:
            cams_record = cams_file.parse_cams(cams_offset)
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

    def parse_cams(self, offset: int) -> DataRecord:
        cams_start = self.start + offset
        cursor = cams_start
        while True:
            cam_pos_data_count = self.rom.read_int16(cursor + 0x02)
            (cam_pos_data_offset, cam_pos_data_file) = self.get_offset(cursor + 0x04)
            if cam_pos_data_offset == 0:
                assert cam_pos_data_count == 0
                cursor += 0x08
                continue
            if cam_pos_data_offset == -1:
                break
            cam_pos_data_length = cam_pos_data_count * 0x06
            cam_pos_data_record = DataRecord(
                self.rom, RecordType.CamPosData, cam_pos_data_file.start, cam_pos_data_offset, cam_pos_data_length)
            self.add_records(cam_pos_data_file, cam_pos_data_record, cursor)
            cursor += 0x08
        return DataRecord(self.rom, RecordType.Cams, self.start, offset, cursor - cams_start)

    # Parse data referenced by rooms

    def parse_mesh_header(self, offset: int) -> DataRecord:
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
        return DataRecord(self.rom, RecordType.MeshHeader, self.start, offset, cursor - mesh_start)

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
            elif op == 0xDA:  # G_MTX
                record = DataRecord(
                    self.rom, RecordType.Mtx, op_file.start, op_offset, 0x40)
            elif op == 0xDE:  # G_DL
                record = op_file.parse_dlist(op_offset)
            elif op == 0xE1:  # G_RDPHALF_1
                lookahead_op = self.rom.read_byte(cursor + 0x08)
                if lookahead_op == 0x04:  # G_BRANCH_Z
                    record = op_file.parse_dlist(op_offset)
                elif lookahead_op == 0xDD:  # G_LOAD_UCODE
                    raise Exception(
                        f'Unexpected gsSPLoadUcodeEx at 0x{cursor - self.start:08X} in {self.name}')
                else:
                    cursor += 0x08
                    continue
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
        (image_offset, image_file) = self.get_offset(cursor + 0x04)
        self.expect_file_at_cursor(image_file, cursor + 0x04)
        (tlut_offset, tlut_file) = self.get_offset(cursor + 0x0C)
        assert tlut_offset == 0 and tlut_file is None
        image_width = self.rom.read_int16(cursor + 0x10)
        image_height = self.rom.read_int16(cursor + 0x12)
        image_siz = self.rom.read_byte(cursor + 0x15)
        image_length = image_width * image_height * \
            self.get_pixel_bytes_from_siz(image_siz)
        image_record = DataRecord(
            self.rom, RecordType.BackgroundImage, image_file.start, image_offset, image_length)
        self.add_records(image_file, image_record, cursor + 0x04)
        return DataRecord(self.rom, RecordType.Background, self.start, offset, 0x1C)

    def get_pixel_bytes_from_siz(self, siz: int) -> int:
        if siz == 0:  # G_IM_SIZ_4b
            return 0.5
        elif siz == 1:  # G_IM_SIZ_8b
            return 1
        elif siz == 2:  # G_IM_SIZ_16b
            return 2
        elif siz == 3:  # G_IM_SIZ_32b
            return 4
        else:
            raise Exception(f'Unexpected siz {siz} in {self.name}')

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
            if command == 0x11:  # SkyboxSettings, does not have pointer to data
                skybox_id = self.rom.read_byte(cursor + 0x04)
                skybox_config = self.rom.read_byte(cursor + 0x05)
                skybox_mode = self.rom.read_byte(cursor + 0x06)
                print(f'Warning: SCENE_CMD_SKYBOX_SETTINGS({skybox_id}, {skybox_config}, {skybox_mode}) looks like a pointer at offset 0x{cursor - self.start:08X} in {self.name}')
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
            elif command == 0x01:  # ActorList
                # Scene files do not typically have actor lists, but Gerudo's Fortress and Goron City do
                print(f'Warning: Found actor list at offset 0x{offset:08X} in {self.name}')
                record = DataRecord(
                    self.rom, RecordType.ActorList, file.start, offset, count * 0x10)
            elif command == 0x13:  # ExitList
                record = DataRecord(
                    self.rom, RecordType.ExitList, file.start, offset, -1)
            elif command == 0x0F:  # LightSettings
                record = DataRecord(
                    self.rom, RecordType.LightSettings, file.start, offset, align4(count * 0x16))
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
                    f'Existing room {existing_room.name} at 0x{existing_room.start:08X} does not match new room at 0x{room_start:08X} in {self.name}')
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
            if command == 0x10:  # TimeSettings, does not have pointer to data
                time_hour = self.rom.read_byte(cursor + 0x04)
                time_min = self.rom.read_byte(cursor + 0x05)
                time_speed = self.rom.read_byte(cursor + 0x06)
                print(f'Warning: SCENE_CMD_TIME_SETTINGS({time_hour}, {time_min}, {time_speed}) looks like a pointer at offset 0x{cursor - self.start:08X} in {self.name}')
                cursor += 0x08
                continue
            if command == 0x18:  # AlternateHeaders
                record = file.parse_alternate_headers(offset)
            elif command == 0x0A:  # MeshHeader
                record = file.parse_mesh_header(offset)
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


# scene_table = 0x00B71440 # for Vanilla
# scene_table = 0x00BA0BB0 # for MQ
def generate_scene_file_data_relocators(rom: Rom, scene_table=0x00B71440):
    actors = {}
    for scene in range(0x00, 0x65):
        scene_start = rom.read_int32(scene_table + 0x00 + (scene * 0x14))
        entry = rom.dma.get_dmadata_record_by_key(scene_start)
        scene_data_relocator = SceneDataRelocator(
            rom, get_scene_name(scene), scene_start, entry.end)
        with open(data_path(f'scenes/{scene_data_relocator.name}.json'), 'w') as outfile:
            dump(scene_data_relocator, outfile,
                 default=lambda x: x.to_json(), indent=2)
    return actors


def get_scene_name(scene: int) -> str:
    if scene == 0x00:
        return 'ydan_scene'
    if scene == 0x01:
        return 'ddan_scene'
    if scene == 0x02:
        return 'bdan_scene'
    if scene == 0x03:
        return 'Bmori1_scene'
    if scene == 0x04:
        return 'HIDAN_scene'
    if scene == 0x05:
        return 'MIZUsin_scene'
    if scene == 0x06:
        return 'jyasinzou_scene'
    if scene == 0x07:
        return 'HAKAdan_scene'
    if scene == 0x08:
        return 'HAKAdanCH_scene'
    if scene == 0x09:
        return 'ice_doukutu_scene'
    if scene == 0x0A:
        return 'ganon_scene'
    if scene == 0x0B:
        return 'men_scene'
    if scene == 0x0C:
        return 'gerudoway_scene'
    if scene == 0x0D:
        return 'ganontika_scene'
    if scene == 0x0E:
        return 'ganon_sonogo_scene'
    if scene == 0x0F:
        return 'ganontikasonogo_scene'
    if scene == 0x10:
        return 'takaraya_scene'
    if scene == 0x11:
        return 'ydan_boss_scene'
    if scene == 0x12:
        return 'ddan_boss_scene'
    if scene == 0x13:
        return 'bdan_boss_scene'
    if scene == 0x14:
        return 'moribossroom_scene'
    if scene == 0x15:
        return 'FIRE_bs_scene'
    if scene == 0x16:
        return 'MIZUsin_bs_scene'
    if scene == 0x17:
        return 'jyasinboss_scene'
    if scene == 0x18:
        return 'HAKAdan_bs_scene'
    if scene == 0x19:
        return 'ganon_boss_scene'
    if scene == 0x1A:
        return 'ganon_final_scene'
    if scene == 0x1B:
        return 'entra_scene'
    if scene == 0x1C:
        return 'entra_n_scene'
    if scene == 0x1D:
        return 'enrui_scene'
    if scene == 0x1E:
        return 'market_alley_scene'
    if scene == 0x1F:
        return 'market_alley_n_scene'
    if scene == 0x20:
        return 'market_day_scene'
    if scene == 0x21:
        return 'market_night_scene'
    if scene == 0x22:
        return 'market_ruins_scene'
    if scene == 0x23:
        return 'shrine_scene'
    if scene == 0x24:
        return 'shrine_n_scene'
    if scene == 0x25:
        return 'shrine_r_scene'
    if scene == 0x26:
        return 'kokiri_home_scene'
    if scene == 0x27:
        return 'kokiri_home3_scene'
    if scene == 0x28:
        return 'kokiri_home4_scene'
    if scene == 0x29:
        return 'kokiri_home5_scene'
    if scene == 0x2A:
        return 'kakariko_scene'
    if scene == 0x2B:
        return 'kakariko3_scene'
    if scene == 0x2C:
        return 'shop1_scene'
    if scene == 0x2D:
        return 'kokiri_shop_scene'
    if scene == 0x2E:
        return 'golon_scene'
    if scene == 0x2F:
        return 'zoora_scene'
    if scene == 0x30:
        return 'drag_scene'
    if scene == 0x31:
        return 'alley_shop_scene'
    if scene == 0x32:
        return 'night_shop_scene'
    if scene == 0x33:
        return 'face_shop_scene'
    if scene == 0x34:
        return 'link_home_scene'
    if scene == 0x35:
        return 'impa_scene'
    if scene == 0x36:
        return 'malon_stable_scene'
    if scene == 0x37:
        return 'labo_scene'
    if scene == 0x38:
        return 'hylia_labo_scene'
    if scene == 0x39:
        return 'tent_scene'
    if scene == 0x3A:
        return 'hut_scene'
    if scene == 0x3B:
        return 'daiyousei_izumi_scene'
    if scene == 0x3C:
        return 'yousei_izumi_tate_scene'
    if scene == 0x3D:
        return 'yousei_izumi_yoko_scene'
    if scene == 0x3E:
        return 'kakusiana_scene'
    if scene == 0x3F:
        return 'hakaana_scene'
    if scene == 0x40:
        return 'hakaana2_scene'
    if scene == 0x41:
        return 'hakaana_ouke_scene'
    if scene == 0x42:
        return 'syatekijyou_scene'
    if scene == 0x43:
        return 'tokinoma_scene'
    if scene == 0x44:
        return 'kenjyanoma_scene'
    if scene == 0x45:
        return 'hairal_niwa_scene'
    if scene == 0x46:
        return 'hairal_niwa_n_scene'
    if scene == 0x47:
        return 'hiral_demo_scene'
    if scene == 0x48:
        return 'hakasitarelay_scene'
    if scene == 0x49:
        return 'turibori_scene'
    if scene == 0x4A:
        return 'nakaniwa_scene'
    if scene == 0x4B:
        return 'bowling_scene'
    if scene == 0x4C:
        return 'souko_scene'
    if scene == 0x4D:
        return 'miharigoya_scene'
    if scene == 0x4E:
        return 'mahouya_scene'
    if scene == 0x4F:
        return 'ganon_demo_scene'
    if scene == 0x50:
        return 'kinsuta_scene'
    if scene == 0x51:
        return 'spot00_scene'
    if scene == 0x52:
        return 'spot01_scene'
    if scene == 0x53:
        return 'spot02_scene'
    if scene == 0x54:
        return 'spot03_scene'
    if scene == 0x55:
        return 'spot04_scene'
    if scene == 0x56:
        return 'spot05_scene'
    if scene == 0x57:
        return 'spot06_scene'
    if scene == 0x58:
        return 'spot07_scene'
    if scene == 0x59:
        return 'spot08_scene'
    if scene == 0x5A:
        return 'spot09_scene'
    if scene == 0x5B:
        return 'spot10_scene'
    if scene == 0x5C:
        return 'spot11_scene'
    if scene == 0x5D:
        return 'spot12_scene'
    if scene == 0x5E:
        return 'spot13_scene'
    if scene == 0x5F:
        return 'spot15_scene'
    if scene == 0x60:
        return 'spot16_scene'
    if scene == 0x61:
        return 'spot17_scene'
    if scene == 0x62:
        return 'spot18_scene'
    if scene == 0x63:
        return 'spot20_scene'
    if scene == 0x64:
        return 'ganon_tou_scene'
    raise Exception(f'Unexpected scene {scene:02X}')


# rom = Rom('ZOOTDEC.z64')
# fully_mix_skulls(rom)
rom = Rom('zeloot_mqdebug.z64')
generate_scene_file_data_relocators(rom)
