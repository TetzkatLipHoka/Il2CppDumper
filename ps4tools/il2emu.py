#!/usr/bin/env python3
"""Run the hook cave of an il2cheat trainer in a CPU emulator against the dump: what would each cheat do?

    python il2emu.py <dumpdir> trainer.TLH                 # every cheat on its own
    python il2emu.py <dumpdir> trainer.TLH --on 2,5        # only these (numbers as listed)
    python il2emu.py <dumpdir> trainer.TLH --this 0x2112d1e40          # rdi for this. paths (il2live --instances Class)
    python il2emu.py <dumpdir> trainer.TLH --poke 0x2112d1e40=0        # change a qword first (null object, another class ...)

The cave is assembled like the loader does (GetMem cells, RegisterSymbol values), memory is the dump (mapped page by
page on first use, writes stay in the emulator). One run per cheat with only its flag on; reported: the bytes it writes
outside its own cells, the game methods it calls with their arguments, its flag afterwards, and whether the hooked
method's arguments, the callee-saved registers and the stack came back as they were. A called method is not executed:
it overwrites the registers a real method may overwrite and returns 0 at once through the return address the cave gave
it, so the return gadget and the frame around the call are executed for real. patch: cheats have no cave
code and are only listed. Needs keystone-engine and unicorn (pip install keystone-engine unicorn).
"""
import html, re, struct, sys
import il2live

MODULE = "Il2CppUserAssemblies.prx"
CAVE, STACK, STOP = 0x7E00_0000_0000, 0x7D00_0000_0000, 0x7E00_0010_0000
FMT = dict(Single="<f", Double="<d", Integer="<i", Cardinal="<I", Int64="<q", UInt64="<Q", SmallInt="<h", Word="<H", Byte="<B", ShortInt="<b", Boolean="<B")
# what the hooked method still needs when the cave is done: its arguments and the callee-saved registers
# (rax, r10, r11 and the flags are free at a function's first instruction)
SAVED = ("rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp", "r8", "r9", "r12", "r13", "r14", "r15")


class Emu:
    """Dump memory behind a unicorn CPU. writes: [(address, bytes)] outside `own`; calls: [(target, regs)] at `stubs`."""

    def __init__(self, dump, own=(), stubs=()):
        import unicorn
        from unicorn import x86_const as x
        self.u, self.x, self.dump, self.own, self.stubs = unicorn, x, dump, own, set(stubs)
        self.writes, self.calls, self.fault = [], [], None
        self.uc = uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        uc.mem_map(STACK, 0x10000)
        uc.hook_add(unicorn.UC_HOOK_MEM_READ_UNMAPPED | unicorn.UC_HOOK_MEM_WRITE_UNMAPPED | unicorn.UC_HOOK_MEM_FETCH_UNMAPPED, self._map)
        uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, self._write)
        uc.hook_add(unicorn.UC_HOOK_CODE, self._code)

    def load(self, addr, blob):
        self.uc.mem_map(addr & ~0xFFF, (len(blob) + (addr & 0xFFF) + 0xFFF) & ~0xFFF)
        self.uc.mem_write(addr, bytes(blob))

    def _map(self, uc, access, addr, size, value, _):
        for page in range(addr & ~0xFFF, (addr + max(size, 1) + 0xFFF) & ~0xFFF, 0x1000):
            data = self.dump.read(page, 0x1000)
            if not data:
                self.fault = addr                           # the cave touched memory the dump does not have
                return False
            try:
                uc.mem_map(page, 0x1000)
            except self.u.UcError:
                continue                                    # already there
            uc.mem_write(page, bytes(data).ljust(0x1000, b"\0"))
        return True

    def _write(self, uc, access, addr, size, value, _):
        if not any(a <= addr < b for a, b in self.own) and not STACK <= addr < STACK + 0x10000:
            self.writes.append((addr, (value & ((1 << 8 * size) - 1)).to_bytes(size, "little")))

    def _code(self, uc, addr, size, _):
        if addr in self.stubs:                              # a game method: note the arguments, return 0 at once
            x = self.x
            regs = {r: uc.reg_read(getattr(x, "UC_X86_REG_" + r.upper())) for r in ("rdi", "rsi", "rdx", "rcx", "r8", "r9")}
            regs.update({f"xmm{i}": uc.reg_read(getattr(x, f"UC_X86_REG_XMM{i}")) & 0xFFFFFFFFFFFFFFFF for i in range(4)})
            rsp = uc.reg_read(x.UC_X86_REG_RSP)
            regs["aligned"] = rsp % 16 == 8                 # System V: rsp is 8 mod 16 at a function's first instruction
            self.calls.append((addr, regs))
            for r in ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "r10", "r11"):        # a real method leaves anything in these
                uc.reg_write(getattr(x, "UC_X86_REG_" + r.upper()), 0xDEAD_0000_0000)
            for i in range(8):
                uc.reg_write(getattr(x, f"UC_X86_REG_XMM{i}"), 0xDEAD_BEEF_DEAD_BEEF)
            uc.reg_write(x.UC_X86_REG_RAX, 0)
            uc.reg_write(x.UC_X86_REG_RSP, rsp + 8)
            uc.reg_write(x.UC_X86_REG_RIP, struct.unpack("<Q", uc.mem_read(rsp, 8))[0])

    def run(self, entry, until, rdi=0, ret=STOP + 0x100, xmm=0):
        """-> (state before, state after, error text or None). The stack starts with `ret` as the hooked method's return address;
        xmm: the hooked method takes that many float arguments, xmm0.. are part of the state."""
        x, uc = self.x, self.uc
        rsp = STACK + 0x8000 - 8                            # rsp at the hooked method's first instruction: 8 mod 16
        uc.mem_write(rsp, struct.pack("<Q", ret))
        for i, r in enumerate(SAVED):
            uc.reg_write(getattr(x, "UC_X86_REG_" + r.upper()), 0x1111_0000_0000 + i * 0x1000 if r not in ("rsp", "rdi") else (rsp if r == "rsp" else rdi))
        for i in range(8):
            uc.reg_write(getattr(x, f"UC_X86_REG_XMM{i}"), 0x4000_0000_0000_0000 + i)
        state = lambda: {r: uc.reg_read(getattr(x, "UC_X86_REG_" + r.upper())) for r in SAVED} |                         {f"xmm{i}": uc.reg_read(getattr(x, f"UC_X86_REG_XMM{i}")) & 0xFFFFFFFFFFFFFFFF for i in range(xmm)}
        before, err = state(), None
        try:
            uc.emu_start(entry, until, count=2_000_000)
        except self.u.UcError as e:
            err = f"{e} at rip {uc.reg_read(x.UC_X86_REG_RIP):#x}" + (f", address {self.fault:#x} is not in the dump" if self.fault else "")
        if not err and uc.reg_read(x.UC_X86_REG_RIP) != until:
            err = f"did not reach the end (rip {uc.reg_read(x.UC_X86_REG_RIP):#x} after 2,000,000 instructions)"
        return before, state(), err


def assemble(lines, cells, numbers, addr):
    """lines with [Cell] operands and symbol numbers -> (blob, {cell: offset}); cells: [(name, initial bytes)] placed behind the code."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_64
    text = "\n".join(lines + [f"{c}: .byte " + ", ".join(str(b) for b in init) for c, init in cells])
    if cells:
        text = re.sub(r"\[(" + "|".join(c for c, _ in cells) + r")\]", r"[rip + \1]", text)
    if numbers:
        text = re.sub(r"\b(" + "|".join(numbers) + r")\b", lambda m: hex(numbers[m.group(1)]), text)
    blob = bytes(Ks(KS_ARCH_X86, KS_MODE_64).asm(text, addr)[0])
    off, where = len(blob), {}
    for c, init in reversed(cells):
        off -= len(init)
        where[c] = off
    return blob, where


def parse_tlh(path):
    """-> (cave lines up to the register restore, [(cell, size)], {symbol: module offset}, [(cheat name, {symbol: (ValueType, text)}, is patch)])"""
    x = open(path, encoding="utf-8-sig").read()
    m = re.search(r"<StartUP.*?<Assembly>(.*?)</Assembly>", x, re.S)
    lines = html.unescape(m.group(1)).splitlines() if m else []
    cells = [(g.group(1), int(g.group(2))) for g in (re.match(r"GetMem\( (\w+), (\d+) \)", l) for l in lines) if g]
    syms = {g.group(1): int(g.group(2), 16) for g in (re.match(r"RegisterSymbol\( (\w+), ModuleBase\+(0x[0-9a-fA-F]+) \)", l) for l in lines) if g}
    body = [l for l in lines if l.strip() and not l.startswith(("GetMem(", "RegisterSymbol("))]
    if body:
        end = body.index("popfq", body.index("done:"))      # behind it: the hooked method's own first instructions
        body = body[:end + 1]
    cheats = []
    for c in re.finditer(r'<Cheat Name="([^"]*)".*?</Cheat>', x, re.S):
        vals = {s: (t, v) for s, t, v in re.findall(r"<Symbol>(\w+)</Symbol>\s*<Type>Value</Type>\s*<ValueType>(\w+)</ValueType>\s*<Value>([^<]*)</Value>", c.group(0))}
        cheats.append((html.unescape(c.group(1)), vals, "<Type>Assembly</Type>" in c.group(0)))
    return body, cells, syms, cheats


def show(dump, emu, base, module, names):
    """Lines describing what a run did."""
    out = []
    for addr, data in emu.writes:
        was = dump.read(addr, len(data))
        out.append(f"writes {len(data)} byte{'s' * (len(data) > 1)} {data.hex()} to {addr:#x} (dump: {bytes(was).hex() if was else 'not in the dump'})")
    for target, r in emu.calls:
        fl = struct.unpack("<f", struct.pack("<I", r["xmm0"] & 0xFFFFFFFF))[0]
        out.append(f"calls {names.get(target, module)}+{target - base:#x} with rdi={r['rdi']:#x} rsi={r['rsi']:#x} rdx={r['rdx']:#x} rcx={r['rcx']:#x} xmm0={fl:g}"
                   + ("" if r["aligned"] else "  STACK NOT ALIGNED at the call"))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dumpdir"); ap.add_argument("tlh")
    ap.add_argument("--json", default="dump.json"); ap.add_argument("--module", default=MODULE)
    ap.add_argument("--on", help="cheat numbers to run, comma separated (default: all)")
    ap.add_argument("--this", type=lambda v: int(v, 0), default=0, help="address of the hooked object (rdi) for this. paths")
    ap.add_argument("--poke", action="append", default=[], help="0xADDRESS=0xQWORD written before each run")
    ap.add_argument("--xmm", type=int, default=0, help="the hooked method takes this many float arguments: check that xmm0.. survive")
    a = ap.parse_args()
    dump = il2live.Dump(a.dumpdir, a.json)
    base = dump.module_base(a.module)
    body, cells, syms, cheats = parse_tlh(a.tlh)
    numbers = {s: base + off for s, off in syms.items()}
    stubs = {v for s, v in numbers.items() if s.startswith("Call")}
    want = {int(n) for n in a.on.split(",")} if a.on else None
    bad = 0
    for k, (name, vals, patch) in enumerate(cheats, 1):
        if want and k not in want:
            continue
        flag = next((s for s in vals if s.startswith("Flag")), None)
        if not body or flag is None or not any(c == flag for c, _ in cells):
            print(f"{k:3d} {name}: " + ("patch at the method start, no cave code" if patch else "no cave code"))
            continue
        init = []
        for c, size in cells:
            t, v = vals.get(c, ("", "0"))
            init.append((c, struct.pack("<B", 1) if c == flag else (struct.pack(FMT[t], float(v) if t in ("Single", "Double") else int(v, 0)) if t in FMT else bytes(size))))
        blob, where = assemble(body + [f"jmp {STOP:#x}"], init, numbers, CAVE)
        emu = Emu(dump, own=[(CAVE, CAVE + len(blob))], stubs=stubs)
        emu.load(CAVE, blob)
        for p in a.poke:
            addr, val = (int(v, 0) for v in p.split("="))
            emu._map(emu.uc, 0, addr, 8, 0, None)
            emu.uc.mem_write(addr, struct.pack("<Q", val))
        before, after, err = emu.run(CAVE, STOP, rdi=a.this, xmm=a.xmm)
        after_flag = emu.uc.mem_read(CAVE + where[flag], 1)[0]
        what = show(dump, emu, base, a.module, {})
        same = before == after
        state = "FAULT: " + err if err else ("nothing done (a path did not resolve)" if not what else "; ".join(what))
        print(f"{k:3d} {name}: {state}" + (f"; flag -> {after_flag}" if after_flag != 1 else "") + ("" if same or err else "; REGISTERS / STACK NOT RESTORED: "
              + ", ".join(f"{r} {before[r]:#x} -> {after[r]:#x}" for r in before if before[r] != after[r])))
        bad += bool(err) or not same
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
