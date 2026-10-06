"""Which moving image tags a release takes: X.Y, X and latest only follow the newest version of
their line, so a fix for an older line published later never sends anyone back to it.
Usage: moving_tags.py vX.Y.Z  (prints minor=, major=, latest= lines for $GITHUB_OUTPUT)"""
import re
import subprocess
import sys


def parse(tag):
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def moving(this, versions):
    versions = set(versions) | {this}
    return {
        "minor": this == max(v for v in versions if v[:2] == this[:2]),
        "major": this == max(v for v in versions if v[0] == this[0]),
        "latest": this == max(versions),
    }


if __name__ == "__main__":
    this = parse(sys.argv[1])
    if this is None:
        sys.exit(f"not a version tag: {sys.argv[1]}")
    tags = subprocess.run(["git", "tag", "--list", "v*"], capture_output=True, text=True, check=True).stdout.split()
    for name, value in moving(this, filter(None, map(parse, tags))).items():
        print(f"{name}={'true' if value else 'false'}")
