"""Minimal .eh_frame reader for the dumped module: CFA rule and LSDA at a pc, and a return gadget for il2cheat.

A method called from the hook cave may throw a managed exception (il2cpp raises a C++ exception); the unwinder walks the
return addresses, finds no FDE for the cave and the process ends with "terminate is called". il2cheat therefore lets the
called method return through a `pop rcx; ret` inside a module function whose unwind row there says CFA = rsp+16 with no
saved registers and no LSDA: unwinding passes that row to the hooked method's caller (its catch logs the exception), and a
normal return lands in the hooked method's caller as well (the hooked method is skipped for that one frame).
"""
import struct

RSP, RIP = 7, 16


def _uleb(b, i):
    v, s = 0, 0
    while True:
        x = b[i]; i += 1
        v |= (x & 0x7F) << s; s += 7
        if not x & 0x80:
            return v, i


def _sleb(b, i):
    v, s = 0, 0
    while True:
        x = b[i]; i += 1
        v |= (x & 0x7F) << s; s += 7
        if not x & 0x80:
            return (v - (1 << s) if x & 0x40 else v), i


def _ptr(b, i, enc, va, hdr_va):
    """Encoded pointer at offset i (va = address of that offset) -> (value, next offset)."""
    if enc == 0xFF:
        return 0, i
    f = enc & 0x0F
    if f == 0x0:
        v, n = struct.unpack_from("<Q", b, i)[0], 8
    elif f == 0x1:
        v, j = _uleb(b, i); n = j - i
    elif f == 0x9:
        v, j = _sleb(b, i); n = j - i
    else:
        fmt, n = {0x2: ("<H", 2), 0x3: ("<I", 4), 0x4: ("<Q", 8), 0xA: ("<h", 2), 0xB: ("<i", 4), 0xC: ("<q", 8)}[f]
        v = struct.unpack_from(fmt, b, i)[0]
    app = enc & 0x70
    if app == 0x10:
        v += va
    elif app == 0x30:
        v += hdr_va
    return v & 0xFFFFFFFFFFFFFFFF, i + n


class EhFrame:
    def __init__(self, blob, blob_va, hdr_va):
        """blob: the module's read-only segment, blob_va its address, hdr_va the eh_frame_hdr inside it."""
        self.b, self.va, self.hdr = blob, blob_va, hdr_va
        i = hdr_va - blob_va
        if self.b[i] != 1:
            raise ValueError("eh_frame_hdr version")
        enc_ptr, enc_cnt, enc_tab = self.b[i + 1], self.b[i + 2], self.b[i + 3]
        self.eh_frame, j = _ptr(self.b, i + 4, enc_ptr, hdr_va + 4, hdr_va)
        self.count, j = _ptr(self.b, j, enc_cnt, hdr_va + (j - i), hdr_va)
        if enc_tab != 0x3B:
            raise ValueError(f"eh_frame_hdr table encoding {enc_tab:#x}")
        self.table = j                                         # (initial_loc, fde) datarel sdata4 pairs, sorted
        self.cies = {}

    @classmethod
    def find(cls, blob, blob_va, text_lo, text_hi):
        """eh_frame_hdr in a read-only segment: version 1, pcrel|sdata4 eh_frame pointer, udata4 count, datarel|sdata4 table."""
        i = blob.find(b"\x01\x1b\x03\x3b")
        while i != -1:
            try:
                eh = cls(blob, blob_va, blob_va + i)
                lo, fde = eh.entry(0)
                if 1000 <= eh.count <= 50_000_000 and blob_va <= eh.eh_frame < blob_va + len(blob) and text_lo <= lo < text_hi:
                    return eh
            except (ValueError, struct.error, KeyError, IndexError):
                pass
            i = blob.find(b"\x01\x1b\x03\x3b", i + 4)
        return None

    def entry(self, n):
        lo, fde = struct.unpack_from("<ii", self.b, self.table + 8 * n)
        return lo + self.hdr, fde + self.hdr

    def fde_for(self, pc):
        a, z = 0, self.count
        while z - a > 1:
            m = (a + z) // 2
            if self.entry(m)[0] <= pc:
                a = m
            else:
                z = m
        return self.entry(a)[1]

    def cie(self, va):
        if va in self.cies:
            return self.cies[va]
        b, i = self.b, va - self.va
        length = struct.unpack_from("<I", b, i)[0]
        end = i + 4 + length
        j = i + 8                                               # length, CIE id
        version = b[j]; j += 1
        aug = b[j:b.index(b"\0", j)].decode(); j += len(aug) + 1
        if version == 4:
            j += 2                                              # address size, segment size
        code_align, j = _uleb(b, j)
        data_align, j = _sleb(b, j)
        if version == 1:
            ra = b[j]; j += 1
        else:
            ra, j = _uleb(b, j)
        fde_enc, lsda_enc, has_lsda = 0, 0xFF, False
        if aug.startswith("z"):
            n, j = _uleb(b, j)
            k = j
            for c in aug[1:]:
                if c == "R":
                    fde_enc = b[k]; k += 1
                elif c == "L":
                    lsda_enc = b[k]; has_lsda = True; k += 1
                elif c == "P":
                    enc = b[k]; k += 1
                    _, k = _ptr(b, k, enc & 0x7F, self.va + k, self.hdr)
                elif c == "S":
                    pass
            j += n
        c = dict(code_align=code_align, data_align=data_align, fde_enc=fde_enc, lsda_enc=lsda_enc, has_lsda=has_lsda,
                 z=aug.startswith("z"), insns=bytes(b[j:end]))
        self.cies[va] = c
        return c

    def fde(self, va):
        """-> dict(pc_begin, pc_end, lsda, cie, insns) of the FDE at va."""
        b, i = self.b, va - self.va
        length = struct.unpack_from("<I", b, i)[0]
        end = i + 4 + length
        cie_ptr = struct.unpack_from("<I", b, i + 4)[0]
        cie = self.cie(va + 4 - cie_ptr)
        j = i + 8
        pc_begin, j = _ptr(b, j, cie["fde_enc"], self.va + j, self.hdr)
        pc_range, j = _ptr(b, j, cie["fde_enc"] & 0x0F, self.va + j, self.hdr)
        lsda = 0
        if cie["z"]:
            n, j = _uleb(b, j)
            if cie["has_lsda"]:
                lsda, _ = _ptr(b, j, cie["lsda_enc"], self.va + j, self.hdr)
            j += n
        return dict(pc_begin=pc_begin, pc_end=pc_begin + pc_range, lsda=lsda, cie=cie, insns=bytes(b[j:end]))

    def row(self, pc):
        """Unwind row at pc -> (cfa_reg, cfa_off, {reg: rule}, lsda, fde) or None when no FDE covers pc; rule 'expr' = DWARF expression."""
        f = self.fde(self.fde_for(pc))
        if not f["pc_begin"] <= pc < f["pc_end"]:
            return None
        cie = f["cie"]
        state = [RSP, 8, {}]
        stack, init = [], None

        def run(insns, loc, stop):
            b, i = insns, 0
            while i < len(b):
                op = b[i]; i += 1
                hi, lo = op & 0xC0, op & 0x3F
                if hi == 0x40:
                    loc += lo * cie["code_align"]
                elif hi == 0x80:
                    off, i = _uleb(b, i); state[2][lo] = off * cie["data_align"]
                elif hi == 0xC0:
                    state[2].pop(lo, None)
                    if init and lo in init[2]:
                        state[2][lo] = init[2][lo]
                elif op == 0x00:
                    pass
                elif op == 0x01:
                    loc, i = _ptr(b, i, cie["fde_enc"], 0, self.hdr)
                elif op in (0x02, 0x03, 0x04):
                    n = {0x02: 1, 0x03: 2, 0x04: 4}[op]
                    loc += int.from_bytes(b[i:i + n], "little") * cie["code_align"]; i += n
                elif op in (0x05, 0x11):
                    r, i = _uleb(b, i); off, i = (_uleb if op == 0x05 else _sleb)(b, i); state[2][r] = off * cie["data_align"]
                elif op == 0x06:
                    r, i = _uleb(b, i); state[2].pop(r, None)
                elif op in (0x07, 0x08):
                    r, i = _uleb(b, i); state[2][r] = "undef" if op == 0x07 else "same"
                elif op == 0x09:
                    r, i = _uleb(b, i); r2, i = _uleb(b, i); state[2][r] = ("reg", r2)
                elif op == 0x0A:
                    stack.append((state[0], state[1], dict(state[2])))
                elif op == 0x0B:
                    state[0], state[1], state[2] = stack.pop()
                elif op == 0x0C:
                    state[0], i = _uleb(b, i); state[1], i = _uleb(b, i)
                elif op == 0x0D:
                    state[0], i = _uleb(b, i)
                elif op == 0x0E:
                    state[1], i = _uleb(b, i)
                elif op == 0x0F:
                    n, i = _uleb(b, i); i += n; state[0], state[1] = "expr", 0
                elif op in (0x10, 0x16):
                    r, i = _uleb(b, i); n, i = _uleb(b, i); i += n; state[2][r] = "expr"
                elif op == 0x12:
                    state[0], i = _uleb(b, i); off, i = _sleb(b, i); state[1] = off * cie["data_align"]
                elif op == 0x13:
                    off, i = _sleb(b, i); state[1] = off * cie["data_align"]
                elif op in (0x14, 0x15):
                    r, i = _uleb(b, i); off, i = (_uleb if op == 0x14 else _sleb)(b, i); state[2][r] = ("val", off * cie["data_align"])
                elif op == 0x2E:
                    _, i = _uleb(b, i)
                elif op == 0x2F:
                    r, i = _uleb(b, i); off, i = _uleb(b, i); state[2][r] = -off * cie["data_align"]
                else:
                    raise ValueError(f"CFA op {op:#x}")
                if loc > stop:
                    break
            return loc

        run(cie["insns"], f["pc_begin"], 1 << 64)
        init = (state[0], state[1], dict(state[2]))
        run(f["insns"], f["pc_begin"], pc)
        return state[0], state[1], state[2], f["lsda"], f


REG_NAMES = {3: "rbx", 12: "r12", 13: "r13", 14: "r14", 15: "r15"}


def find_gadget(eh, text, text_va, limit=3000):
    """(RVA relative to text_va, registers to push below rbp in order) of a `pop rbp; ret` whose unwind rows at the pop and
    the byte before it are: CFA = rbp+16, rbp at CFA-16, return address at CFA-8, callee-saved registers at CFA-24, -32, ...
    with nothing else and no LSDA. The cave builds that frame (push rbp; mov rbp, rsp; push regs...) before the call, so
    unwinding from the called method passes through it to the hooked method's caller. Fewest registers wins; None if none."""
    best, seen, i = None, 0, text.find(b"\x5d\xc3")
    while i != -1 and seen < limit:
        pc = text_va + i
        try:
            rows = [eh.row(p) for p in (pc - 1, pc)]
        except (ValueError, struct.error, KeyError, IndexError):
            rows = [None]
        seen += 1
        r = rows[0]
        if r and rows[1] and rows[1][:4] == r[:4] and r[0] == 6 and r[1] == 16 and r[3] == 0 and r[2].get(6) == -16 \
                and r[2].get(RIP) == -8 and set(r[2]) <= set(REG_NAMES) | {6, RIP} and r[4]["pc_begin"] <= pc - 1:
            offs = sorted(((v, k) for k, v in r[2].items() if k not in (6, RIP)), reverse=True)   # -24 first = pushed first
            if [v for v, _ in offs] == [-24 - 8 * j for j in range(len(offs))] and (best is None or len(offs) < len(best[1])):
                best = (i, [REG_NAMES[k] for _, k in offs])
                if not offs:
                    break
        i = text.find(b"\x5d\xc3", i + 1)
    return best


if __name__ == "__main__":                                      # self check on a dump: python ehframe.py <dumpdir>
    import sys, il2live
    d = il2live.Dump(sys.argv[1])
    regs = [r for r in d.regs if r["name"] == "Il2CppUserAssemblies.prx"]
    text = [r for r in regs if r["prot"] & 4][0]
    tb = d.m[text["offset"]:text["offset"] + text["end"] - text["start"]]
    for r in regs:
        if r["prot"] & 4 or not r["prot"] & 1:
            continue
        rb = d.m[r["offset"]:r["offset"] + r["end"] - r["start"]]
        eh = EhFrame.find(rb, r["start"], text["start"], text["end"])
        if eh:
            print(f"eh_frame_hdr {eh.hdr:#x}, eh_frame {eh.eh_frame:#x}, {eh.count} FDEs")
            g = find_gadget(eh, tb, text["start"])
            print(f"gadget: text+{g[0]:#x} push {g[1]}" if g else "no gadget")
            row = eh.row(text["start"] + g[0])
            print(f"  row: cfa r{row[0]}+{row[1]} regs {row[2]} lsda {row[3]:#x} fde {row[4]['pc_begin']:#x}-{row[4]['pc_end']:#x}")
            assert row[0] == 6 and row[1] == 16 and tb[g[0]:g[0] + 2] == b"\x5d\xc3"
            break
    else:
        print("no eh_frame_hdr")
