#!/usr/bin/env python3
"""List every dump below a folder: metadata version, title id, Unity version and file sizes.

    python il2list.py [folder]        (default: current folder)

One line per folder that holds a global-metadata*.dat, sorted by metadata version, smallest upload first.
"upload" = module image + metadata, which is all the dumper needs. Nothing is changed, the files are only read.
The Unity version is searched in the module image, then in the memory dump; on big dumps that takes a while.
"""
import mmap
import os
import re
import struct
import sys

UNITY = re.compile(rb"(?<![\d.])(?:5|20[12]\d|6000)\.\d\.\d{1,2}[fp]\d{1,2}(?![\w.])")
TITLE = re.compile(r"(?:CUSA|PPSA)\d{5}")


def unity_version(path):
    """The release version string that occurs 5 times first ("" if none does)."""
    seen = {}
    try:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            for hit in UNITY.finditer(m):
                v = hit.group().decode()
                seen[v] = seen.get(v, 0) + 1
                if seen[v] == 5:
                    return v
    except (OSError, ValueError):   # unreadable or empty file
        pass
    return ""


def scan(folder, files):
    size = lambda n: os.path.getsize(os.path.join(folder, n))
    low = {n: n.lower() for n in files}
    meta = min((n for n in files if low[n].startswith("global-metadata") and low[n].endswith(".dat")), key=len)
    with open(os.path.join(folder, meta), "rb") as f:
        head = f.read(8)
    if len(head) < 8 or head[:4] != b"\xAF\x1B\xB1\xFA":
        return None
    images = [n for n in files if low[n].startswith(("il2cppuserassemblies", "gameassembly"))]
    image = max(images, key=lambda n: (low[n].endswith(".elf"), size(n)), default=None)   # il2mem's image first
    dumps = [n for n in files if low[n].endswith(".bin")]
    dump = max(dumps, key=size, default=None)

    title = ""
    for n in files:                 # il2mem's dump.json names the title near its start
        if low[n].endswith(".json") and not title:
            with open(os.path.join(folder, n), "rb") as f:
                m = re.search(rb'"title_id":\s*"([^"]+)"', f.read(4096))
            title = m.group(1).decode() if m else ""
    if not title:
        m = TITLE.search(folder)
        title = m.group() if m else "?"

    unity = (image and unity_version(os.path.join(folder, image))) or (dump and unity_version(os.path.join(folder, dump))) or "?"
    return {
        "meta": struct.unpack("<i", head[4:])[0], "title": title, "unity": unity,
        "upload": size(meta) + (size(image) if image else 0), "image": bool(image),
        "dump": size(dump) if dump else 0,
        "sdk": os.path.isfile(os.path.join(folder, "sdk", "dump.cs")), "folder": folder,
    }


def main():
    top = sys.argv[1] if len(sys.argv) > 1 else "."
    rows = []
    for folder, _, files in os.walk(top):
        if any(n.lower().startswith("global-metadata") and n.lower().endswith(".dat") for n in files):
            print("reading", folder, file=sys.stderr)
            row = scan(folder, files)
            if row:
                rows.append(row)
    rows.sort(key=lambda r: (r["meta"], r["upload"]))
    print("meta  title      unity         upload MB  dump MB  sdk  folder")
    for r in rows:
        print("%-5d %-10s %-13s %8.1f%s %8.0f  %-3s  %s" % (
            r["meta"], r["title"], r["unity"], r["upload"] / 2**20, " " if r["image"] else "*",
            r["dump"] / 2**20, "yes" if r["sdk"] else "no", os.path.relpath(r["folder"], top)))
    if any(not r["image"] for r in rows):
        print("* no module image (Il2CppUserAssemblies*) in the folder: upload is the metadata alone")


if __name__ == "__main__":
    main()
