"""Release notes for version X.Y.Z: its section of CHANGELOG.md, and how to get the image.
Usage: release_notes.py X.Y.Z"""
import os
import re
import sys

version = sys.argv[1]
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as f:
    text = f.read()
m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
if not m or not m.group(1).strip():
    sys.exit(f"CHANGELOG.md has no section for {version}")


def unwrap(section):
    """CHANGELOG.md is wrapped at 100 columns; a GitHub release shows each line break, so the lines
    of a paragraph or list item are joined (code blocks and tables are left as they are)."""
    out, fenced = [], False
    for line in section.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        starts_block = (not stripped or fenced or stripped.startswith(("#", "|", ">", "- ", "* "))
                        or re.match(r"\d+\. ", stripped))
        if out and not starts_block and out[-1].strip() and not out[-1].lstrip().startswith(("#", "|", "```")):
            out[-1] = out[-1].rstrip() + " " + stripped
        else:
            out.append(line)
    return "\n".join(out)


print(unwrap(m.group(1)))
print(f"""
---
Docker image: `ghcr.io/altzone/switchpilot:{version}` (amd64, arm64).
How to update: [docs/upgrade.md](https://github.com/altzone/xike_manager/blob/v{version}/docs/upgrade.md).""")
