/**
 * Zero Download Assistant - C/C++ Header-Only Client & COM Integration
 * 
 * Single-header library for integrating Zero Download Assistant into C/C++ Windows applications.
 * Supports:
 * - Direct COM Automation (IZeroLinkTransmitter2 / ZeroLinkTransmitter)
 * - Lightweight WinINet HTTP REST client (port 9666)
 * - Automatic CLI process spawning fallback
 * 
 * Usage:
 *   #define ZERO_CLIENT_IMPLEMENTATION
 *   #include "zero_client.h"
 * 
 *   int main() {
 *       ZeroClient_Init();
 *       ZeroClient_Download("https://example.com/file.zip", "C:\\Downloads", "file.zip", ZERO_FLAG_SILENT);
 *       ZeroClient_Cleanup();
 *       return 0;
 *   }
 */

#ifndef ZERO_CLIENT_H
#define ZERO_CLIENT_H

#include <windows.h>
#include <ole2.h>
#include <wininet.h>
#include <stdio.h>
#include <stdlib.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "wininet.lib")

#define ZERO_FLAG_NORMAL      0x0
#define ZERO_FLAG_SILENT      0x1
#define ZERO_FLAG_QUEUE_ONLY  0x2

#ifdef __cplusplus
extern "C" {
#endif

// Zero COM GUIDs
static const GUID IID_Zero_ILinkTransmitter = 
    { 0x4BD46AAE, 0xC51F, 0x4BF7, { 0x8B, 0xC0, 0x2E, 0x86, 0xE3, 0x3D, 0x18, 0x73 } };

static const GUID IID_Zero_ILinkTransmitter2 = 
    { 0x94D09862, 0x1875, 0x4FC9, { 0xB4, 0x34, 0x91, 0xCF, 0x25, 0xC8, 0x40, 0xA1 } };

static const GUID CLSID_Zero_LinkTransmitter = 
    { 0xAC746233, 0xE9D3, 0x49CD, { 0x86, 0x2F, 0x06, 0x8F, 0x7B, 0x7C, 0xCC, 0xA4 } };

// Forward declarations
BOOL ZeroClient_Init(void);
void ZeroClient_Cleanup(void);
BOOL ZeroClient_Download(const wchar_t* url, const wchar_t* localPath, const wchar_t* localFileName, DWORD flags);
BOOL ZeroClient_DownloadEx(const wchar_t* url, const wchar_t* referer, const wchar_t* cookies, 
                          const wchar_t* localPath, const wchar_t* localFileName, DWORD flags, const wchar_t* userAgent);

#ifdef ZERO_CLIENT_IMPLEMENTATION

static BOOL g_ZeroComInitialized = FALSE;

BOOL ZeroClient_Init(void) {
    HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (SUCCEEDED(hr)) {
        g_ZeroComInitialized = TRUE;
        return TRUE;
    }
    return FALSE;
}

void ZeroClient_Cleanup(void) {
    if (g_ZeroComInitialized) {
        CoUninitialize();
        g_ZeroComInitialized = FALSE;
    }
}

/**
 * Sends a download link via official COM Automation.
 */
static BOOL ZeroClient_SendViaCom(const wchar_t* url, const wchar_t* referer, const wchar_t* cookies,
                                 const wchar_t* localPath, const wchar_t* localFileName, DWORD flags, const wchar_t* userAgent) {
    CLSID clsid;
    HRESULT hr = CLSIDFromProgID(L"Zero.LinkTransmitter", &clsid);
    if (FAILED(hr)) {
        clsid = CLSID_Zero_LinkTransmitter;
    }

    IDispatch* pDisp = NULL;
    hr = CoCreateInstance(&clsid, NULL, CLSCTX_INPROC_SERVER | CLSCTX_LOCAL_SERVER, &IID_IDispatch, (void**)&pDisp);
    if (FAILED(hr) || !pDisp) {
        return FALSE;
    }

    DISPID dispid;
    OLECHAR* methodName = (OLECHAR*)L"SendLink2";
    hr = pDisp->lpVtbl->GetIDsOfNames(pDisp, &IID_NULL, &methodName, 1, LOCALE_USER_DEFAULT, &dispid);

    if (SUCCEEDED(hr)) {
        VARIANTARG rgvarg[11];
        // Note: DISPPARAMS args are passed in reverse order (10 to 0)
        VariantInit(&rgvarg[0]); // reserved2
        rgvarg[0].vt = VT_EMPTY;

        VariantInit(&rgvarg[1]); // reserved1 (User-Agent)
        if (userAgent && wcslen(userAgent) > 0) {
            rgvarg[1].vt = VT_BSTR;
            rgvarg[1].bstrVal = SysAllocString(userAgent);
        } else {
            rgvarg[1].vt = VT_EMPTY;
        }

        VariantInit(&rgvarg[2]); // lFlags
        rgvarg[2].vt = VT_I4;
        rgvarg[2].lVal = (LONG)flags;

        VariantInit(&rgvarg[3]); // bstrLocalFileName
        rgvarg[3].vt = VT_BSTR;
        rgvarg[3].bstrVal = SysAllocString(localFileName ? localFileName : L"");

        VariantInit(&rgvarg[4]); // bstrLocalPath
        rgvarg[4].vt = VT_BSTR;
        rgvarg[4].bstrVal = SysAllocString(localPath ? localPath : L"");

        VariantInit(&rgvarg[5]); // bstrPassword
        rgvarg[5].vt = VT_BSTR;
        rgvarg[5].bstrVal = SysAllocString(L"");

        VariantInit(&rgvarg[6]); // bstrUser
        rgvarg[6].vt = VT_BSTR;
        rgvarg[6].bstrVal = SysAllocString(L"");

        VariantInit(&rgvarg[7]); // bstrData
        rgvarg[7].vt = VT_BSTR;
        rgvarg[7].bstrVal = SysAllocString(L"");

        VariantInit(&rgvarg[8]); // bstrCookies
        rgvarg[8].vt = VT_BSTR;
        rgvarg[8].bstrVal = SysAllocString(cookies ? cookies : L"");

        VariantInit(&rgvarg[9]); // bstrReferer
        rgvarg[9].vt = VT_BSTR;
        rgvarg[9].bstrVal = SysAllocString(referer ? referer : L"");

        VariantInit(&rgvarg[10]); // bstrUrl
        rgvarg[10].vt = VT_BSTR;
        rgvarg[10].bstrVal = SysAllocString(url);

        DISPPARAMS dp = { rgvarg, NULL, 11, 0 };
        VARIANT result;
        VariantInit(&result);

        hr = pDisp->lpVtbl->Invoke(pDisp, dispid, &IID_NULL, LOCALE_USER_DEFAULT, DISPATCH_METHOD, &dp, &result, NULL, NULL);

        for (int i = 0; i < 11; i++) {
            VariantClear(&rgvarg[i]);
        }
    }

    pDisp->lpVtbl->Release(pDisp);
    return SUCCEEDED(hr);
}

/**
 * Dispatches download request to Zero using WinINet HTTP REST API.
 */
static BOOL ZeroClient_SendViaHttp(const wchar_t* url, const wchar_t* referer, const wchar_t* cookies,
                                  const wchar_t* localPath, const wchar_t* localFileName, DWORD flags, const wchar_t* userAgent) {
    HINTERNET hInternet = InternetOpenW(L"ZeroCClient/1.0", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet) return FALSE;

    HINTERNET hConnect = InternetConnectW(hInternet, L"127.0.0.1", 9666, NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
    if (!hConnect) {
        InternetCloseHandle(hInternet);
        return FALSE;
    }

    HINTERNET hRequest = HttpOpenRequestW(hConnect, L"POST", L"/download", NULL, NULL, NULL, 0, 0);
    if (!hRequest) {
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return FALSE;
    }

    // Convert wide strings to UTF-8 JSON payload
    char json[2048];
    char utf8Url[512] = {0};
    char utf8Path[512] = {0};
    char utf8File[256] = {0};

    WideCharToMultiByte(CP_UTF8, 0, url, -1, utf8Url, sizeof(utf8Url), NULL, NULL);
    if (localPath) WideCharToMultiByte(CP_UTF8, 0, localPath, -1, utf8Path, sizeof(utf8Path), NULL, NULL);
    if (localFileName) WideCharToMultiByte(CP_UTF8, 0, localFileName, -1, utf8File, sizeof(utf8File), NULL, NULL);

    snprintf(json, sizeof(json),
             "{\"url\":\"%s\",\"save_dir\":\"%s\",\"filename\":\"%s\",\"silent\":%s,\"queue_only\":%s}",
             utf8Url, utf8Path, utf8File,
             (flags & ZERO_FLAG_SILENT) ? "true" : "false",
             (flags & ZERO_FLAG_QUEUE_ONLY) ? "true" : "false");

    const wchar_t* headers = L"Content-Type: application/json; charset=utf-8\r\nX-Zero-Client: c-native\r\n";
    BOOL sent = HttpSendRequestW(hRequest, headers, (DWORD)wcslen(headers), json, (DWORD)strlen(json));

    InternetCloseHandle(hRequest);
    InternetCloseHandle(hConnect);
    InternetCloseHandle(hInternet);
    return sent;
}

BOOL ZeroClient_DownloadEx(const wchar_t* url, const wchar_t* referer, const wchar_t* cookies, 
                          const wchar_t* localPath, const wchar_t* localFileName, DWORD flags, const wchar_t* userAgent) {
    if (!url || wcslen(url) == 0) return FALSE;

    // 1. Try COM
    if (ZeroClient_SendViaCom(url, referer, cookies, localPath, localFileName, flags, userAgent)) {
        return TRUE;
    }

    // 2. Try HTTP REST
    if (ZeroClient_SendViaHttp(url, referer, cookies, localPath, localFileName, flags, userAgent)) {
        return TRUE;
    }

    // 3. Fallback: Launch Zero.exe CLI
    wchar_t cmdLine[1024];
    swprintf(cmdLine, 1024, L"Zero.exe /d \"%s\"%s%s%s%s",
             url,
             (localPath && wcslen(localPath) > 0) ? L" /p " : L"",
             (localPath && wcslen(localPath) > 0) ? localPath : L"",
             (flags & ZERO_FLAG_SILENT) ? L" /n" : L"",
             (flags & ZERO_FLAG_QUEUE_ONLY) ? L" /a" : L"");

    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    if (CreateProcessW(NULL, cmdLine, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return TRUE;
    }

    return FALSE;
}

BOOL ZeroClient_Download(const wchar_t* url, const wchar_t* localPath, const wchar_t* localFileName, DWORD flags) {
    return ZeroClient_DownloadEx(url, NULL, NULL, localPath, localFileName, flags, NULL);
}

#endif // ZERO_CLIENT_IMPLEMENTATION

#ifdef __cplusplus
}
#endif

#endif // ZERO_CLIENT_H
