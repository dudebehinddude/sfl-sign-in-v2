"""Checks for instance isolation without starting Docker services."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

spec = importlib.util.spec_from_file_location("sfl_compose", Path(__file__).with_name("compose.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ComposeTests(unittest.TestCase):
    def make_env(self, folder, port):
        path = Path(folder) / f"{port}.env"
        path.write_text(
            f"APP_PORT={port}\nPOSTGRES_PASSWORD=test_only\nMINIO_ROOT_PASSWORD=storage_test_only\n"
        )
        return path

    def test_port_selects_separate_project_and_ignores_shell_override(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"APP_PORT": "9999", "COMPOSE_PROJECT_NAME": "production"}),
        ):
            _, one = module.compose_command(self.make_env(folder, 8080), ["config"])
            _, two = module.compose_command(self.make_env(folder, 8081), ["config"])
            self.assertEqual(one["COMPOSE_PROJECT_NAME"], "sfl-8080")
            self.assertEqual(two["COMPOSE_PROJECT_NAME"], "sfl-8081")
            self.assertNotEqual(one["COMPOSE_PROJECT_NAME"], two["COMPOSE_PROJECT_NAME"])

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is not installed")
    def test_rendered_compose_isolates_volumes_and_only_publishes_app(self):
        with tempfile.TemporaryDirectory() as folder:
            rendered = []
            for port in [8080, 8081]:
                command, env = module.compose_command(
                    self.make_env(folder, port), ["config", "--format", "json"]
                )
                result = subprocess.run(
                    command, env=env, check=True, capture_output=True, text=True
                )
                config = json.loads(result.stdout)
                self.assertEqual(config["name"], f"sfl-{port}")
                self.assertNotIn("ports", config["services"]["db"])
                self.assertNotIn("ports", config["services"]["api"])
                self.assertNotIn("ports", config["services"]["minio"])
                self.assertEqual(str(config["services"]["web"]["ports"][0]["published"]), str(port))
                self.assertEqual(
                    config["services"]["api"]["environment"]["PUBLIC_ORIGIN"],
                    f"http://localhost:{port}",
                )
                self.assertNotIn("cloudflared", config["services"])
                self.assertNotIn("adminer", config["services"])
                rendered.append(config)
            self.assertNotEqual(
                rendered[0]["volumes"]["postgres_data"]["name"],
                rendered[1]["volumes"]["postgres_data"]["name"],
            )
            self.assertNotEqual(
                rendered[0]["volumes"]["object_data"]["name"],
                rendered[1]["volumes"]["object_data"]["name"],
            )
            self.assertNotEqual(
                rendered[0]["networks"]["default"]["name"],
                rendered[1]["networks"]["default"]["name"],
            )

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is not installed")
    def test_development_frontend_has_one_port_and_no_integration_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            command, env = module.compose_command(
                self.make_env(folder, 8099), ["config", "--format", "json"], dev=True
            )
            result = subprocess.run(command, env=env, check=True, capture_output=True, text=True)
            config = json.loads(result.stdout)
            web = config["services"]["web"]
            self.assertEqual(web["build"]["target"], "development")
            self.assertEqual(web["environment"], {"SFL_DEV_BACKEND": "http://api:8000"})
            self.assertEqual(len(web["ports"]), 1)
            self.assertNotIn("ports", config["services"]["db"])
            self.assertNotIn("ports", config["services"]["minio"])

    def test_database_credentials_are_url_encoded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_env(folder, 8082)
            path.write_text(
                "APP_PORT=8082\nPOSTGRES_USER=sfl_test\nPOSTGRES_PASSWORD='a:@/#?%$b'\n"
            )
            _, env = module.compose_command(path, ["config"])
            parsed = urlsplit(env["SFL_DATABASE_URL"])
            self.assertEqual(parsed.hostname, "db")
            self.assertEqual(unquote(parsed.password), "a:@/#?%$b")
            self.assertEqual(parsed.path, "/sfl")

    def test_rejects_invalid_port_and_env_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_env(folder, 70000)
            with self.assertRaises(ValueError):
                module.compose_command(path, ["config"])
            path.write_text("APP_PORT=$(touch /not-executed)\n")
            with self.assertRaises(ValueError):
                module.read_env(path)


if __name__ == "__main__":
    unittest.main()
