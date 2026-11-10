#!/usr/bin/env python3
"""Authenticated local handoff. Never runs in public CI and never publishes."""
import argparse
import json
import pathlib
import subprocess
import tempfile
from candidate import MANIFEST, PACKAGES, PUBLIC_REPO, SOURCE_REPO, download, gh_json, require


def verify_run(run, manifest):
    v = manifest["verification"]
    require(run["status"] == "completed" and run["conclusion"] == "success", "private verification did not pass")
    require(run["path"] == v["workflow"] and run["event"] == "workflow_dispatch" and run["head_branch"] == "master",
            "wrong private verification workflow/event/branch")
    require(run["id"] == v["run_id"] and run["run_attempt"] == v["run_attempt"] and
            run["head_sha"] == manifest["source_sha"], "source/run identity mismatch")
    require(run["repository"]["full_name"] == SOURCE_REPO, "wrong private repository")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--manifest-sha256", required=True, help="SHA-256 reviewed in private CI logs")
    parser.add_argument("--stage", action="store_true", help="Create a public-repository DRAFT, never a published release")
    args = parser.parse_args()
    require(args.run_id > 0, "invalid run ID")
    run = gh_json(f"repos/{SOURCE_REPO}/actions/runs/{args.run_id}")
    require(run["status"] == "completed" and run["conclusion"] == "success", "private verification did not pass")
    tag = f"sdk-candidate-{args.run_id}-{run['run_attempt']}"
    # Draft releases are not returned reliably by the tag endpoint; list them.
    releases = gh_json(f"repos/{SOURCE_REPO}/releases?per_page=100")
    matches = [r for r in releases if r["tag_name"] == tag and r["draft"]]
    require(len(matches) == 1, "expected one private draft candidate among the latest 100 releases")
    with tempfile.TemporaryDirectory(prefix="sdk-handoff-") as work:
        directory = pathlib.Path(work) / "candidate"
        manifest = download(SOURCE_REPO, matches[0]["id"], directory, args.manifest_sha256)
        verify_run(run, manifest)
        print(json.dumps(manifest, indent=2))
        if not args.stage:
            print("Verified only. Add --stage after archive review to create the public repository draft.")
            return
        # Literal, fixed filenames only. No source checkout, fixtures, logs, or credentials leave Platform.
        notes = ("Verified SDK candidate; NOT a published registry release.\n\n"
                 f"Manifest SHA-256: `{args.manifest_sha256}`\n\n"
                 f"Source SHA: `{manifest['source_sha']}`\n\n"
                 f"Private verification: https://github.com/{SOURCE_REPO}/actions/runs/{args.run_id}\n")
        body = json.dumps({"tag_name": tag, "target_commitish": "main", "name": "SDK 0.1.0 candidate",
                           "body": notes, "draft": True, "prerelease": True})
        created = json.loads(subprocess.check_output(["gh", "api", f"repos/{PUBLIC_REPO}/releases",
                                                      "-X", "POST", "--input", "-"], input=body.encode()))
        upload = created["upload_url"].split("{")[0]
        for name in sorted(PACKAGES | {MANIFEST}):
            subprocess.run(["gh", "api", upload + "?name=" + name, "-X", "POST",
                            "-H", "Content-Type: application/octet-stream", "--input", str(directory / name)],
                           stdout=subprocess.DEVNULL, check=True)
        print(f"Draft release ID: {created['id']}; reviewed manifest SHA-256: {args.manifest_sha256}")
        print("No publishing workflow was dispatched. Request approval separately after review.")


if __name__ == "__main__":
    main()
