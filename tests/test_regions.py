from __future__ import annotations

import unittest

from app.core.regions import clamp_region, expand_region


class RegionTests(unittest.TestCase):
    def test_expand_region_adds_padding_inside_bounds(self) -> None:
        expanded = expand_region(
            {"left": 100, "top": 80, "width": 40, "height": 20},
            padding=15,
            bounds_width=300,
            bounds_height=200,
        )
        self.assertEqual(
            expanded,
            {"left": 85, "top": 65, "width": 70, "height": 50},
        )

    def test_expand_region_clips_at_monitor_edges(self) -> None:
        expanded = expand_region(
            {"left": 2, "top": 3, "width": 20, "height": 10},
            padding=10,
            bounds_width=30,
            bounds_height=20,
        )
        self.assertEqual(
            expanded,
            {"left": 0, "top": 0, "width": 30, "height": 20},
        )

    def test_clamp_region_keeps_positive_size(self) -> None:
        clamped = clamp_region(
            {"left": 150, "top": -10, "width": 0, "height": 500},
            bounds_width=100,
            bounds_height=80,
        )
        self.assertEqual(
            clamped,
            {"left": 99, "top": 0, "width": 1, "height": 80},
        )


if __name__ == "__main__":
    unittest.main()
