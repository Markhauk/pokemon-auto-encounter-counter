from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.config_service import CONFIG_VERSION, ConfigService


class ConfigMigrationTests(unittest.TestCase):
    def test_version_upgrade_keeps_original_config_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            original = json.dumps({"version": 6, "encounter_increment": 9}, indent=2)
            config_path.write_text(original, encoding="utf-8")

            with patch("app.services.config_service._read_physical_monitors", return_value=[]):
                migrated = ConfigService(config_path=config_path).load()

            backup = (
                root
                / "output"
                / "migration_backups"
                / f"config_v6_to_v{CONFIG_VERSION}"
                / "config.json"
            )
            self.assertEqual(backup.read_text(encoding="utf-8"), original)
            self.assertEqual(migrated["version"], CONFIG_VERSION)
            self.assertEqual(migrated["encounter_increment"], 9)


if __name__ == "__main__":
    unittest.main()
