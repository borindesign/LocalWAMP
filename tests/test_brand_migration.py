from pathlib import Path
import sys
import shutil
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from configure_apache_php import configure_apache_php

class ApacheBrandMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.temp_parent / f"localwamp-test-{uuid.uuid4().hex}"
        # Inherit the writable parent's ACL in restricted Windows environments.
        self.root.mkdir()
        self.addCleanup(self.remove_fixture)

    def remove_fixture(self) -> None:
        if self.root.resolve().parent != self.temp_parent:
            raise ValueError("Test fixture must stay inside its temporary parent")
        shutil.rmtree(self.root)

    def check_migration(self, brands: tuple[str, ...]) -> None:
        root = self.root
        php = root / "php"
        php.mkdir()
        (php / "php8apache2_4.dll").touch()
        (php / "php.ini").touch()
        conf = root / "httpd.conf"
        content = "Listen 8080\n# Keep my custom configuration\n"
        for brand in brands:
            content += (
                f"# {brand} DocumentRoot start\n"
                'DocumentRoot "D:/custom-projects"\n'
                '<Directory "D:/custom-projects">\nRequire all granted\n</Directory>\n'
                f"# {brand} DocumentRoot end\n"
                f"# {brand} PHP configuration start\n"
                'LoadModule php_module "old/php8apache2_4.dll"\nPHPIniDir "old/php"\n'
                "AddHandler application/x-httpd-php .php\n"
                f"# {brand} PHP configuration end\n"
                f"# {brand} DirectoryIndex start\nDirectoryIndex index.php\n"
                f"# {brand} DirectoryIndex end\n"
                f"# {brand} phpMyAdmin start\nAlias /phpmyadmin old/phpmyadmin\n"
                f"# {brand} phpMyAdmin end\n"
            )
        conf.write_text(content, encoding="utf-8")
        configure_apache_php(conf, php, root / "projects", root, 8080)
        first = conf.read_text(encoding="utf-8")
        configure_apache_php(conf, php, root / "projects", root, 8080)
        second = conf.read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertNotIn("# LocalPHP", second)
        self.assertNotIn("D:/custom-projects", second)
        self.assertNotIn("Alias /phpmyadmin", second)
        self.assertIn("# Keep my custom configuration", second)
        self.assertEqual(second.count("# LocalWAMP DocumentRoot start"), 1)
        self.assertEqual(second.count("LoadModule php_module"), 1)
        self.assertEqual(sum(line.startswith("DirectoryIndex ") for line in second.splitlines()), 1)
        self.assertIn(f'DocumentRoot "{(root / "projects").as_posix()}"', second)

    def test_legacy_configuration_is_migrated(self) -> None:
        self.check_migration(("LocalPHP",))

    def test_current_configuration_is_idempotent(self) -> None:
        self.check_migration(("LocalWAMP",))

    def test_mixed_duplicate_blocks_are_removed(self) -> None:
        self.check_migration(("LocalPHP", "LocalWAMP", "LocalPHP"))

if __name__ == "__main__":
    unittest.main()
