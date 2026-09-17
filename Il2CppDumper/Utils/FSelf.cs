using System;
using System.Collections.Generic;

namespace Il2CppDumper
{
    /// <summary>
    /// Unwraps a Sony PS4 fake-signed SELF (FSELF, magic 4F 15 3D 1D) into the plain ELF it contains.
    /// Port of UnFSelf.py / pkg_pfs_tool unfself.c: every SELF entry is a plaintext copy of one program
    /// segment; the ELF header and program headers are stored verbatim after the entry table.
    /// Encrypted (real) SELF files cannot be handled.
    /// </summary>
    public static class FSelf
    {
        public const uint Magic = 0x1D3D154F;

        public static byte[] Unwrap(byte[] self)
        {
            var entryCount = BitConverter.ToUInt16(self, 0x18);
            var entries = new List<(ulong offset, ulong size, bool used)>();
            for (var i = 0; i < entryCount; i++)
            {
                var entry = 0x20 + i * 32;
                var props = BitConverter.ToUInt64(self, entry);
                var offset = BitConverter.ToUInt64(self, entry + 8);
                var size = BitConverter.ToUInt64(self, entry + 16);
                if ((props & 0x800) != 0 && (props & 0x2) != 0)
                {
                    throw new NotSupportedException("ERROR: SELF is encrypted, decrypt it first (only fake-signed SELF is supported).");
                }
                entries.Add((offset, size, false));
            }
            // trailing data after the last entry (SCE version segment)
            if (entryCount > 0)
            {
                var last = entries[entryCount - 1];
                var end = last.offset + last.size;
                if (end < (ulong)self.Length)
                    entries.Add((end, (ulong)self.Length - end, false));
            }

            var elf = 0x20 + entryCount * 32;
            var phoff = (int)BitConverter.ToUInt64(self, elf + 0x20);
            var phentsize = BitConverter.ToUInt16(self, elf + 0x36);
            var phnum = BitConverter.ToUInt16(self, elf + 0x38);
            var headerEnd = phoff + phnum * phentsize;
            var phdrs = new List<(ulong offset, ulong filesz)>();
            var total = (ulong)headerEnd;
            for (var i = 0; i < phnum; i++)
            {
                var ph = elf + phoff + i * phentsize;
                var offset = BitConverter.ToUInt64(self, ph + 8);
                var filesz = BitConverter.ToUInt64(self, ph + 32);
                phdrs.Add((offset, filesz));
                total = Math.Max(total, offset + filesz);
            }

            var output = new byte[total];
            Buffer.BlockCopy(self, elf, output, 0, headerEnd);
            foreach (var (offset, filesz) in phdrs)
            {
                if (filesz == 0) continue;
                // each blob goes to the first unused program header with the same file size
                for (var i = 0; i < entries.Count; i++)
                {
                    var entry = entries[i];
                    if (entry.used || entry.size != filesz) continue;
                    Buffer.BlockCopy(self, (int)entry.offset, output, (int)offset, (int)filesz);
                    entries[i] = (entry.offset, entry.size, true);
                    break;
                }
            }
            return output;
        }
    }
}
