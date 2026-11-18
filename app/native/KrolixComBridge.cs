using System;
using System.IO;
using System.Text;
using System.Net;
using System.Diagnostics;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Krolix.Com
{
    /// <summary>
    /// Zero COM Interface: IKrolixLinkTransmitter
    /// IID: 4BD46AAE-C51F-4BF7-8BC0-2E86E33D1873
    /// </summary>
    [ComVisible(true)]
    [Guid("4BD46AAE-C51F-4BF7-8BC0-2E86E33D1873")]
    [InterfaceType(ComInterfaceType.InterfaceIsDual)]
    public interface IKrolixLinkTransmitter
    {
        [DispId(1)]
        int SendLink(
            [MarshalAs(UnmanagedType.BStr)] string bstrUrl,
            [MarshalAs(UnmanagedType.BStr)] string bstrReferer,
            [MarshalAs(UnmanagedType.BStr)] string bstrCookies,
            [MarshalAs(UnmanagedType.BStr)] string bstrData,
            [MarshalAs(UnmanagedType.BStr)] string bstrUser,
            [MarshalAs(UnmanagedType.BStr)] string bstrPassword,
            [MarshalAs(UnmanagedType.BStr)] string bstrLocalPath,
            [MarshalAs(UnmanagedType.BStr)] string bstrLocalFileName,
            int lFlags);
    }

    /// <summary>
    /// Zero COM Interface: IKrolixLinkTransmitter2
    /// IID: 94D09862-1875-4FC9-B434-91CF25C840A1
    /// </summary>
    [ComVisible(true)]
    [Guid("94D09862-1875-4FC9-B434-91CF25C840A1")]
    [InterfaceType(ComInterfaceType.InterfaceIsDual)]
    public interface IKrolixLinkTransmitter2 : IKrolixLinkTransmitter
    {
        [DispId(1)]
        new int SendLink(
            [MarshalAs(UnmanagedType.BStr)] string bstrUrl,
            [MarshalAs(UnmanagedType.BStr)] string bstrReferer,
            [MarshalAs(UnmanagedType.BStr)] string bstrCookies,
            [MarshalAs(UnmanagedType.BStr)] string bstrData,
            [MarshalAs(UnmanagedType.BStr)] string bstrUser,
            [MarshalAs(UnmanagedType.BStr)] string bstrPassword,
            [MarshalAs(UnmanagedType.BStr)] string bstrLocalPath,
            [MarshalAs(UnmanagedType.BStr)] string bstrLocalFileName,
            int lFlags);

        [DispId(2)]
        int SendLink2(
            [MarshalAs(UnmanagedType.BStr)] string bstrUrl,
            [MarshalAs(UnmanagedType.BStr)] string bstrReferer,
            [MarshalAs(UnmanagedType.BStr)] string bstrCookies,
            [MarshalAs(UnmanagedType.BStr)] string bstrData,
            [MarshalAs(UnmanagedType.BStr)] string bstrUser,
            [MarshalAs(UnmanagedType.BStr)] string bstrPassword,
            [MarshalAs(UnmanagedType.BStr)] string bstrLocalPath,
            [MarshalAs(UnmanagedType.BStr)] string bstrLocalFileName,
            int lFlags,
            object reserved1,
            object reserved2);

        [DispId(3)]
        int SendLinksArray(
            [MarshalAs(UnmanagedType.BStr)] string location,
            ref object pLinksArray);
    }

    /// <summary>
    /// Krolix.LinkTransmitter COM Automation Class
    /// CLSID: AC746233-E9D3-49CD-862F-068F7B7CCCA4
    /// </summary>
    [ComVisible(true)]
    [Guid("AC746233-E9D3-49CD-862F-068F7B7CCCA4")]
    [ProgId("Krolix.LinkTransmitter")]
    [ClassInterface(ClassInterfaceType.None)]
    public class KrolixLinkTransmitter : IKrolixLinkTransmitter2, IKrolixLinkTransmitter
    {
        public const string CLSID_OFFICIAL = "{AC746233-E9D3-49CD-862F-068F7B7CCCA4}";
        public const string CLSID_COMPAT = "{ACFA5228-B05E-4B07-9E45-8C9B47BEA437}";
        public const string PROGID = "Krolix.LinkTransmitter";
        public const string API_DOWNLOAD_URL = "http://127.0.0.1:9666/download";
        public const string API_BATCH_URL = "http://127.0.0.1:9666/batch-download";

        public int SendLink(
            string bstrUrl,
            string bstrReferer,
            string bstrCookies,
            string bstrData,
            string bstrUser,
            string bstrPassword,
            string bstrLocalPath,
            string bstrLocalFileName,
            int lFlags)
        {
            return SendLink2(bstrUrl, bstrReferer, bstrCookies, bstrData, bstrUser, bstrPassword, bstrLocalPath, bstrLocalFileName, lFlags, null, null);
        }

        public int SendLink2(
            string bstrUrl,
            string bstrReferer,
            string bstrCookies,
            string bstrData,
            string bstrUser,
            string bstrPassword,
            string bstrLocalPath,
            string bstrLocalFileName,
            int lFlags,
            object reserved1,
            object reserved2)
        {
            if (string.IsNullOrEmpty(bstrUrl))
                return -1; // E_FAIL

            string userAgent = "";
            if (reserved1 != null)
            {
                try { userAgent = reserved1.ToString(); } catch { }
            }

            bool silent = (lFlags & 1) != 0;
            bool queueOnly = (lFlags & 2) != 0;

            string json = string.Format(
                "{{\"url\":\"{0}\",\"referer\":\"{1}\",\"cookies\":\"{2}\",\"post_data\":\"{3}\",\"user\":\"{4}\",\"password\":\"{5}\",\"save_dir\":\"{6}\",\"filename\":\"{7}\",\"user_agent\":\"{8}\",\"silent\":{9},\"queue_only\":{10}}}",
                EscapeJson(bstrUrl),
                EscapeJson(bstrReferer),
                EscapeJson(bstrCookies),
                EscapeJson(bstrData),
                EscapeJson(bstrUser),
                EscapeJson(bstrPassword),
                EscapeJson(bstrLocalPath),
                EscapeJson(bstrLocalFileName),
                EscapeJson(userAgent),
                silent ? "true" : "false",
                queueOnly ? "true" : "false"
            );

            bool ok = PostJson(API_DOWNLOAD_URL, json);
            if (!ok)
            {
                // Fallback: Launch Krolix.exe directly
                LaunchZeroCli(bstrUrl, bstrLocalPath, bstrLocalFileName, silent, queueOnly);
            }

            return 0; // S_OK
        }

        public int SendLinksArray(string location, ref object pLinksArray)
        {
            if (pLinksArray == null)
                return -1;

            List<Dictionary<string, string>> items = new List<Dictionary<string, string>>();
            string userAgent = "";

            try
            {
                Array arr = pLinksArray as Array;
                if (arr != null && arr.Rank == 2)
                {
                    int rowCount = arr.GetLength(0);
                    int colCount = arr.GetLength(1);

                    for (int i = 0; i < rowCount; i++)
                    {
                        string url = GetArrayVal(arr, i, 0);
                        string cookies = colCount > 1 ? GetArrayVal(arr, i, 1) : "";
                        string descr = colCount > 2 ? GetArrayVal(arr, i, 2) : "";
                        if (i == 0 && colCount > 3)
                        {
                            userAgent = GetArrayVal(arr, 0, 3);
                        }

                        if (!string.IsNullOrEmpty(url))
                        {
                            var dict = new Dictionary<string, string>();
                            dict["url"] = url;
                            dict["cookies"] = cookies;
                            dict["description"] = descr;
                            items.Add(dict);
                        }
                    }
                }
                else if (arr != null && arr.Rank == 1)
                {
                    for (int i = 0; i < arr.Length; i++)
                    {
                        object v = arr.GetValue(i);
                        if (v != null)
                        {
                            var dict = new Dictionary<string, string>();
                            dict["url"] = v.ToString();
                            items.Add(dict);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Trace.WriteLine("[ZeroCOM] Error parsing pLinksArray: " + ex.Message);
            }

            if (items.Count == 0)
                return -1;

            // Build Batch JSON
            StringBuilder sb = new StringBuilder();
            sb.Append("{");
            sb.AppendFormat("\"referer\":\"{0}\",", EscapeJson(location));
            sb.AppendFormat("\"user_agent\":\"{0}\",", EscapeJson(userAgent));
            sb.Append("\"items\":[");
            for (int i = 0; i < items.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.AppendFormat("{{\"url\":\"{0}\",\"cookies\":\"{1}\",\"description\":\"{2}\"}}",
                    EscapeJson(items[i]["url"]),
                    EscapeJson(items[i].ContainsKey("cookies") ? items[i]["cookies"] : ""),
                    EscapeJson(items[i].ContainsKey("description") ? items[i]["description"] : ""));
            }
            sb.Append("]}");

            bool ok = PostJson(API_BATCH_URL, sb.ToString());
            if (!ok)
            {
                // Fallback: Launch Zero with first URL or batch
                if (items.Count > 0)
                {
                    LaunchZeroCli(items[0]["url"], "", "", false, true);
                }
            }

            return 0; // S_OK
        }

        private static string GetArrayVal(Array arr, int r, int c)
        {
            try
            {
                object v = arr.GetValue(r, c);
                return v != null ? v.ToString() : "";
            }
            catch { return ""; }
        }

        private static bool PostJson(string endpoint, string json)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(endpoint);
                req.Method = "POST";
                req.ContentType = "application/json; charset=utf-8";
                req.Headers.Add("X-Zero-Client", "zero-com");
                req.Timeout = 2500;

                byte[] data = Encoding.UTF8.GetBytes(json);
                req.ContentLength = data.Length;

                using (Stream s = req.GetRequestStream())
                {
                    s.Write(data, 0, data.Length);
                }

                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    return resp.StatusCode == HttpStatusCode.OK;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void LaunchZeroCli(string url, string saveDir, string fileName, bool silent, bool queueOnly)
        {
            string zeroExe = FindZeroExe();
            if (File.Exists(zeroExe))
            {
                StringBuilder cli = new StringBuilder();
                cli.AppendFormat("/d \"{0}\"", url);
                if (!string.IsNullOrEmpty(saveDir)) cli.AppendFormat(" /p \"{0}\"", saveDir);
                if (!string.IsNullOrEmpty(fileName)) cli.AppendFormat(" /f \"{0}\"", fileName);
                if (silent) cli.Append(" /n");
                if (queueOnly) cli.Append(" /a");

                ProcessStartInfo psi = new ProcessStartInfo(zeroExe, cli.ToString());
                psi.UseShellExecute = true;
                Process.Start(psi);
            }
        }

        private static string FindZeroExe()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string[] candidates = new string[]
            {
                Path.Combine(baseDir, "Krolix.exe"),
                Path.GetFullPath(Path.Combine(baseDir, "..", "..", "Krolix.exe")),
                Path.Combine(baseDir, "dist", "Zero", "Krolix.exe"),
                Path.GetFullPath(Path.Combine(baseDir, "..", "..", "dist", "Zero", "Krolix.exe")),
                Environment.ExpandEnvironmentVariables(@"%LOCALAPPDATA%\Programs\Krolix Download Manager\Krolix.exe")
            };

            foreach (var p in candidates)
            {
                if (File.Exists(p)) return p;
            }
            return "";
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n").Replace("\t", "\\t");
        }

        /// <summary>
        /// Registers COM keys in HKCU so any process can call CreateObject("Krolix.LinkTransmitter")
        /// </summary>
        public static bool RegisterInHkcu(string dllPath)
        {
            try
            {
                string asmName = "KrolixComBridge, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
                string codeBase = "file:///" + dllPath.Replace('\\', '/');

                string[] clsids = new string[] { CLSID_OFFICIAL, CLSID_COMPAT };

                // 1. ProgID
                using (RegistryKey prog = Registry.CurrentUser.CreateSubKey(@"Software\Classes\" + PROGID))
                {
                    prog.SetValue("", "Krolix Download Manager Link Transmitter");
                    using (RegistryKey clsidK = prog.CreateSubKey("CLSID"))
                    {
                        clsidK.SetValue("", CLSID_OFFICIAL);
                    }
                }

                // 2. CLSIDs
                foreach (string clsid in clsids)
                {
                    using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Classes\CLSID\" + clsid))
                    {
                        key.SetValue("", "Krolix.Com.KrolixLinkTransmitter");
                        using (RegistryKey ip = key.CreateSubKey("InprocServer32"))
                        {
                            ip.SetValue("", "mscoree.dll");
                            ip.SetValue("ThreadingModel", "Both");
                            ip.SetValue("Class", "Krolix.Com.KrolixLinkTransmitter");
                            ip.SetValue("Assembly", asmName);
                            ip.SetValue("RuntimeVersion", "v4.0.30319");
                            ip.SetValue("CodeBase", codeBase);
                        }
                        using (RegistryKey pr = key.CreateSubKey("ProgID"))
                        {
                            pr.SetValue("", PROGID);
                        }
                    }
                }

                // 3. App Paths
                string zeroExe = FindZeroExe();
                if (!string.IsNullOrEmpty(zeroExe))
                {
                    using (RegistryKey ap = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\App Paths\Krolix.exe"))
                    {
                        ap.SetValue("", zeroExe);
                        ap.SetValue("Path", Path.GetDirectoryName(zeroExe));
                    }
                }

                return true;
            }
            catch (Exception ex)
            {
                Trace.WriteLine("[ZeroCOM] Register error: " + ex.Message);
                return false;
            }
        }

        public static bool UnregisterInHkcu()
        {
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\" + PROGID, false);
                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\CLSID\" + CLSID_OFFICIAL, false);
                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\CLSID\" + CLSID_COMPAT, false);
                return true;
            }
            catch { return false; }
        }
    }

    /// <summary>
    /// Standalone registrar entry point when executed as exe or called from regasm.
    /// </summary>
    public static class Registrar
    {
        public static int Main(string[] args)
        {
            if (args.Length > 0 && args[0].ToLowerInvariant() == "/u")
            {
                bool u = KrolixLinkTransmitter.UnregisterInHkcu();
                Console.WriteLine(u ? "UNREGISTER_OK" : "UNREGISTER_FAIL");
                return u ? 0 : 1;
            }

            string selfDll = typeof(KrolixLinkTransmitter).Assembly.Location;
            bool ok = KrolixLinkTransmitter.RegisterInHkcu(selfDll);
            Console.WriteLine(ok ? "REGISTER_OK" : "REGISTER_FAIL");
            return ok ? 0 : 1;
        }
    }
}
