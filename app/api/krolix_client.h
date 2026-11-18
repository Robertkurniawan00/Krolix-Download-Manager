/**
 * Krolix Download Manager - C/C++ Header-Only Client & COM Integration
 * 
 * Single-header library for integrating Krolix Download Manager into C/C++ Windows applications.
 * Supports:
 * - Direct COM Automation (IKrolixLinkTransmitter / KrolixLinkTransmitter)
 * - Lightweight WinINet HTTP REST client (port 9666)
 * - Automatic CLI process spawning fallback
 * 
 * Usage:
 *   #define KROLIX_CLIENT_IMPLEMENTATION
 *   #include "krolix_client.h"
 * 
 *   int main() {
 *       KrolixClient_Init();
 *       KrolixClient_Download("https://example.com/file.zip", "C:\\Downloads", "file.zip", KROLIX_FLAG_SILENT);
 *       KrolixClient_Cleanup();
 *       return 0;
 *   }
 */

#ifndef KROLIX_CLIENT_H
#define KROLIX_CLIENT_H

#include <windows.h>
#include <ole2.h>
#include <wininet.h>
#include <stdio.h>
#include <stdlib.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "wininet.lib")

#define KROLIX_FLAG_NORMAL      0x0
#define KROLIX_FLAG_SILENT      0x1
#define KROLIX_FLAG_QUEUE_ONLY  0x2

#ifdef __cplusplus
extern "C" {
#endif

// Krolix COM GUIDs
static const GUID CLSID_Krolix_LinkTransmitter = 
    { 0xAC746233, 0xE9D3, 0x49CD, { 0x86, 0x2F, 0x06, 0x8F, 0x7B, 0x7C, 0xCC, 0xA4 } };

static const GUID IID_Krolix_ILinkTransmitter = 
    { 0x94D09862, 0x1875, 0x4FC9, { 0xB4, 0x34, 0x91, 0xCF, 0x25, 0xC8, 0x40, 0xA1 } };

// Forward declarations
BOOL KrolixClient_Init(void);
void KrolixClient_Cleanup(void);
BOOL KrolixClient_Download(const char* url, const char* path, const char* filename, DWORD flags);
BOOL KrolixClient_IsRunning(void);

#ifdef KROLIX_CLIENT_IMPLEMENTATION

static BOOL g_KrolixOleInitialized = FALSE;

BOOL KrolixClient_Init(void) {
    HRESULT hr = OleInitialize(NULL);
    if (SUCCEEDED(hr)) {
        g_KrolixOleInitialized = TRUE;
        return TRUE;
    }
    return FALSE;
}

void KrolixClient_Cleanup(void) {
    if (g_KrolixOleInitialized) {
        OleUninitialize();
        g_KrolixOleInitialized = FALSE;
    }
}

BOOL KrolixClient_Download(const char* url, const char* path, const char* filename, DWORD flags) {
    if (!url || strlen(url) == 0) return FALSE;

    // 1. Try COM Automation
    CLSID clsid;
    HRESULT hr = CLSIDFromProgID(L"Krolix.LinkTransmitter", &clsid);
    if (FAILED(hr)) {
        hr = CLSIDFromProgID(L"Zero.LinkTransmitter", &clsid);
    }

    if (SUCCEEDED(hr)) {
        IDispatch* pDisp = NULL;
        hr = CoCreateInstance(&clsid, NULL, CLSCTX_LOCAL_SERVER, IID_IDispatch, (void**)&pDisp);
        if (SUCCEEDED(hr) && pDisp) {
            OLECHAR* szMember = L"SendLink2";
            DISPID dispid;
            hr = pDisp->lpVtbl->GetIDsOfNames(pDisp, &IID_NULL, &szMember, 1, LOCALE_USER_DEFAULT, &dispid);
            if (SUCCEEDED(hr)) {
                // Prepare BSTR arguments
                int wlen = MultiByteToWideChar(CP_UTF8, 0, url, -1, NULL, 0);
                BSTR bstrUrl = SysAllocStringLen(NULL, wlen);
                MultiByteToWideChar(CP_UTF8, 0, url, -1, bstrUrl, wlen);

                BSTR bstrPath = SysAllocString(L"");
                if (path && strlen(path) > 0) {
                    int plen = MultiByteToWideChar(CP_UTF8, 0, path, -1, NULL, 0);
                    SysReAllocStringLen(&bstrPath, NULL, plen);
                    MultiByteToWideChar(CP_UTF8, 0, path, -1, bstrPath, plen);
                }

                BSTR bstrFile = SysAllocString(L"");
                if (filename && strlen(filename) > 0) {
                    int flen = MultiByteToWideChar(CP_UTF8, 0, filename, -1, NULL, 0);
                    SysReAllocStringLen(&bstrFile, NULL, flen);
                    MultiByteToWideChar(CP_UTF8, 0, filename, -1, bstrFile, flen);
                }

                BSTR bstrEmpty = SysAllocString(L"");

                // Parameters in reverse order for DISPPARAMS (11 params)
                VARIANTARG vargs[11];
                for (int i = 0; i < 11; i++) VariantInit(&vargs[i]);

                vargs[10].vt = VT_BSTR; vargs[10].bstrVal = bstrUrl;
                vargs[9].vt = VT_BSTR;  vargs[9].bstrVal = bstrEmpty;
                vargs[8].vt = VT_BSTR;  vargs[8].bstrVal = bstrEmpty;
                vargs[7].vt = VT_BSTR;  vargs[7].bstrVal = bstrEmpty;
                vargs[6].vt = VT_BSTR;  vargs[6].bstrVal = bstrEmpty;
                vargs[5].vt = VT_BSTR;  vargs[5].bstrVal = bstrEmpty;
                vargs[4].vt = VT_BSTR;  vargs[4].bstrVal = bstrPath;
                vargs[3].vt = VT_BSTR;  vargs[3].bstrVal = bstrFile;
                vargs[2].vt = VT_I4;    vargs[2].lVal = (LONG)flags;
                vargs[1].vt = VT_BSTR;  vargs[1].bstrVal = bstrEmpty;
                vargs[0].vt = VT_NULL;

                DISPPARAMS dp = { vargs, NULL, 11, 0 };
                VARIANT vResult;
                VariantInit(&vResult);

                hr = pDisp->lpVtbl->Invoke(pDisp, dispid, &IID_NULL, LOCALE_USER_DEFAULT, DISPATCH_METHOD, &dp, &vResult, NULL, NULL);

                SysFreeString(bstrUrl);
                SysFreeString(bstrPath);
                SysFreeString(bstrFile);
                SysFreeString(bstrEmpty);
                pDisp->lpVtbl->Release(pDisp);

                if (SUCCEEDED(hr)) return TRUE;
            } else {
                pDisp->lpVtbl->Release(pDisp);
            }
        }
    }

    // 2. Try HTTP REST (Port 9666)
    HINTERNET hOpen = InternetOpenA("KrolixClient-C", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (hOpen) {
        HINTERNET hConnect = InternetConnectA(hOpen, "127.0.0.1", 9666, NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
        if (hConnect) {
            HINTERNET hReq = HttpOpenRequestA(hConnect, "POST", "/download", NULL, NULL, NULL, INTERNET_FLAG_NO_CACHE_WRITE, 0);
            if (hReq) {
                char payload[2048];
                snprintf(payload, sizeof(payload),
                    "{\"url\":\"%s\",\"save_dir\":\"%s\",\"filename\":\"%s\",\"silent\":%s,\"queue_only\":%s}",
                    url, path ? path : "", filename ? filename : "",
                    (flags & KROLIX_FLAG_SILENT) ? "true" : "false",
                    (flags & KROLIX_FLAG_QUEUE_ONLY) ? "true" : "false"
                );

                const char* headers = "Content-Type: application/json; charset=utf-8\r\nX-Krolix-Client: c-header\r\n";
                BOOL bSent = HttpSendRequestA(hReq, headers, (DWORD)strlen(headers), payload, (DWORD)strlen(payload));
                InternetCloseHandle(hReq);
                InternetCloseHandle(hConnect);
                InternetCloseHandle(hOpen);
                if (bSent) return TRUE;
            } else {
                InternetCloseHandle(hConnect);
            }
        }
        InternetCloseHandle(hOpen);
    }

    // 3. Fallback: Launch CLI process
    char cmdLine[2048];
    snprintf(cmdLine, sizeof(cmdLine), "Krolix.exe /d \"%s\"", url);
    if (path && strlen(path) > 0) {
        snprintf(cmdLine + strlen(cmdLine), sizeof(cmdLine) - strlen(cmdLine), " /p \"%s\"", path);
    }
    if (filename && strlen(filename) > 0) {
        snprintf(cmdLine + strlen(cmdLine), sizeof(cmdLine) - strlen(cmdLine), " /f \"%s\"", filename);
    }
    if (flags & KROLIX_FLAG_SILENT) {
        snprintf(cmdLine + strlen(cmdLine), sizeof(cmdLine) - strlen(cmdLine), " /n");
    }
    if (flags & KROLIX_FLAG_QUEUE_ONLY) {
        snprintf(cmdLine + strlen(cmdLine), sizeof(cmdLine) - strlen(cmdLine), " /a");
    }

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(NULL, cmdLine, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return TRUE;
    }

    return FALSE;
}

#endif // KROLIX_CLIENT_IMPLEMENTATION

#ifdef __cplusplus
}
#endif

#endif // KROLIX_CLIENT_H
