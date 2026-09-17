using System;
using System.Runtime.InteropServices;

namespace Il2CppDumper
{
    // comdlg32 GetOpenFileName instead of the IFileDialog COM RCW: built-in COM interop is not available under NativeAOT
    public class OpenFileDialog
    {
        public string Title { get; set; }
        public string Filter { get; set; }
        public string FileName { get; set; }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct OPENFILENAME
        {
            public int lStructSize;
            public IntPtr hwndOwner;
            public IntPtr hInstance;
            public string lpstrFilter;
            public IntPtr lpstrCustomFilter;
            public int nMaxCustFilter;
            public int nFilterIndex;
            public IntPtr lpstrFile;
            public int nMaxFile;
            public IntPtr lpstrFileTitle;
            public int nMaxFileTitle;
            public IntPtr lpstrInitialDir;
            public string lpstrTitle;
            public int Flags;
            public short nFileOffset;
            public short nFileExtension;
            public IntPtr lpstrDefExt;
            public IntPtr lCustData;
            public IntPtr lpfnHook;
            public IntPtr lpTemplateName;
            public IntPtr pvReserved;
            public int dwReserved;
            public int FlagsEx;
        }

        [DllImport("comdlg32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool GetOpenFileNameW(ref OPENFILENAME ofn);

        private const int OFN_FILEMUSTEXIST = 0x1000;
        private const int OFN_PATHMUSTEXIST = 0x800;
        private const int OFN_NOCHANGEDIR = 0x8;
        private const int OFN_EXPLORER = 0x80000;
        private const int OFN_DONTADDTORECENT = 0x2000000;
        private const int MaxPath = 32768;

        public bool ShowDialog()
        {
            var buffer = Marshal.AllocHGlobal(MaxPath * 2);
            try
            {
                Marshal.WriteInt16(buffer, 0);
                var ofn = new OPENFILENAME
                {
                    lStructSize = Marshal.SizeOf<OPENFILENAME>(),
                    lpstrFilter = string.IsNullOrEmpty(Filter) ? null : Filter.Replace('|', '\0') + "\0\0",
                    nFilterIndex = 1,
                    lpstrFile = buffer,
                    nMaxFile = MaxPath,
                    lpstrTitle = string.IsNullOrEmpty(Title) ? null : Title,
                    Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_DONTADDTORECENT,
                };
                if (!GetOpenFileNameW(ref ofn))
                {
                    return false;
                }
                FileName = Marshal.PtrToStringUni(buffer);
                return true;
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
    }
}
