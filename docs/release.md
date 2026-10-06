# Publishing a version

How a new SwitchPilot version reaches users: a git tag builds, tests and publishes the Docker
image, then the GitHub release. Everything runs in GitHub Actions (`.github/workflows/ci.yml`).

## Every time

1. Set the version in the four places that carry it (`backend/tests/test_version.py` checks they
   agree):
   - `backend/version.py`
   - `frontend/package.json`
   - the badge at the top of `README.md`
   - a new `## [X.Y.Z] - YYYY-MM-DD` section at the top of `CHANGELOG.md`: it becomes the release
     notes
2. Commit and push to `master`, and wait for the CI run to be green (tests, page build, image build
   for amd64 and arm64).
3. Tag that commit and push the tag:

   ```bash
   git tag v2.3.0
   git push origin v2.3.0
   ```

4. The tag's CI run then:
   - checks the tag matches `backend/version.py` (else it stops, nothing published);
   - runs the tests again and builds the image for amd64 and arm64;
   - refuses to publish a version that is already published (a tag is never rebuilt);
   - pushes `ghcr.io/altzone/switchpilot:X.Y.Z`. `X.Y`, `X` and `latest` move to it only if it is
     the newest version of their line: a 2.2.2 fix published after 2.3.0 does not move `2` or
     `latest`, so nobody is sent back to 2.2;
   - creates the GitHub release `vX.Y.Z` with the CHANGELOG section as notes, only once the image
     is published.

A failed run publishes nothing that is wrong:
- **Failed before the image was published** (tests, version check, build): fix, then delete and
  push the tag again (`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`, then tag again).
- **Image published, release job failed:** re-run only that job from the Actions page (**Re-run
  failed jobs**). Do not push the tag again: the image step refuses a version that is already
  published.
- **Something wrong in a published version:** publish the fix as the next version.

A fix for an older line (2.2.2 after 2.3.0, say) is tagged on a branch made from that line's tag.
That branch needs this workflow (2.3.0 or later); for an older line, add `.github/` from master to
it first.

## Once, after the first published version

On GitHub, **Your profile → Packages → switchpilot → Package settings**:
- **Change visibility → Public**, so anyone can pull it without logging in. GitHub does not allow
  turning a public package back to private.
- Check that the package shows **altzone/xike_manager** as its repository (the image's
  `org.opencontainers.image.source` label links it).

Then check a pull from a machine that is not logged in to GitHub:
`docker pull ghcr.io/altzone/switchpilot:2`.

Also, in the repository's **Settings → Actions → General**, Actions must be allowed (the default).
