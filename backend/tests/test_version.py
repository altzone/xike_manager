"""The version shown in the UI comes from the server; every copy of the number must agree."""
import json
import os
import re

import main
from version import VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


def test_the_running_version_is_served_to_signed_in_users(api):
    assert api.get("/api/version").json() == {"version": VERSION}
    assert api.get("/api/version", headers={"Authorization": ""}).status_code in (401, 403)  # signed in only
    assert main.app.version == VERSION


def test_every_copy_of_the_version_number_agrees():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
    # the web page's own build: the sidebar compares it with the server's to spot a stale page
    assert json.loads(read("frontend", "package.json"))["version"] == VERSION
    assert f"badge/version-{VERSION}-blue" in read("README.md")
    latest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", read("CHANGELOG.md"), re.M)
    assert latest and latest.group(1) == VERSION
