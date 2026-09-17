using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace Il2CppDumper
{
    /// <summary>
    /// Reconstructs Il2CppCodeRegistration for x86-64 binaries where the linker (LTO, seen with the Sony PS4
    /// toolchain) folded the struct into code so it no longer exists in data. The tables it pointed to still
    /// exist. Their starts are either targets of rip-relative lea instructions or stored as pointers in data;
    /// both are used as anchors to delimit table candidates. Needs a found Il2CppMetadataRegistration.
    /// Version 24.2+ (code gen modules). Only codeGenModules, genericMethodPointers and invokerPointers
    /// are recovered, the rest of the struct stays zero.
    /// </summary>
    public class LtoSearch
    {
        private readonly Il2Cpp il2Cpp;
        private readonly int imageCount;
        private readonly List<(SearchSection sec, byte[] buf, bool exec)> segs = new();
        private readonly HashSet<ulong> anchors = new();

        public LtoSearch(Il2Cpp il2Cpp, SectionHelper helper, int imageCount)
        {
            this.il2Cpp = il2Cpp;
            this.imageCount = imageCount;
            foreach (var (list, exec) in new[] { (helper.Exec, true), (helper.Data, false) })
            {
                foreach (var sec in list.OrderByDescending(x => x.offsetEnd - x.offset))
                {
                    var size = (long)Math.Min(sec.offsetEnd, il2Cpp.Length) - (long)sec.offset;
                    if (size <= 0 || segs.Any(s => s.sec.offset <= sec.offset && sec.offsetEnd <= s.sec.offsetEnd))
                        continue; // empty or contained in an already loaded segment
                    il2Cpp.Position = sec.offset;
                    segs.Add((sec, il2Cpp.ReadBytes((int)size), exec));
                }
            }
        }

        public bool Search(ulong metadataRegistration)
        {
            if (metadataRegistration == 0)
            {
                Console.WriteLine("ERROR: MetadataRegistration is needed to reconstruct CodeRegistration");
                return false;
            }
            var mr = il2Cpp.MapVATR<Il2CppMetadataRegistration>(metadataRegistration);
            ScanAnchors();

            var codeGenModules = FindCodeGenModules();
            if (codeGenModules == 0)
            {
                Console.WriteLine("ERROR: codeGenModules not found");
                return false;
            }
            Console.WriteLine("codeGenModules : {0:x} ({1})", codeGenModules, imageCount);

            // expected table sizes from the indices that reference them
            var maxMethodIndex = -1;
            var maxInvokerIndex = -1;
            foreach (var entry in il2Cpp.MapVATR<Il2CppGenericMethodFunctionsDefinitions>(mr.genericMethodTable, mr.genericMethodTableCount))
            {
                maxMethodIndex = Math.Max(maxMethodIndex, entry.indices.methodIndex);
                maxInvokerIndex = Math.Max(maxInvokerIndex, entry.indices.invokerIndex);
            }
            var moduleTables = new HashSet<ulong>();
            foreach (var pModule in Qwords(codeGenModules, imageCount))
            {
                var module = il2Cpp.MapVATR<Il2CppCodeGenModule>(pModule);
                moduleTables.Add(module.methodPointers);
                moduleTables.Add(module.adjustorThunks);
                if (module.invokerIndices != 0)
                {
                    foreach (var i in il2Cpp.MapVATR<int>(module.invokerIndices, module.methodPointerCount))
                        maxInvokerIndex = Math.Max(maxInvokerIndex, i);
                }
            }
            var funcRuns = QwordRuns(v => v == 0 || InExec(v)).Where(r => anchors.Contains(r.start) && !moduleTables.Contains(r.start)).ToList();
            var (genericMethodPointers, genericMethodPointersCount) = PickFuncArray(funcRuns, maxMethodIndex + 1);
            Console.WriteLine("genericMethodPointers : {0:x} ({1})", genericMethodPointers, genericMethodPointersCount);
            var (invokerPointers, invokerPointersCount) = PickFuncArray(funcRuns, maxInvokerIndex + 1);
            Console.WriteLine("invokerPointers : {0:x} ({1})", invokerPointers, invokerPointersCount);
            if (genericMethodPointers == 0)
            {
                Console.WriteLine("WARNING: generic method pointers not found, generic method addresses will be missing");
                mr.genericMethodTableCount = 0; // table without pointers would index out of range
            }

            var cr = new Il2CppCodeRegistration
            {
                genericMethodPointersCount = (ulong)genericMethodPointersCount,
                genericMethodPointers = genericMethodPointers,
                invokerPointersCount = (ulong)invokerPointersCount,
                invokerPointers = invokerPointers,
                codeGenModulesCount = (ulong)imageCount,
                codeGenModules = codeGenModules,
            };
            il2Cpp.Init(cr, mr);
            return true;
        }

        #region memory helpers
        private bool InExec(ulong va) => segs.Any(s => s.exec && va >= s.sec.address && va < s.sec.addressEnd);

        private bool TryRead(ulong va, int size, out (byte[] buf, int off) loc)
        {
            foreach (var s in segs)
            {
                var off = va - s.sec.address; // garbage va must not overflow anywhere in here
                if (va >= s.sec.address && off < (ulong)s.buf.Length && (ulong)size <= (ulong)s.buf.Length - off)
                {
                    loc = (s.buf, (int)off);
                    return true;
                }
            }
            loc = default;
            return false;
        }

        private bool TryRead64(ulong va, out ulong value)
        {
            value = 0;
            if (!TryRead(va, 8, out var loc)) return false;
            value = BitConverter.ToUInt64(loc.buf, loc.off);
            return true;
        }

        private IEnumerable<ulong> Qwords(ulong va, long count)
        {
            for (long i = 0; i < count; i++)
            {
                TryRead64(va + (ulong)i * 8, out var v);
                yield return v;
            }
        }
        #endregion

        /// <summary>Anchors: targets of rip-relative 64-bit lea (REX.W 8D /r, mod=00 rm=101) plus every pointer stored in data.</summary>
        private void ScanAnchors()
        {
            foreach (var s in segs)
            {
                var buf = s.buf;
                if (s.exec)
                {
                    for (var i = 0; i + 7 <= buf.Length; i++)
                    {
                        if ((buf[i] & 0xF8) == 0x48 && buf[i + 1] == 0x8D && (buf[i + 2] & 0xC7) == 0x05)
                        {
                            var disp = BitConverter.ToInt32(buf, i + 3);
                            anchors.Add(s.sec.address + (ulong)i + 7 + (ulong)(long)disp);
                        }
                    }
                }
                else
                {
                    for (var i = 0; i + 8 <= buf.Length; i += 8)
                    {
                        anchors.Add(BitConverter.ToUInt64(buf, i));
                    }
                }
            }
        }

        /// <summary>Runs of consecutive 8-byte aligned qwords satisfying <paramref name="valid"/>, split at anchors.</summary>
        private IEnumerable<(ulong start, int count)> QwordRuns(Func<ulong, bool> valid)
        {
            foreach (var s in segs.Where(x => !x.exec))
            {
                var n = s.buf.Length / 8;
                var runStart = -1;
                for (var i = 0; i <= n; i++)
                {
                    var va = s.sec.address + (ulong)i * 8;
                    var ok = i < n && valid(BitConverter.ToUInt64(s.buf, i * 8));
                    if (runStart >= 0 && (!ok || anchors.Contains(va)))
                    {
                        yield return (s.sec.address + (ulong)runStart * 8, i - runStart);
                        runStart = -1;
                    }
                    if (ok && runStart < 0)
                    {
                        runStart = i;
                    }
                }
            }
        }

        private (ulong start, int count) PickFuncArray(List<(ulong start, int count)> runs, int expected)
        {
            if (expected <= 0) return (0, 0);
            // exact length first; the generic adjustor thunk table has the same length as genericMethodPointers but is mostly null
            var exact = runs.Where(r => r.count == expected).OrderBy(r => Qwords(r.start, r.count).Count(x => x == 0)).ToList();
            if (exact.Count > 0) return exact[0];
            return runs.Where(r => r.count > expected).OrderBy(r => r.count).FirstOrDefault();
        }

        private static readonly byte[] mscorlib = Encoding.ASCII.GetBytes("mscorlib.dll\0");

        private bool IsModuleName(ulong va)
        {
            if (!TryRead(va, 4, out var loc)) return false;
            var end = Math.Min(loc.buf.Length, loc.off + 260);
            var i = loc.off;
            while (i < end && loc.buf[i] >= 0x20 && loc.buf[i] < 0x7f) i++;
            return i < end && loc.buf[i] == 0 && i - loc.off >= 3; // "*.dll" or "__Generated"
        }

        private bool IsModulePointer(ulong p) => (p & 7) == 0 && TryRead64(p, out var name) && IsModuleName(name);

        private IEnumerable<ulong> RefsTo(ulong target)
        {
            foreach (var s in segs.Where(x => !x.exec))
            {
                for (var i = 0; i + 8 <= s.buf.Length; i += 8)
                {
                    if (BitConverter.ToUInt64(s.buf, i) == target)
                        yield return s.sec.address + (ulong)i;
                }
            }
        }

        /// <summary>mscorlib.dll string -> Il2CppCodeGenModule -> entry in the codeGenModules table -> table start.</summary>
        private ulong FindCodeGenModules()
        {
            foreach (var s in segs)
            {
                foreach (var index in s.buf.Search(mscorlib))
                {
                    var dll = s.sec.address + (ulong)index;
                    foreach (var module in RefsTo(dll))
                    {
                        foreach (var entry in RefsTo(module))
                        {
                            var start = entry;
                            while (TryRead64(start - 8, out var prev) && IsModulePointer(prev))
                                start -= 8;
                            var count = 0;
                            while (TryRead64(start + (ulong)count * 8, out var p) && IsModulePointer(p))
                                count++;
                            if (count == imageCount)
                                return start;
                            // neighbouring module tables merged into one run: the real one starts at an anchor
                            for (var candidate = start; candidate <= entry; candidate += 8)
                            {
                                if (anchors.Contains(candidate) && (long)(candidate - start) / 8 + imageCount <= count)
                                    return candidate;
                            }
                        }
                    }
                }
            }
            return 0;
        }
    }
}
