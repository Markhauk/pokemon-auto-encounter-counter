from __future__ import annotations

from dataclasses import dataclass


FRAME_TYPE_1 = 1
FRAME_TYPE_2 = 2
FRAME_TYPE_3 = 3
FRAME_TYPE_4 = 4
FRAME_TYPE_5 = 5
FRAME_TYPE_6 = 6
FRAME_TYPE_7 = 7
FRAME_TYPE_8 = 8
FRAME_TYPE_9 = 9
FRAME_TYPE_10 = 10
FRAME_TYPE_11 = 11
FRAME_TYPE_12 = 12
FRAME_TYPE_13 = 13
FRAME_TYPE_14 = 14
FRAME_TYPE_15 = 15
FRAME_TYPE_16 = 16
FRAME_TYPE_17 = 17
FRAME_TYPE_18 = 18
FRAME_TYPE_19 = 19
FRAME_TYPE_20 = 20
DEFAULT_FRAME_TYPE = FRAME_TYPE_1


@dataclass(frozen=True)
class InterfaceFrameDefinition:
    frame_type: int
    name: str
    description: str

    @property
    def asset_filename(self) -> str:
        return f"frame_{self.frame_type:02d}.png"


INTERFACE_FRAME_DEFINITIONS = (
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_1,
        name="Frame Type 1",
        description="Lavender layered edge inspired by the default Generation 3 frame.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_2,
        name="Frame Type 2",
        description="Bright monochrome edge with the sharper Generation 3 contrast.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_3,
        name="Frame Type 3",
        description="Red and blue checker pattern with circular corner details.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_4,
        name="Frame Type 4",
        description="Steel-gray frame with small mechanical corner joints.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_5,
        name="Frame Type 5",
        description="Vivid orange, green, and blue high-contrast border.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_6,
        name="Frame Type 6",
        description="Muted green mosaic edge with a weathered texture.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_7,
        name="Frame Type 7",
        description="Red geometric maze pattern with white highlights.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_8,
        name="Frame Type 8",
        description="Black and white lines with multicolor star corners.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_9,
        name="Frame Type 9",
        description="Icy blue zigzag pattern with rounded corners.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_10,
        name="Frame Type 10",
        description="Golden woven edge with warm orange detailing.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_11,
        name="Frame Type 11",
        description="Soft pink and lavender scallops with bright highlights.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_12,
        name="Frame Type 12",
        description="Dense black, gold, and green ornamental weave.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_13,
        name="Frame Type 13",
        description="Clean blue bands with small gold corner pins.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_14,
        name="Frame Type 14",
        description="Warm sand-colored edge with fine gold texture.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_15,
        name="Frame Type 15",
        description="White and lavender lace loops with a soft outline.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_16,
        name="Frame Type 16",
        description="Bold red, yellow, and blue geometric bands.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_17,
        name="Frame Type 17",
        description="Black and white braided edge with crisp contrast.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_18,
        name="Frame Type 18",
        description="Bright yellow border with blue dotted detailing.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_19,
        name="Frame Type 19",
        description="Fresh green leaf weave with white highlights.",
    ),
    InterfaceFrameDefinition(
        frame_type=FRAME_TYPE_20,
        name="Frame Type 20",
        description="Red and blue stitched edge with jeweled corners.",
    ),
)

SUPPORTED_FRAME_TYPES = tuple(
    definition.frame_type for definition in INTERFACE_FRAME_DEFINITIONS
)


def normalize_frame_type(value: object) -> int:
    try:
        frame_type = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FRAME_TYPE
    if frame_type not in SUPPORTED_FRAME_TYPES:
        return DEFAULT_FRAME_TYPE
    return frame_type


def get_interface_frame_definition(frame_type: object) -> InterfaceFrameDefinition:
    normalized = normalize_frame_type(frame_type)
    return next(
        definition
        for definition in INTERFACE_FRAME_DEFINITIONS
        if definition.frame_type == normalized
    )
