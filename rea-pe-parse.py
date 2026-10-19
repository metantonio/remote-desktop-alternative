#!/usr/bin/env python
"""PE static parser for the AnyDesk x86 exe (no execution)."""
import struct, sys

p = sys.argv[1]
d = bytearray(open(p, "rb").read())

if d[0:2] != b"MZ":
    raise SystemExit("not MZ")
e = struct.unpack_from("<I", d, 0x3c)[0]
print(f"[dos] e_lfanew=0x{e:08x}")
mach = struct.unpack_from("<H", d, e+4)[0]
nsec = struct.unpack_from("<H", d, e+6)[0]
print(f"[coff] machine=0x{mach:x} nsectors={nsec}")
oh = e + 0x14
magic = struct.unpack_from("<H", d, oh+0x00)[0]
sizeopt = struct.unpack_from("<H", d, oh+0x12)[0]
print(f"[oh] magic=0x{magic:x} sizeopt=0x{sizeopt:x}")

def u32(o): return struct.unpack_from("<I", d, o)[0]
def u16(o): return struct.unpack_from("<H", d, o)[0]

entpt = u32(oh+0x54); base = u32(oh+0x58); sizeimage = u32(oh+0x5c)
subsys = u16(oh+0x42); ppdd = u32(oh+0x9c)
print(f"[oh] eptRVA=0x{entpt:08x} base=0x{base:08x} sizeimage=0x{sizeimage:08x} subsystem={subsys}({'GUI' if subsys==2 else 'CONSOLE'})")
print(f"[oh] pointerToDataDirectory file=0x{ppdd:08x}")

sect_off = oh + sizeopt
secs = {}
for i in range(nsec):
    b = sect_off + i*40
    name = d[b:b+8].rstrip(b"\0").decode("latin1","replace")
    if not name: break
    secs[name] = {"vaddr": u32(b+0x0c), "vsize": u32(b+0x08),
                  "p2raw": u32(b+0x14), "rawsize": u32(b+0x10), "chars": u32(b+0x28)}

print("\n=== SECTIONS ===")
for k,s in secs.items():
    print(f"  {k:14} vaddr=0x{s['vaddr']:08x} vsize=0x{s['vsize']:08x} p2raw=0x{s['p2raw']:08x} rawsize=0x{s['rawsize']:08x} chars=0x{s['chars']:x}")

def rva2file(rva):
    for k,s in secs.items():
        if s["vaddr"] <= rva < s["vaddr"] + max(s["vsize"],1):
            return s["p2raw"] + (rva - s["vaddr"])
    return None

import_idx = 1
dd_off = ppdd + import_idx*8
imp_raw = u32(dd_off); imp_rawsize = u32(dd_off+4)
print(f"\n=== IMPORT DIRECTORY ===")
print(f"import raw file offset=0x{imp_raw:08x} rawsize=0x{imp_rawsize:08x}")
idx = 0
seen = set()
while True:
    o = idx
    if o+20 > imp_rawsize: break
    origthunk = u32(imp_raw+o)
    ttime = u32(imp_raw+o+4)
    fwd = u32(imp_raw+o+8)
    name_rva = u32(imp_raw+o+0xc)
    firstthunk = u32(imp_raw+o+0x10)
    if name_rva == 0 and firstthunk == 0 and origthunk == 0:
        break
    name = ""
    foff = rva2file(name_rva)
    if foff is not None and foff < len(d):
        try:
            end = d.index(b"\0", foff, min(foff+256, len(d)))
            name = d[foff:end].decode("latin1","replace")
        except Exception: pass
    print(f"  dll name RVA=0x{name_rva:08x} -> '{name}'")
    if name_rva in seen: break
    seen.add(name_rva)
    idx += 20

print("\ndone")
sys.exit(0)
