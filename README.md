# Anchras SDK releases

Release tooling for the handwritten `@anchras/sdk` and `anchras` sandbox
clients. Platform remains private. This repository contains no Platform source
checkout or private-source credentials. Its presence does not imply registry
publication, live-server compatibility, or availability beyond recorded evidence.

## Human approval and storage

Candidate archives live in **draft GitHub Releases**, not Actions artifacts.
The PyPI publisher uses the `sdk-pypi` environment with Dieter as required
reviewer, prevent self-review enabled, administrator bypass disabled, and only
`main` allowed. Never remove those protections to make a run proceed.

Only the request workflow has `actions: write`; it validates the candidate and
dispatches the publisher using GitHub's automation identity. The separately
dispatched publisher requires `github-actions[bot]` as its actor and waits for
the human environment approval. Agents may prepare/request a release but must
never approve it. Only the protected publisher has PyPI OIDC permission.

Both jobs validate the reviewed manifest digest and every archive digest. The
publisher downloads the candidate again **after** approval, preventing a changed
draft asset from changing the approved package. Neither public job builds or
executes package contents. Publication is limited to 0.1.0; later versions require
reviewed changes to the filename/metadata checks.

## Publisher setup (before any real publish)

1. Review and merge the tooling PRs here and in private Platform.
2. Verify the `sdk-pypi` environment protections above, including `main` only.
3. In [PyPI account Publishing](https://pypi.org/manage/account/publishing/),
   register pending project `anchras` for GitHub owner `Anchras`, repository
   `sdk-releases`, workflow **`sdk-pypi-publish.yml`**, environment **`sdk-pypi`**.
   Remove the obsolete pending publisher for the private repository. A pending
   publisher does not reserve the package name. No long-lived PyPI API token is
   needed or should be added here.
4. Keep npm first publication manual, with the established organization owner
   and publishing 2FA. This repository does not automate npm publication.

## Prepare and stage a candidate

In Platform, manually dispatch `sdk-release-prepare.yml` on `master`. It tests
installed archives on Node 18/22 and Python 3.9/3.13, then uploads the selected
Node 22 tarball, Python 3.13 wheel/sdist, and `release-manifest.json` into a private
draft Release. Require the entire run to complete successfully. Review the
source revision, tests, package contents and manifest SHA-256 from that run.

Run the local staging tool with a GitHub account authorized to read Platform:

```sh
python3 scripts/stage.py --run-id RUN_ID --manifest-sha256 REVIEWED_SHA256
# Only after reviewing the successful private run and exact archives:
python3 scripts/stage.py --run-id RUN_ID --manifest-sha256 REVIEWED_SHA256 --stage
```

The first command verifies only. `--stage` creates a draft in this repository;
it neither publishes that release nor dispatches registry publication. It copies
only three fixed distribution filenames and the manifest. It never copies
Platform's source checkout, CI logs, test fixtures, or credentials. A failed or
partial upload leaves a draft that cannot pass the exact-file-set validation.

The manifest identifies the private source revision and successful verification
run/attempt and binds all three archive hashes. The staging tool validates that
private run using the operator's existing authenticated `gh` session. Public CI
does **not** independently access that run: the human reviewer must check the
private source evidence. No public-source build-provenance claim is made.

## Rehearse approval, then request publication

After reviewing the workflow and staging the candidate, request a rehearsal:

```sh
gh workflow run request-sdk-release.yml --repo Anchras/sdk-releases --ref main \
  -f release_id=DRAFT_RELEASE_ID -f manifest_sha256=REVIEWED_SHA256 \
  -f publish_release=false
```

Confirm the separately dispatched `Publish reviewed Python SDK` run is initiated
as `github-actions[bot]` and waits for Dieter's required approval. Dieter approves
this rehearsal in GitHub's deployment review UI. It verifies the candidate
without contacting PyPI. If the actor is wrong or the gate does not wait, stop
and repair the reviewed implementation; do not disable prevent self-review.

For the real release, use the same command with `publish_release=true`. It still
requires Dieter's approval. Review the private successful run, source revision,
manifest SHA-256 and archive hashes before approving. Direct human dispatches
of `sdk-pypi-publish.yml` are intentionally skipped; use the request workflow.

The PyPI action publishes exactly the reviewed wheel and sdist, without rebuilding.
Publish npm manually from the **same reviewed tarball** using the established
human authorization/2FA process:

```sh
npm publish /path/to/reviewed/anchras-sdk-0.1.0.tgz --access public
```

Do not publish the draft GitHub Release or either registry until the explicit
release authorization conditions are satisfied. After publication, retain real
registry version links, publisher/attestation receipts, clean exact-version
install/import/API-fixture results, and separately any approved live-server
compatibility evidence. Update documentation only from those actual receipts.

## Tooling validation

```sh
python3 -m unittest discover -s tests -v
actionlint .github/workflows/*.yml
```
