from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import IntEnum
from json import dumps, JSONEncoder
from sys import version_info
from typing import Optional, Any

from Rom import Rom
from Utils import data_path

if version_info >= (3, 10):
    from typing import TypeAlias
else:
    TypeAlias = str


class HeaderCommand(IntEnum):
    PositionList = 0x00,
    ActorList = 0x01,
    # = 0x02
    Collision = 0x03,
    RoomList = 0x04,
    WindSettings = 0x05,
    EntranceDefs = 0x06,
    SpecialObject = 0x07,
    RoomBehavior = 0x08,
    RoomMesh = 0x0A,
    ObjectList = 0x0B,
    PathList = 0x0D,
    TransitionActorList = 0x0E,
    EnvironmentSettings = 0x0F,
    TimeSettings = 0x10,
    SkyboxSettings = 0x11,
    SkyboxModifier = 0x12,
    ExitList = 0x13,
    End = 0x14,
    SoundSettings = 0x15,
    SoundSettingsEcho = 0x16,
    Cutscene = 0x17,
    AlternateHeaders = 0x18,
    CameraAndWorldMap = 0x19,
    # MM only
    Textures = 0x1A,
    _0x1B = 0x1B,
    Minimap = 0x1C,
    MinimapChests = 0x1E,


class SceneWord:
    def __init__(self, code: int, data1: int, data2: int) -> None:
        self.code: int = code
        self.data1: int = data1
        self.data2: int = data2


@dataclass
class File_MQJson:
    Name: str
    Start: str
    End: str
    RemapStart: Optional[str] = None


@dataclass
class Path_MQJson:
    Points: list[list[int]] = field(default_factory=list)


class Room_MQJson:
    File: File_MQJson
    Id: int
    Objects: list[str]
    Actors: list[str]

    def __init__(self, rom: Rom, scene_id: int, room_id: int, start: int, end: int) -> None:
        self.File = File_MQJson(
            Name=f'Scene {scene_id}, Room {room_id}',
            Start=f'{start:08X}',
            End=f'{end:08X}',
        )
        self.Id = room_id
        self.Objects = []
        self.Actors = []

        cursor: int = start
        command: Optional[SceneWord] = None
        while command is None or command.code != HeaderCommand.End:
            command = SceneWord(
                code=rom.read_byte(cursor),
                data1=rom.read_byte(cursor + 1),
                data2=rom.read_int32(cursor + 4),
            )
            cursor += 8

            if command.code == HeaderCommand.ObjectList:
                offset = command.data2 & 0x00FFFFFF
                self.init_objects(rom, start, offset, command.data1)
            elif command.code == HeaderCommand.ActorList:
                offset = command.data2 & 0x00FFFFFF
                self.init_actors(rom, start, offset, command.data1)

    def init_objects(self, rom: Rom, start: int, offset: int, num_objects: int) -> None:
        cursor: int = start + offset
        for _ in range(num_objects):
            object_id: int = rom.read_int16(cursor)
            self.Objects.append(f'{object_id:04X}')
            cursor += 2

    def init_actors(self, rom: Rom, start: int, offset: int, num_actors: int) -> None:
        cursor: int = start + offset
        for _ in range(num_actors):
            actor_data: list[int] = []
            for _ in range(8):
                actor_data.append(rom.read_int16(cursor))
                cursor += 2
            self.Actors.append(' '.join([f'{x:04X}' for x in actor_data]))


@dataclass
class ColVertex_MQJson:
    Id: int
    X: int
    Y: int
    Z: int


@dataclass
class ColPoly_MQJson:
    Id: int
    Type: int
    Flags: int


@dataclass
class ColMat_MQJson:
    Id: int
    High: int
    Low: int


@dataclass
class ColCam_MQJson:
    Data: int
    PositionIndex: int


@dataclass
class ColWaterBox_MQJson:
    Id: int
    Data: list[int] = field(default_factory=list)


@dataclass
class Col_MQJson:
    IsLarger: bool
    MinVertex: ColVertex_MQJson
    MaxVertex: ColVertex_MQJson
    NumVertices: int = 0
    Vertices: list[ColVertex_MQJson] = field(default_factory=list)
    NumPolys: int = 0
    Polys: list[ColPoly_MQJson] = field(default_factory=list)
    NumPolyTypes: int = 0
    PolyTypes: list[ColMat_MQJson] = field(default_factory=list)
    NumCams: int = 0
    Cams: list[ColCam_MQJson] = field(default_factory=list)
    NumWaterBoxes: int = 0
    WaterBoxes: list[ColWaterBox_MQJson] = field(default_factory=list)


@dataclass
class IconPoint:
    Flag: int
    x: float
    y: float


@dataclass
class DungeonFloorIcon:
    Icon: int
    Count: int
    IconPoints: list[IconPoint] = field(default_factory=list)


@dataclass
class DungeonFloor:
    Icons: list[DungeonFloorIcon] = field(default_factory=list)


@dataclass
class IconPoint_Minimap:
    Flag: int
    x: int
    y: int


@dataclass
class DungeonMinimapIcon:
    Icon: int
    Count: int
    IconPoints: list[IconPoint_Minimap] = field(default_factory=list)


@dataclass
class DungeonMinimap:
    Icons: list[DungeonMinimapIcon] = field(default_factory=list)


class Scene_MQJson:
    File: File_MQJson
    Id: int
    TActors: list[str]
    Paths: list[Path_MQJson]
    Rooms: list[Room_MQJson]
    ColDelta: Col_MQJson
    Floormaps: list[DungeonFloor]
    Minimaps: list[DungeonMinimap]

    def __init__(self, rom: Rom, id: int, start: int, end: int) -> None:
        self.File = File_MQJson(
            Name=f'Scene {id}',
            Start=f'{start:08X}',
            End=f'{end:08X}',
        )
        self.Id = id
        self.TActors = []
        self.Paths = []
        self.Rooms = []
        self.ColDelta = None
        self.Floormaps = []
        self.Minimaps = []

        print(self.File.Name)

        cursor: int = start
        command: Optional[SceneWord] = None
        while command is None or command.code != HeaderCommand.End:
            command = SceneWord(
                code=rom.read_byte(cursor),
                data1=rom.read_byte(cursor + 1),
                data2=rom.read_int32(cursor + 4),
            )
            print(
                f'{cursor:02X} {HeaderCommand(command.code).name} {command.data1:02X} {command.data2:04X}'
            )
            cursor += 8

            if command.code == HeaderCommand.TransitionActorList:
                num_t_actors = command.data1
                offset = command.data2 & 0x00FFFFFF
                self.init_t_actors(rom, start, offset, num_t_actors)
            elif command.code == HeaderCommand.PathList:
                offset = command.data2 & 0x00FFFFFF
                self.init_paths(rom, start, offset)
            elif command.code == HeaderCommand.RoomList:
                num_rooms = command.data1
                offset = command.data2 & 0x00FFFFFF
                self.init_rooms(rom, start, offset, num_rooms)
            elif command.code == HeaderCommand.Collision:
                offset = command.data2 & 0x00FFFFFF
                self.init_collision(rom, start, offset)

    def init_t_actors(self, rom: Rom, start: int, offset: int, num_t_actors: int) -> None:
        cursor: int = start + offset
        for _ in range(num_t_actors):
            t_actor_data: list[int] = []
            for _ in range(8):
                t_actor_data.append(rom.read_int16(cursor))
                cursor += 2
            t_actor = ' '.join([f'{x:04X}' for x in t_actor_data])
            self.TActors.append(t_actor)

    def init_paths(self, rom: Rom, start: int, offset: int) -> None:
        cursor: int = start + offset
        for _ in range(20):
            num_nodes: int = rom.read_byte(cursor)
            cursor += 4

            segment: int = rom.read_byte(cursor)
            offset: int = rom.read_int24(cursor + 1)
            cursor += 4

            if num_nodes <= 0 or offset >= 0x002FFFFF or segment != 0x02:
                break

            path_data: list[list[int]] = []
            for i in range(num_nodes):
                point = [
                    rom.read_int16(start + offset + (i * 6)),
                    rom.read_int16(start + offset + (i * 6) + 2),
                    rom.read_int16(start + offset + (i * 6) + 4),
                ]
                path_data.append(point)

            path = Path_MQJson(path_data)
            self.Paths.append(path)

    def init_rooms(self, rom: Rom, start: int, offset: int, num_rooms: int) -> None:
        for room_id in range(num_rooms):
            room_start = rom.read_int32(start + offset + (room_id * 8))
            room_end = rom.read_int32(start + offset + (room_id * 8) + 4)
            room = Room_MQJson(rom, self.Id, room_id, room_start, room_end)
            self.Rooms.append(room)

    def init_collision(self, rom: Rom, start: int, offset: int) -> None:
        is_larger: bool = False

        min_vertex: ColVertex_MQJson = ColVertex_MQJson(
            -1,
            rom.read_int16(start + offset),
            rom.read_int16(start + offset + 2),
            rom.read_int16(start + offset + 4),
        )
        max_vertex: ColVertex_MQJson = ColVertex_MQJson(
            -1,
            rom.read_int16(start + offset + 0x06),
            rom.read_int16(start + offset + 0x06 + 2),
            rom.read_int16(start + offset + 0x06 + 4),
        )

        num_vertices: int = rom.read_int16(start + offset + 0x0C)
        vertices_offset: int = rom.read_int32(start + offset + 0x10) & 0x00FFFFFF
        vertices = []
        for i in range(num_vertices):
            vertex = ColVertex_MQJson(
                i,
                rom.read_int16(start + vertices_offset + (i * 6)),
                rom.read_int16(start + vertices_offset + (i * 6) + 2),
                rom.read_int16(start + vertices_offset + (i * 6) + 4),
            )
            vertices.append(vertex)

        num_polys: int = rom.read_int16(start + offset + 0x14)
        polys_offset: int = rom.read_int32(start + offset + 0x18) & 0x00FFFFFF
        polys = []
        for i in range(num_polys):
            poly = ColPoly_MQJson(
                i,
                rom.read_int16(start + polys_offset + (i * 16)),
                (rom.read_byte(start + polys_offset + (i * 16) + 2) & 0xE0) >> 5,
            )
            polys.append(poly)

        polytypes_offset: int = rom.read_int32(start + offset + 0x18) & 0x00FFFFFF
        num_polytypes: int = (polys_offset - polytypes_offset) // 8
        polytypes = []
        if polytypes_offset != 0:
            for i in range(num_polytypes):
                polytype = ColMat_MQJson(
                    i,
                    rom.read_int32(start + polytypes_offset + (i * 8)),
                    rom.read_int32(start + polytypes_offset + (i * 8) + 4),
                )
                polytypes.append(polytype)

        cams_offset: int = rom.read_int32(start + offset + 0x20) & 0x00FFFFFF
        num_cams: int = (polytypes_offset - cams_offset) // 8
        cams = []
        if cams_offset != 0:
            for i in range(num_cams):
                cam = ColCam_MQJson(
                    rom.read_int32(start + cams_offset + (i * 8)),
                    i,
                )
                cams.append(cam)

        num_waterboxes: int = rom.read_int16(start + offset + 0x24)
        waterboxes_offset: int = rom.read_int16(start + offset + 0x28) & 0x00FFFFFF
        waterboxes = []
        for i in range(num_waterboxes):
            waterbox = ColWaterBox_MQJson(
                i,
                [rom.read_int16(start + waterboxes_offset + (i * 16) + (j * 2)) for j in range(8)]
            )
            waterboxes.append(waterbox)

        self.ColDelta = Col_MQJson(
            is_larger,
            min_vertex,
            max_vertex,
            num_vertices,
            vertices,
            num_polys,
            polys,
            num_polytypes,
            polytypes,
            num_cams,
            cams,
            num_waterboxes,
            waterboxes,
        )


# scene_table = 0x00BA0BB0 # for MQ


def generate_mq_json(rom: Rom, scene_table=0x00B71440):
    mq_json = []
    for scene_id in range(0x00, 0x65):
        scene_start = rom.read_int32(scene_table + (scene_id * 0x14))
        scene_end = rom.read_int32(scene_table + (scene_id * 0x14) + 4)
        scene = Scene_MQJson(rom, scene_id, scene_start, scene_end)
        mq_json.append(scene)
    return mq_json


class EnhancedJSONEncoder(JSONEncoder):
    def default(self, o):
        if is_dataclass(o):
            return asdict(o)
        return o.__dict__


mq_json = generate_mq_json(Rom("zeloot_mqdebug.z64"))
mq_json_str = dumps(mq_json, indent=2, cls=EnhancedJSONEncoder)
with open(data_path("mqdbg.json"), "w") as f:
    f.write(mq_json_str)
