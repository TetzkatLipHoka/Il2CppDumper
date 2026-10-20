"""Extract what Il2CppDumper needs from a ps4dump.py memory dump (dump.bin + dump.json): no prx/metadata files required.

    python il2mem.py <dumpdir> [-o outdir] [--module Il2CppUserAssemblies.prx]

Writes <outdir>/global-metadata.dat (found by its magic AF 1B B1 FA in the heap, size from the header) and
<outdir>/<module>.elf: a minimal ELF64 (ET_DYN) whose PT_LOAD segments are the module's mapped regions at their
runtime addresses. The loader strips the real ELF header, so the first page of the module is 0xCC padding.
Then run Il2CppDumper (the fork) on both: the ELF is tagged "il2mem" in ei_pad, the dumper takes the base from the
segment addresses itself and skips the dump-address prompt and the NoRedirectedPointer setting.
"""
import argparse, json, mmap, os, struct

META_MAGIC = b"\xaf\x1b\xb1\xfa"


def metadata_size(buf, base):
    """Furthest section end from the (offset, size) pairs behind sanity+version."""
    end, prev = 8, 0
    for i in range(64):
        off, size = struct.unpack_from("<ii", buf, base + 8 + i * 8)
        if off < 8 or off > 0x7FFFFFFF or size < 0 or off < prev:
            break
        prev, end = off, max(end, off + size)
    return end


def find_metadata(m, regions):
    pos = 0
    while True:
        i = m.find(META_MAGIC, pos)
        if i < 0:
            return None
        ver = struct.unpack_from("<I", m, i + 4)[0]
        if 16 <= ver <= 64 and i % 16 == 0:
            size = metadata_size(m, i)
            r = region_of(regions, i)
            if r and size > 0x1000 and i + size <= r["offset"] + r["end"] - r["start"]:
                return i, ver, size, r
        pos = i + 4


def region_of(regions, file_offset):
    for r in regions:
        if r["offset"] <= file_offset < r["offset"] + r["end"] - r["start"]:
            return r
    return None


def write_elf(m, regions, out):
    """ELF64 with one PT_LOAD per region (p_vaddr = runtime address) plus an empty PT_DYNAMIC Il2CppDumper insists on."""
    phnum = len(regions) + 1
    phoff = 64
    data_start = (phoff + phnum * 56 + 0xFFF) & ~0xFFF
    with open(out, "wb") as f:
        f.write(b"\x7fELF" + bytes([2, 1, 1, 9, 0]) + b"il2mem\0")                  # ELF64 LE, FreeBSD ABI; ei_pad tag: the dumper takes the base from the segments, no prompt / config
        f.write(struct.pack("<HHIQQQIHHHHHH", 3, 0x3E, 1, 0, phoff, 0, 0, 64, 56, phnum, 64, 0, 0))
        off = data_start
        for r in regions:
            size = r["end"] - r["start"]
            prot = r["prot"]                                                       # ps4debug: 1=R 2=W 4=X -> ELF: 4=R 2=W 1=X
            flags = (4 if prot & 1 else 0) | (2 if prot & 2 else 0) | (1 if prot & 4 else 0)
            f.write(struct.pack("<IIQQQQQQ", 1, flags, off, r["start"], r["start"], size, size, 0x4000))
            off += size
        f.write(struct.pack("<IIQQQQQQ", 2, 6, data_start, 0, 0, 0, 0, 8))          # PT_DYNAMIC, empty
        f.write(b"\0" * (data_start - f.tell()))
        for r in regions:
            size = r["end"] - r["start"]
            f.write(m[r["offset"]:r["offset"] + size])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dumpdir", help="folder with dump.bin and dump.json from ps4dump.py")
    ap.add_argument("-o", "--out", help="output folder (default: dumpdir)")
    ap.add_argument("--module", default="Il2CppUserAssemblies.prx", help="il2cpp module name in dump.json (PS4/PS5 default)")
    a = ap.parse_args()
    out = a.out or a.dumpdir
    os.makedirs(out, exist_ok=True)
    info = json.load(open(os.path.join(a.dumpdir, "dump.json")))
    regions = info["regions"]
    fh = open(os.path.join(a.dumpdir, "dump.bin"), "rb")
    m = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)

    mod = sorted((r for r in regions if r["name"] == a.module), key=lambda r: r["start"])
    if not mod:
        raise SystemExit(f"module {a.module} not in dump.json; names: {sorted(set(r['name'] for r in regions))[:40]}")
    base = mod[0]["start"]
    elf = os.path.join(out, a.module + ".elf")
    write_elf(m, mod, elf)
    print(f"{elf}: {len(mod)} segments, base 0x{base:X}")

    hit = find_metadata(m, regions)
    if not hit:
        raise SystemExit("global-metadata not found in the dump (game not running / metadata encrypted?)")
    off, ver, size, r = hit
    meta = os.path.join(out, "global-metadata.dat")
    with open(meta, "wb") as f:
        f.write(m[off:off + size])
    print(f"{meta}: version {ver}, {size} bytes, was at 0x{r['start'] + off - r['offset']:X}")
    print(f"\nIl2CppDumper \"{elf}\" \"{meta}\" <outdir>")


if __name__ == "__main__":
    main()
