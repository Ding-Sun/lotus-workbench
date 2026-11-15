"""Material presets, in the spirit of Untamed's window-material list.

Each preset is a tint colour plus a tint strength. All presets stay dark or
mid-dark so white text keeps its contrast; strength is deliberately below 80%
so the acrylic blur actually shows through.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    name: str
    color: str
    opacity: int


PRESETS: tuple[Material, ...] = (
    Material("白昼观", "#2B3444", 76),
    Material("云萍城", "#1E3F4F", 72),
    Material("莲花坞", "#4A3560", 68),
    Material("云深不知处", "#1B2A44", 70),
    Material("金鳞台", "#4A3A22", 70),
    Material("彩衣镇", "#5A2E44", 68),
    Material("义城", "#2C2C2C", 72),
    Material("冷泉", "#1F3B3A", 52),
    Material("乱葬岗", "#3A2626", 70),
)

DEFAULT_MATERIAL = "冷泉"


def by_name(name: str) -> Material:
    for preset in PRESETS:
        if preset.name == name:
            return preset
    return by_name(DEFAULT_MATERIAL)

