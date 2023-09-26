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
    Name: str = field(metadata={"order": 1})
    Start: str = field(metadata={"order": 2})
    End: str = field(metadata={"order": 3})
    RemapStart: Optional[str] = field(metadata={"order": 4}, default=None)


@dataclass
class Path_MQJson:
    Points: list[list[int]] = field(metadata={"order": 1})


@dataclass
class Room_MQJson:
    File: File_MQJson = field(metadata={"order": 1})
    Id: int = field(metadata={"order": 2})
    Objects: list[str] = field(metadata={"order": 3})
    Actors: list[str] = field(metadata={"order": 4})


@dataclass
class ColVertex_MQJson:
    Id: int = field(metadata={"order": 1})
    X: int = field(metadata={"order": 2})
    Y: int = field(metadata={"order": 3})
    Z: int = field(metadata={"order": 4})


@dataclass
class ColPoly_MQJson:
    Id: int = field(metadata={"order": 1})
    Type: int = field(metadata={"order": 2})
    Flags: int = field(metadata={"order": 3})


@dataclass
class ColMat_MQJson:
    Id: int = field(metadata={"order": 1})
    High: int = field(metadata={"order": 2})
    Low: int = field(metadata={"order": 3})


@dataclass
class ColCam_MQJson:
    Data: int = field(metadata={"order": 1})
    PositionIndex: int = field(metadata={"order": 2})


@dataclass
class ColWaterBox_MQJson:
    Id: int = field(metadata={"order": 1})
    Data: list[int] = field(metadata={"order": 2})


@dataclass
class Col_MQJson:
    IsLarger: bool = field(metadata={"order": 1})
    MinVertex: ColVertex_MQJson = field(metadata={"order": 2})
    MaxVertex: ColVertex_MQJson = field(metadata={"order": 3})
    NumVertices: int = field(metadata={"order": 4})
    Vertices: list[ColVertex_MQJson] = field(metadata={"order": 5})
    NumPolys: int = field(metadata={"order": 6})
    Polys: list[ColPoly_MQJson] = field(metadata={"order": 7})
    NumPolyTypes: int = field(metadata={"order": 8})
    PolyTypes: list[ColMat_MQJson] = field(metadata={"order": 9})
    NumCams: int = field(metadata={"order": 10})
    Cams: list[ColCam_MQJson] = field(metadata={"order": 11})
    NumWaterBoxes: int = field(metadata={"order": 12})
    WaterBoxes: list[ColWaterBox_MQJson] = field(metadata={"order": 13})


@dataclass
class IconPoint:
    Flag: int = field(metadata={"order": 1})
    x: float = field(metadata={"order": 2})
    y: float = field(metadata={"order": 3})


@dataclass
class DungeonFloorIcon:
    Icon: int = field(metadata={"order": 1})
    Count: int = field(metadata={"order": 2})
    IconPoints: list[IconPoint] = field(metadata={"order": 3})


@dataclass
class DungeonFloor:
    Icons: list[DungeonFloorIcon] = field(metadata={"order": 1})


@dataclass
class IconPoint_Minimap:
    Flag: int = field(metadata={"order": 1})
    x: int = field(metadata={"order": 2})
    y: int = field(metadata={"order": 3})


@dataclass
class DungeonMinimapIcon:
    Icon: int = field(metadata={"order": 1})
    Count: int = field(metadata={"order": 2})
    IconPoints: list[IconPoint_Minimap] = field(metadata={"order": 3})


@dataclass
class DungeonMinimap:
    Icons: list[DungeonMinimapIcon] = field(metadata={"order": 1})


@dataclass
class Scene_MQJson:
    File: File_MQJson = field(metadata={"order": 1})
    Id: int = field(metadata={"order": 2})
    TActors: list[str] = field(metadata={"order": 3})
    Paths: list[Path_MQJson] = field(metadata={"order": 4})
    Rooms: list[Room_MQJson] = field(metadata={"order": 5})
    # ColDelta: Col_MQJson = field(metadata={"order": 6})
    Floormaps: list[DungeonFloor] = field(metadata={"order": 7})
    Minimaps: list[DungeonMinimap] = field(metadata={"order": 8})

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
        # self.ColDelta = ???
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

            if command.code == HeaderCommand.PathList:
                offset = command.data2 & 0x00FFFFFF
                self.init_paths(rom, start, offset)
            elif command.code == HeaderCommand.TransitionActorList:
                num_t_actors = command.data1
                offset = command.data2 & 0x00FFFFFF
                self.init_t_actors(rom, start, offset, num_t_actors)
            elif command.code == HeaderCommand.RoomList:
                self.rooms_count = command.data1
                self.rooms_address = command.data2

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
                    rom.read_int16(start + offset + 6 * i),
                    rom.read_int16(start + offset + 6 * i + 2),
                    rom.read_int16(start + offset + 6 * i + 4),
                ]
                path_data.append(point)
            self.Paths.append(Path_MQJson(Points=path_data))

    def init_t_actors(self, rom: Rom, start: int, offset: int, num_t_actors: int) -> None:
        cursor: int = start + offset
        for _ in range(num_t_actors):
            t_actor_data: list[int] = []
            for _ in range(8):
                t_actor_data.append(rom.read_int16(cursor))
                cursor += 2
            self.TActors.append(' '.join([f'{x:04X}' for x in t_actor_data]))


# scene_table = 0x00BA0BB0 # for MQ


def generate_mq_json(rom: Rom, scene_table=0x00B71440):
    mq_json = []
    for id in range(0x00, 0x65):
        start = rom.read_int32(scene_table + (id * 0x14))
        end = rom.read_int32(scene_table + (id * 0x14) + 4)
        mq_json.append(Scene_MQJson(rom, id, start, end))
    return mq_json


class EnhancedJSONEncoder(JSONEncoder):
    def default(self, o):
        if is_dataclass(o):
            return asdict(o)
        return super().default(o)


mq_json = generate_mq_json(Rom("zeloot_mqdebug.z64"))
mq_json_str = dumps(mq_json, indent=2, cls=EnhancedJSONEncoder)
with open(data_path("mqdbg.json"), "w") as f:
    f.write(mq_json_str)
