#!/usr/bin/env python3
"""Swap the homepage hero banner.

The active banner is assets/hero-banner.jpg (mirrored into docs/assets/ for the
static pages). Every banner ever used is kept in assets/banners/ so an old one
can be restored without hunting through git history or Downloads.

    python3 scripts/set_hero_banner.py --list
    python3 scripts/set_hero_banner.py ~/Downloads/new-banner.jpg
    python3 scripts/set_hero_banner.py assets/banners/2026-10-06-nuppl-sunrise-reservoir.jpg
"""
import argparse
import datetime
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, "assets", "banners")
ACTIVE = os.path.join(ROOT, "assets", "hero-banner.jpg")
MIRRORS = [os.path.join(ROOT, "docs", "assets", "hero-banner.jpg")]


def list_archive():
    if not os.path.isdir(ARCHIVE):
        print("no archive yet")
        return
    names = sorted(os.listdir(ARCHIVE))
    if not names:
        print("archive is empty")
        return
    for name in names:
        size = os.path.getsize(os.path.join(ARCHIVE, name)) // 1024
        marker = ""
        if os.path.exists(ACTIVE) and _same(os.path.join(ARCHIVE, name), ACTIVE):
            marker = "  <- currently active"
        print(f"{name}  ({size} KB){marker}")


def _same(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def main():
    parser = argparse.ArgumentParser(description="Swap the homepage hero banner.")
    parser.add_argument("image", nargs="?", help="path to the new banner image")
    parser.add_argument("--list", action="store_true", help="list archived banners")
    parser.add_argument("--label", help="short slug used in the archived filename")
    args = parser.parse_args()

    if args.list or not args.image:
        list_archive()
        return 0

    source = os.path.abspath(os.path.expanduser(args.image))
    if not os.path.isfile(source):
        print(f"error: no such file: {source}", file=sys.stderr)
        return 1

    os.makedirs(ARCHIVE, exist_ok=True)

    # archive whatever is active right now, unless it is already in the archive
    if os.path.exists(ACTIVE):
        already = any(
            _same(os.path.join(ARCHIVE, n), ACTIVE) for n in os.listdir(ARCHIVE)
        )
        if not already:
            stamp = datetime.date.today().isoformat()
            shutil.copy2(ACTIVE, os.path.join(ARCHIVE, f"{stamp}-replaced.jpg"))
            print(f"archived previous banner -> assets/banners/{stamp}-replaced.jpg")

    shutil.copy2(source, ACTIVE)
    for mirror in MIRRORS:
        os.makedirs(os.path.dirname(mirror), exist_ok=True)
        shutil.copy2(ACTIVE, mirror)

    # keep a copy of the incoming image in the archive too
    if not os.path.commonpath([source, ARCHIVE]) == ARCHIVE:
        label = args.label or re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(source))[0].lower()).strip("-")
        stamp = datetime.date.today().isoformat()
        dest = os.path.join(ARCHIVE, f"{stamp}-{label}.jpg"[:120])
        if not os.path.exists(dest):
            shutil.copy2(source, dest)
            print(f"archived new banner    -> assets/banners/{os.path.basename(dest)}")

    print("active banner updated: assets/hero-banner.jpg + docs/assets/hero-banner.jpg")
    print("note: run `firebase deploy --only hosting` to push it live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
