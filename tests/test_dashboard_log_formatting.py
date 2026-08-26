from __future__ import annotations

import unittest

from app.gui.dashboard_tab import compact_log_timestamp, format_dashboard_log_event


class DashboardLogFormattingTests(unittest.TestCase):
    def test_fractional_timestamp_is_limited_to_one_decimal(self) -> None:
        self.assertEqual(
            compact_log_timestamp("2026-08-26T16:32:46.987654Z"),
            "2026-08-26T16:32:46.9Z",
        )
        self.assertEqual(compact_log_timestamp("16:32:46"), "16:32:46")

    def test_recent_event_line_only_shows_hunt_focused_values(self) -> None:
        line = format_dashboard_log_event(
            {
                "timestamp": "2026-08-26T16:32:46.987654Z",
                "filter_name": "Wild",
                "filter_event_type": "encounter_start",
                "encounter_increment": 3,
                "hunt_encounter_count": 43,
                "last_match_score": 0.914,
                "session_number": 4,
                "counter": 103,
                "catch_counter": 2,
            }
        )

        self.assertEqual(
            line,
            "[2026-08-26T16:32:46.9Z] WILD [encounter_start] | +3 | "
            "Hunt encounters: 43 | Score: 0.9",
        )
        self.assertNotIn("session", line.lower())
        self.assertNotIn("all-time", line.lower())
        self.assertNotIn("catch", line.lower())
        self.assertNotIn("103", line)


if __name__ == "__main__":
    unittest.main()
