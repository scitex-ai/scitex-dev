## Skills to Load (Required)
skill:scitex-versions
skill:speak-and-signature
skill:autonomous

## Task: Full Ecosystem Release

For each SciTeX package (skip scitex-cloud alpha unless requested):

1. **Check GitHub Actions** — verify latest CI passes before proceeding. If failures exist, report and offer to fix before push.
2. **Determine version bump** — count commits since last tag, check for `feat:` (minor) vs `fix:` (patch).
3. **Bump version** — edit pyproject.toml.
4. **Commit and tag** — `git commit` + `git tag vX.Y.Z`.
5. **Push** — `git push origin develop --tags`.
6. **GitHub Release** — `gh release create vX.Y.Z --generate-notes`.
7. **PyPI** — verify `publish-pypi.yml` triggered (check Actions).
8. **pip install -e** — local editable install.
9. **NAS sync** — `scitex dev versions sync --confirm --host nas`.

Use parallel subagents for independent packages. Present ecosystem summary table when done.

## Arguments
$ARGUMENTS

(If no arguments, process all packages with appropriate version increments)
