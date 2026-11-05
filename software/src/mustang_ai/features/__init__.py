"""Hardware-agnostic feature controllers (`mustang_ai.features`) consuming pure HAL protocols."""

from mustang_ai.features.maneuver_obstacle import (
    MANEUVER_LIBRARY,
    ManeuverObstacleSequencer,
    ManeuverStep,
)
from mustang_ai.features.person_follower import PersonFollowerController
from mustang_ai.features.voice_emoji_hud import VoiceEmojiHUDController

__all__ = [
    "MANEUVER_LIBRARY",
    "ManeuverObstacleSequencer",
    "ManeuverStep",
    "PersonFollowerController",
    "VoiceEmojiHUDController",
]
