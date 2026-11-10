#!/usr/bin/env python3
"""Validate fixed-version SDK candidates without executing their contents."""
import argparse
import email
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tarfile
import zipfile

VERSION = "0.1.0"
PACKAGES = {"anchras-sdk-0.1.0.tgz", "anchras-0.1.0-py3-none-any.whl", "anchras-0.1.0.tar.gz"}
MANIFEST = "release-manifest.json"
RUNTIMES = ["node18", "node22", "python3.9", "python3.13"]
PUBLIC_REPO = "Anchras/sdk-releases"
SOURCE_REPO = "Anchras/Platform"
LIMIT = 5 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gh_json(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint]))


def validate(directory, expected):
    directory = pathlib.Path(directory)
    require(re.fullmatch(r"[0-9a-f]{64}", expected), "invalid reviewed manifest SHA-256")
    require({p.name for p in directory.iterdir()} == PACKAGES | {MANIFEST}, "unexpected candidate files")
    for path in directory.iterdir():
        require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= LIMIT,
                "invalid candidate file")
    path = directory / MANIFEST
    require(path.stat().st_size <= 16384, "oversized manifest")
    require(sha256(path) == expected, "reviewed manifest hash mismatch")
    m = json.loads(path.read_bytes())
    require(set(m) == {"schema", "version", "source_repository", "source_sha", "verification", "files"},
            "unexpected manifest schema")
    require(m["schema"] == 1 and m["version"] == VERSION and m["source_repository"] == SOURCE_REPO,
            "wrong package/source")
    require(re.fullmatch(r"[0-9a-f]{40}", m["source_sha"]), "invalid source SHA")
    v = m["verification"]
    require(set(v) == {"workflow", "run_id", "run_attempt", "runtimes"}, "invalid verification receipt")
    require(v["workflow"] == ".github/workflows/sdk-release-prepare.yml" and v["runtimes"] == RUNTIMES,
            "wrong verification workflow or runtime matrix")
    require(all(type(v[k]) is int and v[k] > 0 for k in ("run_id", "run_attempt")), "invalid run identity")
    require(set(m["files"]) == PACKAGES, "wrong distribution set")
    for name, digest in m["files"].items():
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid file digest")
        require(sha256(directory / name) == digest, "distribution hash mismatch: " + name)
    for name in ("anchras-sdk-0.1.0.tgz", "anchras-0.1.0.tar.gz"):
        with tarfile.open(directory / name) as archive:
            members = archive.getmembers()
            require(len(members) < 1024 and sum(p.size for p in members) < 20 * LIMIT, "oversized archive")
            for p in members:
                require(not p.issym() and not p.islnk() and (p.isfile() or p.isdir()), "unsafe archive entry")
                require(not p.name.startswith("/") and ".." not in pathlib.PurePosixPath(p.name).parts,
                        "unsafe archive path")
            if name.endswith(".tgz"):
                require(all(p.name.startswith("package/") for p in members), "wrong npm archive root")
                pkg = json.load(archive.extractfile("package/package.json"))
                require(pkg["name"] == "@anchras/sdk" and pkg["version"] == VERSION, "wrong npm metadata")
                require("package/LICENSE" in archive.getnames(), "missing npm license")
            else:
                require(all(p.name.startswith("anchras-0.1.0/") for p in members), "wrong sdist root")
                metadata = email.message_from_bytes(archive.extractfile("anchras-0.1.0/PKG-INFO").read())
                require(metadata["Name"] == "anchras" and metadata["Version"] == VERSION, "wrong sdist metadata")
                require("anchras-0.1.0/LICENSE" in archive.getnames(), "missing sdist license")
    with zipfile.ZipFile(directory / "anchras-0.1.0-py3-none-any.whl") as archive:
        require(len(archive.infolist()) < 1024 and sum(p.file_size for p in archive.infolist()) < 20 * LIMIT,
                "oversized wheel")
        names = archive.namelist()
        require(all(not n.startswith("/") and ".." not in pathlib.PurePosixPath(n).parts for n in names),
                "unsafe wheel path")
        metadata = email.message_from_bytes(archive.read("anchras-0.1.0.dist-info/METADATA"))
        require(metadata["Name"] == "anchras" and metadata["Version"] == VERSION, "wrong wheel metadata")
        require("anchras/py.typed" in names and any(n.endswith("/LICENSE") for n in names),
                "missing wheel typing marker/license")
    return m


def download(repository, release_id, directory, expected):
    require(repository in (PUBLIC_REPO, SOURCE_REPO), "unexpected repository")
    require(type(release_id) is int and release_id > 0, "invalid release ID")
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    release = gh_json(f"repos/{repository}/releases/{release_id}")
    require(release["draft"] is True, "candidate must be a draft release")
    assets = release["assets"]
    require(len(assets) == 4 and {a["name"] for a in assets} == PACKAGES | {MANIFEST}, "wrong release assets")
    for asset in assets:
        require(type(asset["id"]) is int and 0 < asset["size"] <= LIMIT, "invalid release asset")
        output = directory / asset["name"]
        with output.open("xb") as target:
            subprocess.run(["gh", "api", f"repos/{repository}/releases/assets/{asset['id']}",
                            "-H", "Accept: application/octet-stream"], stdout=target, check=True)
        require(output.stat().st_size == asset["size"], "incomplete release asset")
    manifest = validate(directory, expected)
    v = manifest["verification"]
    require(release["tag_name"] == f"sdk-candidate-{v['run_id']}-{v['run_attempt']}", "wrong candidate tag")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", required=True, type=int)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--directory", required=True, type=pathlib.Path)
    parser.add_argument("--python-dist", type=pathlib.Path)
    args = parser.parse_args()
    m = download(PUBLIC_REPO, args.release_id, args.directory, args.manifest_sha256)
    print(json.dumps(m, indent=2))
    if args.python_dist:
        args.python_dist.mkdir(parents=True, exist_ok=False)
        for name in ("anchras-0.1.0-py3-none-any.whl", "anchras-0.1.0.tar.gz"):
            shutil.copyfile(args.directory / name, args.python_dist / name)


if __name__ == "__main__":
    main()
