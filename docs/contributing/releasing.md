# Releasing

CoolPlot is published in two places: PyPI (`pip install coolplot`),
uploaded by this repository's release workflow, and conda-forge
(`conda install -c conda-forge coolplot`), built from a separate
repository, the feedstock, that follows PyPI. A release goes to PyPI
first; conda-forge picks it up from there.

## Checklist

Before:

- [ ] Every change of the release is merged into master, and CI on
      master is green.
- [ ] `CHANGELOG.md`: the `[Unreleased]` section becomes the version with
      its date, and a new, empty `[Unreleased]` goes above it.
- [ ] `docs/upgrade.md` says what to change in your code, if a change
      needs it.
- [ ] `src/coolplot/__version__.py`: `VERSION` names the new version.
- [ ] A change of the dependencies in `pyproject.toml` (a new minimum
      `coolprop` or `numpy`, a new Python version) is noted for the
      conda-forge recipe, see below.
- [ ] Optional: a rehearsal on TestPyPI (Actions tab, "release", "Run
      workflow").

Release:

- [ ] Merge the pull request "Release X.Y.Z" with the version and the
      changelog.
- [ ] Tag the merge commit `vX.Y.Z` and push the tag (below).
- [ ] The release workflow passes: tests, build, PyPI upload, GitHub
      release.

After:

- [ ] `pip install coolplot==X.Y.Z` in a fresh environment installs it
      and draws a chart.
- [ ] The documentation of the tag is on Read the Docs.
- [ ] conda-forge: merge the version pull request on the feedstock once
      its CI is green (usually within a day of the PyPI upload).
- [ ] `conda install -c conda-forge coolplot=X.Y.Z` installs it (about an
      hour after the merge).

## PyPI

A release is a version tag. Pushing a tag such as `v1.0.0` starts the
workflow `.github/workflows/release.yml`, which:

1. runs the whole test workflow (`tests.yml`: five Python versions,
   coolplot-core, the package build and the documentation);
2. builds the sdist and the wheel, checks them with `twine check`, and
   stops if the tag does not name the version that was built;
3. installs the wheel in a fresh environment and draws a chart with it;
4. uploads both files to PyPI;
5. creates a GitHub release with the same files, marked as a pre-release
   for versions such as `1.1.0rc1`.

Nothing is uploaded unless every step before it passed.

### Make a release

```bash
# 1. Set the version and date the changelog in a pull request
#    "Release 1.1.0", and merge it into master once CI is green
#    src/coolplot/__version__.py:  VERSION = (1, 1, 0, '')
#    CHANGELOG.md:                 the section of this version

# 2. Tag the merge commit on master; the tag starts the release
git switch master && git pull --ff-only
git tag -a v1.1.0 -m "CoolPlot 1.1.0"
git push origin v1.1.0
```

Push the one tag by name, never `git push --tags`: that also pushes any
other tag in your clone, and a stray `v*` tag starts a release. Follow the
run on the Actions tab. A release candidate works the same way with
`VERSION = (1, 1, 0, 'rc1')` and the tag `v1.1.0rc1`.

After the release: `pip install coolplot==1.1.0` installs it, and the
version shows on Read the Docs. The repository's webhook tells Read the
Docs about the new tag, which builds it without a step by hand
(`https://coolplot.readthedocs.io/en/v1.1.0/`).

To rehearse without publishing, start the workflow by hand: Actions tab,
"release", "Run workflow", on the branch to try. It runs the same steps
and uploads to TestPyPI instead (a version already there is skipped), and
makes no GitHub release.

### When something fails

* Tests or the build fail: nothing was uploaded. Fix the problem on
  master, move the tag to the new commit
  (`git tag -d v1.1.0 && git push origin :refs/tags/v1.1.0`, then tag and
  push again).
* "Tag ... does not match the version that was built": the tag and
  `VERSION` disagree. Fix one of them and tag again as above.
* The upload to PyPI fails after the tests passed: usually the trusted
  publisher is not set up (below). Re-run the failed jobs from the run's
  page once it is.
* PyPI never accepts the same version twice, even after a release is
  deleted there. A release with a mistake is followed by a new version
  (1.1.1), not replaced.

### One-time setup

The workflow uploads with PyPI's trusted publishing: PyPI accepts uploads
from this workflow file in this repository, and no password or token is
stored in GitHub. A maintainer of the PyPI project registers it once:

1. On pypi.org, project CoolPlot, "Manage", "Publishing", add a GitHub
   publisher: owner `CoolProp`, repository `CoolPlot`, workflow
   `release.yml`, environment `pypi`.
2. The same on test.pypi.org with environment `testpypi` (only needed for
   rehearsals).
3. In the GitHub repository settings, "Environments", create `pypi` and
   `testpypi`. Adding required reviewers to `pypi` makes every upload wait
   for a person's approval on the run's page.

The documentation on Read the Docs is built from the repository by Read
the Docs itself (`.readthedocs.yaml`) and needs no step here.

## conda-forge

conda-forge builds its packages from one repository per package, the
feedstock (`conda-forge/coolplot-feedstock`), which holds the recipe:
where the source is, the dependencies and the tests. Its maintainers are
the people listed in the recipe; they need no rights in conda-forge
otherwise. CoolPlot is pure Python, so the recipe is `noarch: python`
and builds one package for every platform and Python version.

The first submission is under review
(https://github.com/conda-forge/staged-recipes/pull/35603), see the end
of this section. Until it is merged there is no feedstock: a new version
is put into that pull request by hand (version and sha256 of the sdist).

### Every release

1. Release on PyPI as above. The feedstock builds from the sdist on PyPI,
   not from GitHub, so PyPI comes first.
2. Within a few hours, conda-forge's bot (`regro-cf-autotick-bot`) sees
   the new version on PyPI and opens a pull request on the feedstock. It
   sets the version and the sha256 of the sdist and resets the build
   number to 0.
3. Check that pull request against `pyproject.toml`. The bot changes the
   version, not the dependencies: a new minimum version of `coolprop` or
   `numpy`, or a new minimum Python (`python_min` in the recipe), has to
   be added to the pull request by hand. The bot's own check of the
   dependencies (a comment in the pull request) helps, but it is not
   always right.
4. Merge it once its CI is green. The package is on the `conda-forge`
   channel about an hour later.

If the bot has not opened a pull request after a day, make it by hand
from a fork of the feedstock: in `recipe/recipe.yaml` (or
`recipe/meta.yaml` in an older recipe) set the version, set the sha256
to the one PyPI shows for the sdist (`coolplot-X.Y.Z.tar.gz`, "view
hashes"), and set the build number to 0. Commenting
`@conda-forge-admin, please rerender` in the pull request updates the
CI files of the feedstock if its checks ask for it.

A fix of the recipe alone (a dependency forgotten, a test that fails on
conda-forge) needs no new version of CoolPlot: raise the build number by
one in a pull request on the feedstock. A mistake in CoolPlot itself
needs a new version, as on PyPI.

Release candidates (`1.1.0rc1`) are not published on conda-forge; the
bot skips them.

### The test suite on conda-forge

conda-forge runs the tests of the recipe on the package it built, from
the files of the sdist. That is why the sdist carries `tests/`,
`examples/` and the documentation, and why the build job of `tests.yml`
compares the sdist with the files tracked in git. The recipe runs at
least:

```bash
pip check
python -c "import coolplot; from coolplot import PropertyDiagram"
pytest tests -q
```

The browser and Kaleido tests and the slow numerics sweeps skip
themselves unless asked (`tests/conftest.py`), so `pytest tests` needs
only `pytest`, `matplotlib` and `plotly` besides CoolPlot.

### First submission (once)

1. Fork `conda-forge/staged-recipes` and make a branch.
2. Make the recipe in `recipes/coolplot/`. `grayskull pypi coolplot`
   (`conda install -c conda-forge grayskull`) writes a first version from
   the sdist on PyPI; check it against `pyproject.toml`:
   * `noarch: python`, with `python >=${{ python_min }}` in `host` and
     `run` and `python_min` set to 3.11 (the `requires-python` of
     CoolPlot);
   * `run`: `numpy >=1.22` and `coolprop >=8.0`;
   * the tests above, with `pytest`, `matplotlib` and `plotly` as test
     requirements;
   * `license: MIT`, `license_file: LICENSE`;
   * the maintainers by their GitHub names.
3. Open a pull request on `conda-forge/staged-recipes` and follow its
   checklist. When its CI is green, comment
   `@conda-forge-admin, please ping team` to ask the Python reviewers
   for a review.
4. Once it is merged, conda-forge creates `conda-forge/coolplot-feedstock`
   and builds the first package. From then on, the steps under "Every
   release" apply.
