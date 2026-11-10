import copy
import hashlib
import io
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import candidate
from stage import verify_run


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name)
        self.tar("anchras-sdk-0.1.0.tgz", {
            "package/package.json": json.dumps({"name": "@anchras/sdk", "version": "0.1.0"}),
            "package/LICENSE": "Apache-2.0",
        })
        self.tar("anchras-0.1.0.tar.gz", {
            "anchras-0.1.0/PKG-INFO": "Name: anchras\nVersion: 0.1.0\n",
            "anchras-0.1.0/LICENSE": "Apache-2.0",
        })
        with zipfile.ZipFile(self.path / "anchras-0.1.0-py3-none-any.whl", "w") as z:
            z.writestr("anchras-0.1.0.dist-info/METADATA", "Name: anchras\nVersion: 0.1.0\n")
            z.writestr("anchras-0.1.0.dist-info/licenses/LICENSE", "Apache-2.0")
            z.writestr("anchras/py.typed", "")
        self.m = {"schema": 1, "version": "0.1.0", "source_repository": "Anchras/Platform",
                  "source_sha": "a" * 40,
                  "verification": {"workflow": ".github/workflows/sdk-release-prepare.yml",
                                   "run_id": 123, "run_attempt": 1, "runtimes": candidate.RUNTIMES.copy()},
                  "files": {n: candidate.sha256(self.path / n) for n in candidate.PACKAGES}}
        self.write_manifest()

    def tar(self, name, files):
        with tarfile.open(self.path / name, "w:gz") as t:
            for name, contents in files.items():
                contents = contents.encode()
                info = tarfile.TarInfo(name)
                info.size = len(contents)
                t.addfile(info, io.BytesIO(contents))

    def write_manifest(self):
        (self.path / candidate.MANIFEST).write_text(json.dumps(self.m))
        self.digest = candidate.sha256(self.path / candidate.MANIFEST)

    def test_valid_candidate(self):
        self.assertEqual(candidate.validate(self.path, self.digest), self.m)

    def test_manifest_replacement_rejected(self):
        self.m["source_sha"] = "b" * 40
        (self.path / candidate.MANIFEST).write_text(json.dumps(self.m))
        with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
            candidate.validate(self.path, self.digest)

    def test_archive_replacement_rejected(self):
        (self.path / "anchras-sdk-0.1.0.tgz").write_bytes(b"replacement")
        with self.assertRaisesRegex(ValueError, "distribution hash mismatch"):
            candidate.validate(self.path, self.digest)

    def test_extra_private_file_rejected(self):
        (self.path / "internal-source.txt").write_text("must not transfer")
        with self.assertRaisesRegex(ValueError, "unexpected candidate files"):
            candidate.validate(self.path, self.digest)

    def test_incomplete_runtime_matrix_rejected(self):
        self.m["verification"]["runtimes"].pop()
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "runtime matrix"):
            candidate.validate(self.path, self.digest)

    def test_archive_path_traversal_rejected_even_with_matching_hash(self):
        name = "anchras-sdk-0.1.0.tgz"
        self.tar(name, {"../escape": "bad"})
        self.m["files"][name] = candidate.sha256(self.path / name)
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "unsafe archive path"):
            candidate.validate(self.path, self.digest)

    def test_private_ci_receipt_must_match_success_and_source(self):
        v = self.m["verification"]
        run = {"status": "completed", "conclusion": "success", "path": v["workflow"],
               "event": "workflow_dispatch", "head_branch": "master", "id": 123, "run_attempt": 1,
               "head_sha": self.m["source_sha"], "repository": {"full_name": candidate.SOURCE_REPO}}
        verify_run(run, self.m)
        for key, wrong in [("conclusion", "failure"), ("head_sha", "b" * 40),
                           ("event", "pull_request"), ("run_attempt", 2)]:
            changed = copy.deepcopy(run)
            changed[key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_run(changed, self.m)


if __name__ == "__main__":
    unittest.main()
