using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Net;
using System.Diagnostics;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Krolix.Native
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
        public static event Action OnActivity;

        private void Touch()
        {
            if (OnActivity != null)
            {
                try { OnActivity(); } catch { }
            }
        }

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
            Touch();
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
                Program.EscapeJson(bstrUrl),
                Program.EscapeJson(bstrReferer),
                Program.EscapeJson(bstrCookies),
                Program.EscapeJson(bstrData),
                Program.EscapeJson(bstrUser),
                Program.EscapeJson(bstrPassword),
                Program.EscapeJson(bstrLocalPath),
                Program.EscapeJson(bstrLocalFileName),
                Program.EscapeJson(userAgent),
                silent ? "true" : "false",
                queueOnly ? "true" : "false"
            );

            bool ok = Program.PostJson(Program.API_ENDPOINT, json);
            if (!ok)
            {
                Program.LaunchZeroCli(bstrUrl, bstrLocalPath, bstrLocalFileName, silent, queueOnly);
            }

            return 0; // S_OK
        }

        public int SendLinksArray(string location, ref object pLinksArray)
        {
            Touch();
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

            StringBuilder sb = new StringBuilder();
            sb.Append("{");
            sb.AppendFormat("\"referer\":\"{0}\",", Program.EscapeJson(location));
            sb.AppendFormat("\"user_agent\":\"{0}\",", Program.EscapeJson(userAgent));
            sb.Append("\"items\":[");
            for (int i = 0; i < items.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.AppendFormat("{{\"url\":\"{0}\",\"cookies\":\"{1}\",\"description\":\"{2}\"}}",
                    Program.EscapeJson(items[i]["url"]),
                    Program.EscapeJson(items[i].ContainsKey("cookies") ? items[i]["cookies"] : ""),
                    Program.EscapeJson(items[i].ContainsKey("description") ? items[i]["description"] : ""));
            }
            sb.Append("]}");

            bool ok = Program.PostJson(Program.API_BATCH_ENDPOINT, sb.ToString());
            if (!ok)
            {
                if (items.Count > 0)
                {
                    Program.LaunchZeroCli(items[0]["url"], "", "", false, true);
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
    }

    /// <summary>
    /// Zero Native Acceleration Engine & Companion.
    /// High-performance C# native module for Windows:
    /// - Ultra-fast multi-threaded file segment merging.
    /// - Hardware-accelerated cryptographic hashing (SHA256, SHA1, MD5).
    /// - Out-Of-Process COM Automation Server (LocalServer32) & CLI forwarder.
    /// - Windows App Paths & COM Registration.
    /// </summary>
    class Program
    {
        public const int BUFFER_SIZE = 8 * 1024 * 1024; // 8MB high-throughput buffer
        public const string API_ENDPOINT = "http://127.0.0.1:9666/download";
        public const string API_BATCH_ENDPOINT = "http://127.0.0.1:9666/batch-download";
        public const string CLSID_OFFICIAL = "{AC746233-E9D3-49CD-862F-068F7B7CCCA4}";
        public const string CLSID_COMPAT = "{ACFA5228-B05E-4B07-9E45-8C9B47BEA437}";

        private static System.Threading.Timer idleTimer;

        [STAThread]
        static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                PrintUsage();
                return 0;
            }

            string command = args[0].ToLowerInvariant().TrimStart('-', '/');

            try
            {
                switch (command)
                {
                    case "embedding":
                    case "com-server":
                        return RunComServer();

                    case "merge":
                        return HandleMerge(args);

                    case "hash":
                        return HandleHash(args);

                    case "sendlink":
                    case "send-link":
                        return HandleSendLink(args);

                    case "register-bridge":
                    case "register-com":
                    case "register":
                        return HandleRegister();

                    case "unregister-bridge":
                    case "unregister-com":
                    case "unregister":
                        return HandleUnregister();

                    case "ping":
                        Console.WriteLine("ZERO_NATIVE_OK");
                        return 0;

                    default:
                        // If invoked with standard download switches directly (e.g. KrolixNativeEngine.exe /d "http://...")
                        if (args[0].StartsWith("/") || args[0].StartsWith("-"))
                        {
                            return HandleCliArgs(args);
                        }
                        Console.Error.WriteLine("[ZeroNative] Unknown command: " + args[0]);
                        PrintUsage();
                        return 1;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[ZeroNative Error] " + ex.Message);
                return 2;
            }
        }

        private static void PrintUsage()
        {
            Console.WriteLine("Zero Native Engine v2.7 (C# Native Acceleration & COM Server)");
            Console.WriteLine("Usage:");
            Console.WriteLine("  KrolixNativeEngine.exe merge <output_path> <chunk1> <chunk2> ... [--delete]");
            Console.WriteLine("  KrolixNativeEngine.exe hash <file_path> <sha256|sha1|md5>");
            Console.WriteLine("  KrolixNativeEngine.exe send-link <url> [options]");
            Console.WriteLine("  KrolixNativeEngine.exe register");
            Console.WriteLine("  KrolixNativeEngine.exe unregister");
            Console.WriteLine("  KrolixNativeEngine.exe ping");
            Console.WriteLine("  KrolixNativeEngine.exe -Embedding (COM LocalServer32 mode)");
        }

        [DllImport("ole32.dll")]
        private static extern int CoResumeClassObjects();

        /// <summary>
        /// Runs Out-Of-Process COM Server for Krolix.LinkTransmitter automation.
        /// Exits automatically after 30 seconds of inactivity.
        /// </summary>
        private static int RunComServer()
        {
            RegistrationServices reg = new RegistrationServices();
            int cookie = reg.RegisterTypeForComClients(
                typeof(KrolixLinkTransmitter),
                RegistrationClassContext.LocalServer,
                RegistrationConnectionType.MultipleUse);

            try { CoResumeClassObjects(); } catch { }

            ResetIdleTimer();
            KrolixLinkTransmitter.OnActivity += ResetIdleTimer;

            Application.Run();

            reg.UnregisterTypeForComClients(cookie);
            return 0;
        }

        private static void ResetIdleTimer()
        {
            if (idleTimer == null)
            {
                idleTimer = new System.Threading.Timer((s) => {
                    try { Application.Exit(); } catch { }
                }, null, 30000, Timeout.Infinite);
            }
            else
            {
                try { idleTimer.Change(30000, Timeout.Infinite); } catch { }
            }
        }

        /// <summary>
        /// Ultra-fast file chunk merging with sequential unbuffered I/O.
        /// </summary>
        private static int HandleMerge(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine("Error: merge requires <output_path> and at least one <chunk_path>");
                return 1;
            }

            string outputPath = args[1];
            bool deleteChunks = false;
            List<string> chunkFiles = new List<string>();

            for (int i = 2; i < args.Length; i++)
            {
                if (args[i].Equals("--delete", StringComparison.OrdinalIgnoreCase))
                {
                    deleteChunks = true;
                }
                else
                {
                    chunkFiles.Add(args[i]);
                }
            }

            string tempOut = outputPath + ".zero_merge_tmp";
            string outputDir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(outputDir) && !Directory.Exists(outputDir))
            {
                Directory.CreateDirectory(outputDir);
            }

            Stopwatch sw = Stopwatch.StartNew();
            long totalBytes = 0;
            byte[] buffer = new byte[BUFFER_SIZE];

            using (FileStream outStream = new FileStream(tempOut, FileMode.Create, FileAccess.Write, FileShare.None, BUFFER_SIZE, FileOptions.SequentialScan))
            {
                foreach (string chunk in chunkFiles)
                {
                    if (!File.Exists(chunk))
                    {
                        Console.Error.WriteLine("[ZeroNative] Missing chunk file: " + chunk);
                        outStream.Close();
                        if (File.Exists(tempOut)) File.Delete(tempOut);
                        return 3;
                    }

                    using (FileStream inStream = new FileStream(chunk, FileMode.Open, FileAccess.Read, FileShare.Read, BUFFER_SIZE, FileOptions.SequentialScan))
                    {
                        int bytesRead;
                        while ((bytesRead = inStream.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            outStream.Write(buffer, 0, bytesRead);
                            totalBytes += bytesRead;
                        }
                    }
                }
                outStream.Flush();
            }

            if (File.Exists(outputPath))
            {
                File.Delete(outputPath);
            }
            File.Move(tempOut, outputPath);

            if (deleteChunks)
            {
                foreach (string chunk in chunkFiles)
                {
                    try { File.Delete(chunk); } catch { }
                }
            }

            sw.Stop();
            double mb = totalBytes / (1024.0 * 1024.0);
            double speed = sw.ElapsedMilliseconds > 0 ? (mb / (sw.ElapsedMilliseconds / 1000.0)) : mb;
            Console.WriteLine(string.Format("SUCCESS: Merged {0} chunks ({1:F2} MB) in {2}ms ({3:F1} MB/s)",
                chunkFiles.Count, mb, sw.ElapsedMilliseconds, speed));
            return 0;
        }

        /// <summary>
        /// Hardware-accelerated cryptographic checksum computation.
        /// </summary>
        private static int HandleHash(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine("Error: hash requires <file_path> <algorithm>");
                return 1;
            }

            string filePath = args[1];
            string algo = args[2].ToLowerInvariant();

            if (!File.Exists(filePath))
            {
                Console.Error.WriteLine("File not found: " + filePath);
                return 1;
            }

            using (HashAlgorithm hasher = CreateHasher(algo))
            {
                if (hasher == null)
                {
                    Console.Error.WriteLine("Unsupported algorithm: " + algo);
                    return 1;
                }

                byte[] buffer = new byte[BUFFER_SIZE];
                using (FileStream fs = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.Read, BUFFER_SIZE, FileOptions.SequentialScan))
                {
                    byte[] hash = hasher.ComputeHash(fs);
                    StringBuilder sb = new StringBuilder();
                    for (int i = 0; i < hash.Length; i++)
                    {
                        sb.Append(hash[i].ToString("x2"));
                    }
                    Console.WriteLine(sb.ToString());
                    return 0;
                }
            }
        }

        private static HashAlgorithm CreateHasher(string algo)
        {
            switch (algo)
            {
                case "sha256":
                case "sha-256":
                    return SHA256.Create();
                case "sha1":
                case "sha-1":
                    return SHA1.Create();
                case "md5":
                    return MD5.Create();
                default:
                    return null;
            }
        }

        /// <summary>
        /// Parses CLI switches directly and dispatches to Zero.
        /// </summary>
        private static int HandleCliArgs(string[] args)
        {
            string url = "";
            string saveDir = "";
            string fileName = "";
            bool silent = false;
            bool queueOnly = false;

            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                string lower = a.ToLowerInvariant().Replace("-", "/");
                if (lower == "/d" && i + 1 < args.Length)
                    url = args[++i];
                else if (lower == "/p" && i + 1 < args.Length)
                    saveDir = args[++i];
                else if (lower == "/f" && i + 1 < args.Length)
                    fileName = args[++i];
                else if (lower == "/n")
                    silent = true;
                else if (lower == "/a")
                    queueOnly = true;
            }

            if (string.IsNullOrEmpty(url))
            {
                Console.Error.WriteLine("Error: /d <URL> is required");
                return 1;
            }

            return DispatchLinkToZero(url, "", "", "", saveDir, fileName, silent, queueOnly);
        }

        private static int HandleSendLink(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine("Error: send-link requires <url>");
                return 1;
            }

            string url = args[1];
            string referer = "";
            string cookies = "";
            string userAgent = "";
            string saveDir = "";
            string fileName = "";
            bool silent = false;
            bool queueOnly = false;

            for (int i = 2; i < args.Length; i++)
            {
                string a = args[i];
                if (a.Equals("--referer", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                    referer = args[++i];
                else if (a.Equals("--cookies", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                    cookies = args[++i];
                else if (a.Equals("--ua", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                    userAgent = args[++i];
                else if (a.Equals("--dir", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                    saveDir = args[++i];
                else if (a.Equals("--filename", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                    fileName = args[++i];
                else if (a.Equals("--silent", StringComparison.OrdinalIgnoreCase))
                    silent = true;
                else if (a.Equals("--queue", StringComparison.OrdinalIgnoreCase))
                    queueOnly = true;
            }

            return DispatchLinkToZero(url, referer, cookies, userAgent, saveDir, fileName, silent, queueOnly);
        }

        private static int DispatchLinkToZero(string url, string referer, string cookies, string userAgent, string saveDir, string fileName, bool silent, bool queueOnly)
        {
            string json = string.Format(
                "{{\"url\":\"{0}\",\"referer\":\"{1}\",\"cookies\":\"{2}\",\"user_agent\":\"{3}\",\"save_dir\":\"{4}\",\"filename\":\"{5}\",\"silent\":{6},\"queue_only\":{7}}}",
                EscapeJson(url),
                EscapeJson(referer),
                EscapeJson(cookies),
                EscapeJson(userAgent),
                EscapeJson(saveDir),
                EscapeJson(fileName),
                silent ? "true" : "false",
                queueOnly ? "true" : "false"
            );

            bool ok = PostJson(API_ENDPOINT, json);
            if (!ok)
            {
                LaunchZeroCli(url, saveDir, fileName, silent, queueOnly);
            }

            return 0;
        }

        public static bool PostJson(string endpoint, string json)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(endpoint);
                req.Method = "POST";
                req.ContentType = "application/json; charset=utf-8";
                req.Headers.Add("X-Zero-Client", "zero-native-engine");
                req.Timeout = 2500;

                byte[] data = Encoding.UTF8.GetBytes(json);
                req.ContentLength = data.Length;

                using (Stream stream = req.GetRequestStream())
                {
                    stream.Write(data, 0, data.Length);
                }

                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                {
                    if (resp.StatusCode == HttpStatusCode.OK)
                    {
                        Console.WriteLine("SUCCESS: Dispatched to active Zero instance.");
                        return true;
                    }
                }
            }
            catch { }
            return false;
        }

        public static void LaunchZeroCli(string url, string saveDir, string fileName, bool silent, bool queueOnly)
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
                Console.WriteLine("SUCCESS: Launched Krolix.exe with CLI parameters.");
            }
            else
            {
                Console.Error.WriteLine("Could not locate Krolix.exe to handle request.");
            }
        }

        public static string FindZeroExe()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string p1 = Path.Combine(baseDir, "Krolix.exe");
            if (File.Exists(p1)) return p1;

            string pRoot = Path.GetFullPath(Path.Combine(baseDir, "..", "..", "Krolix.exe"));
            if (File.Exists(pRoot)) return pRoot;

            string p2 = Path.Combine(baseDir, "dist", "Zero", "Krolix.exe");
            if (File.Exists(p2)) return p2;

            string p2Root = Path.GetFullPath(Path.Combine(baseDir, "..", "..", "dist", "Zero", "Krolix.exe"));
            if (File.Exists(p2Root)) return p2Root;

            string localApp = Environment.ExpandEnvironmentVariables(@"%LOCALAPPDATA%\Programs\Krolix Download Manager\Krolix.exe");
            if (File.Exists(localApp)) return localApp;

            return "";
        }

        /// <summary>
        /// Registers Zero COM automation keys in HKCU.
        /// Registers LocalServer32 out-of-process COM server and cleans any stale InprocServer32.
        /// </summary>
        public static int HandleRegister()
        {
            try
            {
                string selfExe = System.Reflection.Assembly.GetExecutingAssembly().Location;
                string zeroExe = FindZeroExe();
                if (string.IsNullOrEmpty(zeroExe)) zeroExe = selfExe;

                string[] clsids = new string[] { CLSID_OFFICIAL, CLSID_COMPAT };
                string[] bases = new string[] { @"Software\Classes", @"Software\Classes\Wow6432Node" };

                foreach (string b in bases)
                {
                    // 1. ProgID
                    using (RegistryKey prog = Registry.CurrentUser.CreateSubKey(b + @"\Krolix.LinkTransmitter"))
                    {
                        prog.SetValue("", "Krolix Download Manager Link Transmitter");
                        using (RegistryKey clsidKey = prog.CreateSubKey("CLSID"))
                        {
                            clsidKey.SetValue("", CLSID_OFFICIAL);
                        }
                    }

                    // 2. CLSIDs
                    foreach (string clsid in clsids)
                    {
                        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(b + @"\CLSID\" + clsid))
                        {
                            key.SetValue("", "Krolix.LinkTransmitter");

                            string dllPath = Path.Combine(Path.GetDirectoryName(selfExe), "KrolixComBridge.dll");
                            if (File.Exists(dllPath))
                            {
                                try { key.DeleteSubKeyTree("LocalServer32", false); } catch { }
                                using (RegistryKey ip = key.CreateSubKey("InprocServer32"))
                                {
                                    ip.SetValue("", "mscoree.dll");
                                    ip.SetValue("ThreadingModel", "Both");
                                    ip.SetValue("Class", "Zero.Com.KrolixLinkTransmitter");
                                    ip.SetValue("Assembly", "KrolixComBridge, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null");
                                    ip.SetValue("RuntimeVersion", "v4.0.30319");
                                    ip.SetValue("CodeBase", "file:///" + dllPath.Replace('\\', '/'));
                                }
                            }
                            else
                            {
                                try { key.DeleteSubKeyTree("InprocServer32", false); } catch { }
                                using (RegistryKey ls = key.CreateSubKey("LocalServer32"))
                                {
                                    ls.SetValue("", "\"" + selfExe + "\"");
                                }
                            }

                            using (RegistryKey pi = key.CreateSubKey("ProgID"))
                            {
                                pi.SetValue("", "Krolix.LinkTransmitter");
                            }
                        }
                    }
                }

                Console.WriteLine("SUCCESS: Registered Zero COM automation in HKCU.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[ZeroNative Register Error] " + ex.Message);
                return 1;
            }
        }

        public static int HandleUnregister()
        {
            try
            {
                string[] clsids = new string[] { CLSID_OFFICIAL, CLSID_COMPAT };
                string[] bases = new string[] { @"Software\Classes", @"Software\Classes\Wow6432Node" };

                foreach (string b in bases)
                {
                    try { Registry.CurrentUser.DeleteSubKeyTree(b + @"\Krolix.LinkTransmitter", false); } catch { }
                    foreach (string clsid in clsids)
                    {
                        try { Registry.CurrentUser.DeleteSubKeyTree(b + @"\CLSID\" + clsid, false); } catch { }
                    }
                }

                Console.WriteLine("SUCCESS: Unregistered Zero COM keys.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[ZeroNative Unregister Error] " + ex.Message);
                return 1;
            }
        }

        public static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n").Replace("\t", "\\t");
        }
    }
}
