from __future__ import annotations
from enum import Enum
from typing import Optional

# TODO.GQ: Fix category name
class Scenes(Enum):
    # internal name                  id    location name                         category name
    DEKU_TREE                      = 0x00, "Deku Tree"                         , "Deku Tree"
    DODONGOS_CAVERN                = 0x01, "Dodongos Cavern"                   , "Dodongo's Cavern"
    JABU_JABU                      = 0x02, "Jabu Jabus Belly"                  , "Jabu Jabu's Belly"
    FOREST_TEMPLE                  = 0x03, "Forest Temple"                     , "Forest Temple"
    FIRE_TEMPLE                    = 0x04, "Fire Temple"                       , "Fire Temple"
    WATER_TEMPLE                   = 0x05, "Water Temple"                      , "Water Temple"
    SPIRIT_TEMPLE                  = 0x06, "Spirit Temple"                     , "Spirit Temple"
    SHADOW_TEMPLE                  = 0x07, "Shadow Temple"                     , "Shadow Temple"
    BOTTOM_OF_THE_WELL             = 0x08, "Bottom of the Well"                , "Bottom of the Well"
    ICE_CAVERN                     = 0x09, "Ice Cavern"                        , "Ice Cavern"
    GANONS_TOWER                   = 0x0A, "Ganons Tower"                      , "Ganon's Tower"
    GERUDO_TRAINING_GROUND         = 0x0B, "Gerudo Training Ground"            , "Gerudo Training Ground"
    THIEVES_HIDEOUT                = 0x0C, "Thieves Hideout"                   , "Thieves' Hideout"
    INSIDE_GANONS_CASTLE           = 0x0D, "Ganons Castle"                     , "Ganon's Castle"
    GANONS_TOWER_COLLAPSE_INTERIOR = 0x0E, "Ganons Tower Collapse"             , "Collapse"
    INSIDE_GANONS_CASTLE_COLLAPSE  = 0x0F, "Ganons Castle Collapse"            , "Collapse"
    TREASURE_BOX_SHOP              = 0x10, "Market Treasure Chest Game"        , "Market"
    DEKU_TREE_BOSS                 = 0x11, "Deku Tree Boss Room"               , "Deku Tree"
    DODONGOS_CAVERN_BOSS           = 0x12, "Dodongos Cavern Boss Room"         , "Dodongo's Cavern"
    JABU_JABU_BOSS                 = 0x13, "Jabu Jabus Belly Boss Room"        , "Jabu Jabu's Belly"
    FOREST_TEMPLE_BOSS             = 0x14, "Forest Temple Boss Room"           , "Forest Temple"
    FIRE_TEMPLE_BOSS               = 0x15, "Fire Temple Boss Room"             , "Fire Temple"
    WATER_TEMPLE_BOSS              = 0x16, "Water Temple Boss Room"            , "Water Temple"
    SPIRIT_TEMPLE_BOSS             = 0x17, "Spirit Temple Boss Room"           , "Spirit Temple"
    SHADOW_TEMPLE_BOSS             = 0x18, "Shadow Temple Boss Room"           , "Shadow Temple"
    GANONDORF_BOSS                 = 0x19, "Ganondorf Boss Room"               , "Ganon's Tower"
    GANONS_TOWER_COLLAPSE_EXTERIOR = 0x1A, "Ganons Tower Collapse"             , "Collapse"
    MARKET_ENTRANCE_DAY            = 0x1B, "Market Entrance"                   , "Market"
    MARKET_ENTRANCE_NIGHT          = 0x1C, "Market Entrance"                   , "Market"
    MARKET_ENTRANCE_RUINS          = 0x1D, "Market Entrance"                   , "Market"
    BACK_ALLEY_DAY                 = 0x1E, "Market Back Alley"                 , "Market"
    BACK_ALLEY_NIGHT               = 0x1F, "Market Back Alley"                 , "Market"
    MARKET_DAY                     = 0x20, "Market"                            , "Market"
    MARKET_NIGHT                   = 0x21, "Market"                            , "Market"
    MARKET_RUINS                   = 0x22, "Market"                            , "Market"
    TEMPLE_OF_TIME_EXTERIOR_DAY    = 0x23, "Market Outside ToT"                , "Market"
    TEMPLE_OF_TIME_EXTERIOR_NIGHT  = 0x24, "Market Outside ToT"                , "Market"
    TEMPLE_OF_TIME_EXTERIOR_RUINS  = 0x25, "Market Outside ToT"                , "Market"
    KNOW_IT_ALL_BROS_HOUSE         = 0x26, "KF Know it All House"              , "Kokiri Forest"
    TWINS_HOUSE                    = 0x27, "KF House of Twins"                 , "Kokiri Forest"
    MIDOS_HOUSE                    = 0x28, "KF Midos"                          , "Kokiri Forest"
    SARIAS_HOUSE                   = 0x29, "KF Sarias House"                   , "Kokiri Forest"
    KAKARIKO_CENTER_GUEST_HOUSE    = 0x2A, "Kak Carpenter Boss House"          , "Kakariko Village"
    BACK_ALLEY_HOUSE               = 0x2B, "Market Man in Green House"         , "Market"
    BAZAAR                         = 0x2C, "Bazaar"                            , "Kakariko Village/Market"
    KOKIRI_SHOP                    = 0x2D, "KF Shop"                           , "Kokiri Forest"
    GORON_SHOP                     = 0x2E, "GC Shop"                           , "Goron City"
    ZORA_SHOP                      = 0x2F, "ZD Shop"                           , "Zora's Domain"
    POTION_SHOP_KAKARIKO           = 0x30, "Kak Potion Shop"                   , "Kakariko Village"
    POTION_SHOP_MARKET             = 0x31, "Market Potion Shop"                , "Market"
    BOMBCHU_SHOP                   = 0x32, "Bombchu Shop"                      , "Market"
    HAPPY_MASK_SHOP                = 0x33, "Market Happy Mask Shop"            , "Market"
    LINKS_HOUSE                    = 0x34, "KF Links House"                    , "Kokiri Forest"
    DOG_LADY_HOUSE                 = 0x35, "Market Dog Lady House"             , "Market"
    STABLE                         = 0x36, "LLR Stables"                       , "Lon Lon Ranch"
    IMPAS_HOUSE                    = 0x37, "Kak Impas House"                   , "Kakariko Village"
    LAKESIDE_LABORATORY            = 0x38, "LH Lab"                            , "Lake Hylia"
    CARPENTERS_TENT                = 0x39, "GV Carpenters Tent"                , "Gerudo Valley"
    GRAVEKEEPERS_HUT               = 0x3A, "Graveyard Dampes House"            , "Graveyard"
    GREAT_FAIRYS_FOUNTAIN_MAGIC    = 0x3B, "Great Fairy Fountain"              , "Death Mountain Trail/Death Mountain Crater/Outside Ganon's Castle"
    FAIRYS_FOUNTAIN                = 0x3C, "Fairy Fountain"                    , "Death Mountain Crater/Death Mountain Trail/Gerudo's Fortress/Hyrule Field/Sacred Forest Meadow/Zora's Domain/Zora's River"
    GREAT_FAIRYS_FOUNTAIN_SPELLS   = 0x3D, "Great Fairy Fountain"              , "Hyrule Castle/Zora's Fountain/Desert Colossus"
    GROTTOS                        = 0x3E, "Grotto"                            , "Death Mountain Crater/Death Mountain Trail/Desert Colossus/Gerudo Valley/Goron City/Hyrule Castle/Hyrule Field/Kakariko Village/Kokiri Forest/Lake Hylia/Lon Lon Ranch/Lost Woods/Market/Sacred Forest Meadow/Zora's River/Zora's Fountain"
    REDEAD_GRAVE                   = 0x3F, "Graveyard Heart Piece Grave"       , "Graveyard"
    GRAVE_WITH_FAIRYS_FOUNTAIN     = 0x40, "Graveyard Shield Grave"            , "Graveyard"
    ROYAL_FAMILYS_TOMB             = 0x41, "Graveyard Royal Familys Tomb"      , "Graveyard"
    SHOOTING_GALLERY               = 0x42, "Shooting Gallery"                  , "Kakariko Village/Market"
    TEMPLE_OF_TIME                 = 0x43, "ToT"                               , "Temple of Time"
    CHAMBER_OF_THE_SAGES           = 0x44, "Chamber of the Sages"              , "Chamber of the Sages"
    CASTLE_COURTYARD_GUARDS_DAY    = 0x45, "HC Hedge Maze"                     , "Hyrule Castle"
    CASTLE_COURTYARD_GUARDS_NIGHT  = 0x46, "HC Hedge Maze"                     , "Hyrule Castle"
    CUTMAP                         = 0x47, "Cutscene Map"                      , "Cutscene Map"
    WINDMILL_AND_DAMPES_GRAVE      = 0x48, "Kak Windmill/Graveyard Dampe Race" , "Kakariko Village/Graveyard"
    FISHING_POND                   = 0x49, "LH Fishing"                        , "Lake Hylia"
    CASTLE_COURTYARD_ZELDA         = 0x4A, "HC Courtyard"                      , "Hyrule Castle"
    BOMBCHU_BOWLING_ALLEY          = 0x4B, "Market Bombchu Bowling"            , "Market"
    LON_LON_BUILDINGS              = 0x4C, "LLR Talons House/LLR Tower"        , "Lon Lon Ranch"
    MARKET_GUARD_HOUSE             = 0x4D, "Market Guard House"                , "Market"
    POTION_SHOP_GRANNY             = 0x4E, "Kak Odd Medicine Building"         , "Kakariko Village"
    GANON_BOSS                     = 0x4F, "Ganon Boss Fight"                  , "Ganon Boss Fight"
    HOUSE_OF_SKULLTULA             = 0x50, "Kak Skulltula House"               , "Kakariko Village"
    HYRULE_FIELD                   = 0x51, "HF"                                , "Hyrule Field"
    KAKARIKO_VILLAGE               = 0x52, "Kak"                               , "Kakariko Village"
    GRAVEYARD                      = 0x53, "Graveyard"                         , "Graveyard"
    ZORAS_RIVER                    = 0x54, "ZR"                                , "Zora's River"
    KOKIRI_FOREST                  = 0x55, "KF"                                , "Kokiri Forest"
    SACRED_FOREST_MEADOW           = 0x56, "SFM"                               , "Sacred Forest Meadow"
    LAKE_HYLIA                     = 0x57, "LH"                                , "Lake Hylia"
    ZORAS_DOMAIN                   = 0x58, "ZD"                                , "Zora's Domain"
    ZORAS_FOUNTAIN                 = 0x59, "ZF"                                , "Zora's Fountain"
    GERUDO_VALLEY                  = 0x5A, "GV"                                , "Gerudo Valley"
    LOST_WOODS                     = 0x5B, "LW"                                , "Lost Woods"
    DESERT_COLOSSUS                = 0x5C, "Colossus"                          , "Desert Colossus"
    GERUDOS_FORTRESS               = 0x5D, "GF"                                , "Gerudo's Fortress"
    HAUNTED_WASTELAND              = 0x5E, "Wasteland"                         , "Haunted Wasteland"
    HYRULE_CASTLE                  = 0x5F, "HC"                                , "Hyrule Castle"
    DEATH_MOUNTAIN_TRAIL           = 0x60, "DMT"                               , "Death Mountain Trail"
    DEATH_MOUNTAIN_CRATER          = 0x61, "DMC"                               , "Death Mountain Crater"
    GORON_CITY                     = 0x62, "GC"                                , "Goron City"
    LON_LON_RANCH                  = 0x63, "LLR"                               , "Lon Lon Ranch"
    OUTSIDE_GANONS_CASTLE          = 0x64, "OGC"                               , "Outside Ganon's Castle"

    @classmethod
    def for_id(cls, id: str) -> Optional[Scenes]:
        for scene in cls:
            if scene.id == id:
                return scene
        return None

    # index in the scene table
    @property
    def id(self) -> int:
        return self.value[0]

    # used for location names
    def __str__(self) -> str:
        return self.value[1]

    # used for location categories
    @property
    def category(self) -> str:
        return self.value[2]
