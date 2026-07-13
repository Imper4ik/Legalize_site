from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


class ReleaseScriptTests(SimpleTestCase):
    def test_render_blueprint_uses_docker_release_and_readiness(self):
        blueprint = (Path(__file__).resolve().parents[2] / "render.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("preDeployCommand: bash release.sh", blueprint)
        self.assertIn("runtime: docker", blueprint)
        self.assertIn("dockerfilePath: ./Dockerfile", blueprint)
        self.assertIn("healthCheckPath: /readyz/", blueprint)

    def test_release_script_syntax_is_valid(self):
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is required to validate release.sh syntax")

        script = Path(__file__).resolve().parents[2] / "release.sh"
        result = subprocess.run(
            [bash, "-n", str(script)],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_script_skips_translation_import_when_tooling_is_disabled(self):
        script = (Path(__file__).resolve().parents[2] / "release.sh").read_text(encoding="utf-8")

        self.assertIn('case "${ENABLE_TRANSLATION_TOOLING:-False}" in', script)
        self.assertIn('python manage.py import_po_to_db "${translation_import_args[@]}"', script)
        self.assertIn("Skipping import_po_to_db because ENABLE_TRANSLATION_TOOLING is disabled.", script)
        self.assertIn("TRANSLATION_IMPORT_ARGS", script)
