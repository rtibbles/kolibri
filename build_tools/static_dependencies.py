# /// script
# requires-python = ">=3.11"
# dependencies = ["packaging", "tomlkit"]
# ///
"""
Helpers for the static (`make dist`) wheel build, which vendors the runtime
dependencies into kolibri/dist and ships a wheel with empty metadata, rather
than declaring them (the default dynamic build).

Two modes:

  --requirements  Print [project] dependencies one per line, excluding the C
                  extensions listed in requirements/cext.txt -- install_cexts.py
                  vendors those per-arch, so they must not be installed flat into
                  kolibri/dist. Used to feed `uv pip install` for the staticdeps
                  vendoring (and the CI jobs that previously consumed the `base`
                  dependency group).

  --clear         Rewrite pyproject.toml with empty [project] dependencies, so
                  the static wheel declares no dependencies. The Makefile
                  restores the file with `git checkout` after the build.

[project] dependencies is the single source of truth; both modes read it.
"""

import argparse
import logging
import os

import tomlkit
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
PYPROJECT = os.path.join(HERE, "..", "pyproject.toml")
CEXT_REQUIREMENTS = os.path.join(HERE, "..", "requirements", "cext.txt")


def load():
    with open(PYPROJECT, "r") as f:
        return tomlkit.parse(f.read())


def cext_requirements():
    """
    The C extensions vendored per-arch by install_cexts.py, by canonical name.
    """
    requirements = {}
    with open(CEXT_REQUIREMENTS, "r") as f:
        for line in f:
            line = line.partition("#")[0].strip()
            if line:
                requirement = Requirement(line)
                requirements[canonicalize_name(requirement.name)] = requirement
    return requirements


def runtime_requirements(doc):
    """
    [project] dependencies, less the packages vendored as C extensions.
    """
    cexts = cext_requirements()
    for requirement in doc["project"]["dependencies"]:
        cext = cexts.get(canonicalize_name(Requirement(requirement).name))
        if cext is None:
            yield requirement
            continue
        # The package is versioned in both files. Nothing else keeps the static
        # and dynamic builds from shipping incompatible versions of it.
        pinned = [spec.version for spec in cext.specifier if spec.operator == "=="]
        if pinned and not Requirement(requirement).specifier.contains(pinned[0]):
            raise SystemExit(
                "{} is pinned to {} in requirements/cext.txt, which does not "
                "satisfy '{}' in pyproject.toml".format(
                    cext.name, pinned[0], requirement
                )
            )


def print_requirements():
    for requirement in runtime_requirements(load()):
        print(requirement)  # noqa: T201 -- stdout is the script's output


def clear_dependencies():
    doc = load()
    doc["project"]["dependencies"] = []
    with open(PYPROJECT, "w") as f:
        f.write(tomlkit.dumps(doc))
    logger.info("Cleared [project] dependencies for the static build")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--requirements",
        action="store_true",
        help="print runtime dependencies (excluding cryptography)",
    )
    group.add_argument(
        "--clear",
        action="store_true",
        help="empty [project] dependencies in pyproject.toml",
    )
    args = parser.parse_args()
    if args.requirements:
        print_requirements()
    else:
        clear_dependencies()
