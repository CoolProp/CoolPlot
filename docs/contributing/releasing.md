# Releasing

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

## Make a release

```bash
# 1. Set the version and date the changelog
#    src/coolplot/__version__.py:  VERSION = (1, 1, 0, '')
#    CHANGELOG.md:                 the section of this version
git commit -am "Release 1.1.0"
git push origin master

# 2. Tag the commit; the tag starts the release
git tag -a v1.1.0 -m "CoolPlot 1.1.0"
git push origin v1.1.0
```

Follow the run on the Actions tab. A release candidate works the same
way with `VERSION = (1, 1, 0, 'rc1')` and the tag `v1.1.0rc1`.

To rehearse without publishing, start the workflow by hand: Actions tab,
"release", "Run workflow", on the branch to try. It runs the same steps
and uploads to TestPyPI instead (a version already there is skipped), and
makes no GitHub release.

## When something fails

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

## One-time setup

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
