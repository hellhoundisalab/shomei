import base64
import io
import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from gallery_build.builder import build
from gallery_build.form import form_files


class FormTests(unittest.TestCase):
    def test_form_is_static_separate_from_exhibition_previews_and_has_local_fonts(self):
        files = form_files()
        html = files["new/index.html"].decode()
        self.assertIn("connect-src 'none'", html)
        self.assertIn('id="files"', html)
        self.assertIn('id="export"', html)
        self.assertIn('id="background"', html)
        self.assertTrue(any(name.startswith("assets/form-fonts/") for name in files))
        self.assertNotIn("new/index.html", build([]))
        self.assertNotIn("fetch(", files["assets/form.js"].decode())

    @unittest.skipUnless(shutil.which("node"), "Node required for ZIP writer parity")
    def test_browser_zip_writer_crc_stored_files_and_paths(self):
        module = (
            Path(__file__).resolve().parents[1]
            / "src/gallery_build/form-assets/form-zip.js"
        )
        code = f"""import {{packageZip}} from {json.dumps(module.as_uri())};
const data={{photos:[{{file:'images/01.jpg'}}]}};
const zip=await packageZip(data,[new Blob(['sample bytes'])]);
console.log(Buffer.from(await zip.arrayBuffer()).toString('base64'));
"""
        run = subprocess.run(
            ["node", "--input-type=module", "-e", code],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(run.stdout))) as archive:
            self.assertEqual(archive.namelist(), ["manifest.json", "images/01.jpg"])
            self.assertEqual(archive.read("images/01.jpg"), b"sample bytes")
            self.assertTrue(
                all(
                    info.compress_type == zipfile.ZIP_STORED
                    for info in archive.infolist()
                )
            )
            self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
