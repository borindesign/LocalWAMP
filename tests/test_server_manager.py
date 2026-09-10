from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from server_manager import ServerManager  # noqa: E402


class ApacheEnvironmentTests(unittest.TestCase):
    def test_apache_paths_precede_existing_windows_path(self) -> None:
        php_dir = Path("bin/php/php-current").resolve()
        apache_bin_dir = Path("bin/apache/apache-current/bin").resolve()

        with patch.dict(os.environ, {"PATH": r"C:\Windows\System32"}, clear=True):
            env = ServerManager._build_apache_environment(php_dir, apache_bin_dir)

        self.assertEqual(
            env["PATH"].split(os.pathsep),
            [str(php_dir), str(apache_bin_dir), r"C:\Windows\System32"],
        )

    def test_each_start_uses_the_new_selected_runtime_paths(self) -> None:
        old_php_dir = Path("bin/php/php-8.4.x").resolve()
        new_php_dir = Path("bin/php/php-8.5.x").resolve()
        old_apache_bin_dir = Path("bin/apache/apache-2.4.old/bin").resolve()
        new_apache_bin_dir = Path("bin/apache/apache-2.4.new/bin").resolve()

        with patch.dict(os.environ, {"PATH": r"C:\Windows"}, clear=True):
            old_env = ServerManager._build_apache_environment(old_php_dir, old_apache_bin_dir)
            new_env = ServerManager._build_apache_environment(new_php_dir, new_apache_bin_dir)

        self.assertEqual(old_env["PATH"].split(os.pathsep)[:2], [str(old_php_dir), str(old_apache_bin_dir)])
        self.assertEqual(new_env["PATH"].split(os.pathsep)[:2], [str(new_php_dir), str(new_apache_bin_dir)])
        self.assertNotIn(str(old_php_dir), new_env["PATH"].split(os.pathsep))
        self.assertNotIn(str(old_apache_bin_dir), new_env["PATH"].split(os.pathsep))

    def test_caller_environment_overrides_are_preserved(self) -> None:
        php_dir = Path("bin/php/php-current").resolve()
        apache_bin_dir = Path("bin/apache/apache-current/bin").resolve()

        with patch.dict(os.environ, {"PATH": r"C:\Windows", "SYSTEMROOT": r"C:\Windows"}, clear=True):
            env = ServerManager._build_apache_environment(
                php_dir,
                apache_bin_dir,
                {"PATH": r"D:\CustomBin", "LOCALPHP_TEST": "enabled"},
            )

        self.assertEqual(
            env["PATH"].split(os.pathsep),
            [str(php_dir), str(apache_bin_dir), r"D:\CustomBin"],
        )
        self.assertEqual(env["LOCALPHP_TEST"], "enabled")
        self.assertEqual(env["SYSTEMROOT"], r"C:\Windows")


if __name__ == "__main__":
    unittest.main()
