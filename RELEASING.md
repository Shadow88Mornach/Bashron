# Releasing bashron

bashron publishes to PyPI automatically when you push a `v*` tag to GitHub.
This document describes the one-time setup and the recurring release flow.

## How it works (in one sentence)

A GitHub Actions workflow (`.github/workflows/release.yml`) triggers on
`v*` tags, builds the package with `uv`, and publishes to PyPI using
**Trusted Publishing** (OIDC). **No PyPI API tokens are stored anywhere** —
not in GitHub Secrets, not in environment variables, not in your shell.

## One-time setup

You only do this once per project, in a browser, in about two minutes.

### 1. Create a PyPI "pending publisher"

1. Sign in to <https://pypi.org> with the account that will own the project.
2. Go to <https://pypi.org/manage/account/publishing/>.
3. Click **Add a new pending publisher**.
4. Fill in:

   | Field              | Value                      |
   |--------------------|----------------------------|
   | PyPI Project Name  | `bashron`                  |
   | Owner              | `shadowmornachAsia`        |
   | Repository name    | `Bashron`                  |
   | Workflow name      | `release.yml`              |
   | Environment name   | `pypi`                     |

5. Click **Add**.

PyPI now trusts any upload signed by the `release.yml` workflow in
`shadowmornachAsia/Bashron` that runs in the `pypi` environment.

### 2. Create the `pypi` environment on GitHub (optional but recommended)

This gives you the option to add a manual approval gate before every release.

1. Go to <https://github.com/shadowmornachAsia/Bashron/settings/environments>.
2. Click **New environment**.
3. Name it `pypi` (must match the `environment.name` field in `release.yml`).
4. (Optional) Under **Deployment protection rules**, check
   **Required reviewers** and add yourself. This makes every release wait
   for a one-click approval in the GitHub UI — a great safety net.

### 3. Revoke the old PyPI tokens

If you previously created PyPI API tokens (for manual `uv publish`), delete
them now — you will never need them again.

- <https://pypi.org/manage/account/token/>
- <https://test.pypi.org/manage/account/token/>

## Releasing a new version

Once setup is done, every release is three commands:

```bash
# 1. Bump the version in pyproject.toml AND src/bashron/__init__.py.
#    They MUST match — the workflow verifies this and fails if they drift.
#    Also add an entry to CHANGELOG.md under a new version heading.

# 2. Commit the bump and push.
git add pyproject.toml src/bashron/__init__.py uv.lock CHANGELOG.md
git commit -m "Release v0.1.2"
git push

# 3. Tag and push the tag.
git tag v0.1.2
git push origin v0.1.2
```

GitHub Actions then:
1. Runs the full test suite on Python 3.9–3.13.
2. Verifies the tag matches the version in `pyproject.toml`.
3. Builds `dist/bashron-0.1.2-py3-none-any.whl` and `dist/bashron-0.1.2.tar.gz`.
4. Runs `twine check` on both artifacts.
5. Publishes to PyPI using an OIDC token signed by GitHub.

You can watch it happen live at
<https://github.com/shadowmornachAsia/Bashron/actions>.

Within ~90 seconds of the tag push, `uv tool install bashron==0.1.2`,
`pipx install bashron==0.1.2`, and `pip install bashron==0.1.2` all work.

## If something goes wrong

- **The workflow fails with "tag does not match pyproject.toml version"** —
  you forgot to bump `pyproject.toml` or `src/bashron/__init__.py`. Fix it,
  delete the tag locally and on GitHub, retag with the correct version.

  ```bash
  git tag -d v0.1.2
  git push origin :refs/tags/v0.1.2
  # ...fix the version...
  git tag v0.1.2 && git push origin v0.1.2
  ```

- **The publish step fails with "OIDC credential is not authorized"** —
  the PyPI trusted publisher configuration does not match what the workflow
  is sending. Double-check the five fields in step 1 of the setup above.
  The `Workflow name` must be exactly `release.yml`, the `Environment name`
  must match the `environment.name` in `release.yml` exactly.

- **Tests fail in CI but pass locally** — usually a Python version
  incompatibility. The CI matrix runs 3.9–3.13; if your local is only 3.13,
  older versions may behave differently. Fix the code, not the CI matrix.

- **The package version needs to change after a failed publish** — you can
  never reuse a version number on PyPI. Bump to the next patch and re-release.
