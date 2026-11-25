const ZERO_API = "http://127.0.0.1:9666/download";
const ZERO_BATCH_API = "http://127.0.0.1:9666/batch-download";

// Create context menu items on startup, install, and service worker boot
function setupContextMenus() {
  if (typeof chrome === "undefined" || !chrome.contextMenus) return;
  try {
    chrome.contextMenus.removeAll(() => {
      chrome.contextMenus.create({
        id: "zero_download_link",
        title: "Download with Krolix",
        contexts: ["link", "video", "audio", "image"]
      }, () => { if (chrome.runtime?.lastError) {} });

      chrome.contextMenus.create({
        id: "zero_download_all",
        title: "Download all links on page with Krolix",
        contexts: ["page"]
      }, () => { if (chrome.runtime?.lastError) {} });

      chrome.contextMenus.create({
        id: "zero_download_selected",
        title: "Download selected link(s) with Krolix",
        contexts: ["selection"]
      }, () => { if (chrome.runtime?.lastError) {} });
    });
  } catch (err) {
    console.warn("[Krolix] Error setting up context menus:", err);
  }
}

let captureHlsEnabled = true;
try {
  chrome.storage?.local?.get({ captureHls: true }, (res) => {
    captureHlsEnabled = res?.captureHls !== false;
  });
  chrome.storage?.onChanged?.addListener((changes, area) => {
    if (area === "local" && changes.captureHls) {
      captureHlsEnabled = changes.captureHls.newValue !== false;
    }
  });
} catch (e) {}

chrome.runtime.onInstalled.addListener(setupContextMenus);
chrome.runtime.onStartup.addListener(setupContextMenus);

function sendBatchToZero(payload) {
  fetch(ZERO_BATCH_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  }).catch(err => {
    console.error("[Krolix Extension] Failed to send batch download:", err);
  });
}

// Context menu click handler
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "zero_download_all") {
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_PAGE_LINKS" }, (response) => {
        if (chrome.runtime.lastError || !response || !response.items || response.items.length === 0) {
          sendToZero({
            url: tab.url,
            referer: tab.url,
            open_grabber: true,
            force: true
          });
          return;
        }
        sendBatchToZero({
          referer: tab.url,
          items: response.items
        });
      });
    }
    return;
  }

  if (info.menuItemId === "zero_download_selected") {
    const sel = (info.selectionText || "").trim();
    if (sel) {
      const urlRegex = /(https?:\/\/[^\s"'<>]+|magnet:\?[^\s"'<>]+)/gi;
      const matches = sel.match(urlRegex) || [];
      if (matches.length > 1) {
        sendBatchToZero({
          referer: tab ? tab.url : "",
          items: matches.map(u => ({ url: u, description: "", cookies: "" }))
        });
        return;
      } else if (matches.length === 1) {
        sendToZero({
          url: matches[0],
          filename: "",
          referer: tab ? tab.url : "",
          force: true
        });
        return;
      }
    }
  }

  let targetUrl = info.linkUrl || info.srcUrl;
  if (!targetUrl && info.selectionText) {
    const s = info.selectionText.trim();
    if (s.startsWith("http://") || s.startsWith("https://") || s.startsWith("magnet:")) {
      targetUrl = s;
    }
  }
  if (!targetUrl) {
    targetUrl = info.pageUrl;
  }

  if (targetUrl) {
    const isMediaContext = info.mediaType === "video" || info.mediaType === "audio";
    sendToZero({
      url: targetUrl,
      filename: "",
      referer: tab ? tab.url : "",
      is_media: isMediaContext,
      force: true
    });
  }
});

// Helper to identify synthetic, extension-internal, and stream-saver downloads that must NOT be intercepted
function shouldIgnoreDownload(downloadItem) {
  if (!downloadItem || !downloadItem.url) return true;

  const url = (downloadItem.url || "").toLowerCase();
  const finalUrl = (downloadItem.finalUrl || "").toLowerCase();
  const referrer = (downloadItem.referrer || "").toLowerCase();

  // 1. Initiated by another browser extension (e.g. FetchV, Video DownloadHelper, SingleFile)
  // chrome.downloads.DownloadItem provides byExtensionId when another extension creates the download
  if (downloadItem.byExtensionId) {
    console.log("[Krolix] Skipping download initiated by extension:", downloadItem.byExtensionId, downloadItem.url);
    return true;
  }

  // 2. Internal browser protocols & synthetic URLs
  const virtualProtocols = [
    "blob:",
    "data:",
    "filesystem:",
    "chrome:",
    "chrome-extension:",
    "moz-extension:",
    "edge:",
    "about:",
    "javascript:"
  ];
  if (virtualProtocols.some((p) => url.startsWith(p) || finalUrl.startsWith(p))) {
    return true;
  }

  // 3. StreamSaver.js and browser-internal caching services
  // Extensions like FetchV cache HLS segments in browser memory/IndexedDB and flush them to disk via StreamSaver.
  // The synthetic URL (e.g. https://fetchv.net/extensions/dist/modules/streamSaver/...) is virtual and handled
  // ONLY by the browser's ServiceWorker inside Chrome. External processes attempting to connect get 404.
  const streamSaverIndicators = [
    "streamsaver",
    "stream-saver",
    "/modules/streamsaver",
    "fetchv.net",
    "fetchv",
    "videodownloadhelper",
    "singlefile"
  ];
  if (streamSaverIndicators.some((ind) => url.includes(ind) || finalUrl.includes(ind) || referrer.includes(ind))) {
    console.log("[Krolix] Skipping internal StreamSaver / extension stream download:", downloadItem.url);
    return true;
  }

  // 4. Ignore ad network media downloads
  if (isAdOrJunkMedia(downloadItem.url, downloadItem.filename || "", { initiator: downloadItem.referrer || "" })) {
    console.log("[Krolix] Skipping ad / junk media download:", downloadItem.url);
    return true;
  }

  return false;
}

// Recent intercepted download tracker to prevent duplicate interception from redirects / retries
const recentInterceptedDownloads = new Map();

function isDownloadDebounced(downloadItem) {
  if (!downloadItem) return false;
  const now = Date.now();
  // Clean up entries older than 30s
  for (const [key, timestamp] of recentInterceptedDownloads.entries()) {
    if (now - timestamp > 30000) {
      recentInterceptedDownloads.delete(key);
    }
  }

  const keys = [];
  if (downloadItem.id) keys.push(`id:${downloadItem.id}`);
  if (downloadItem.url) keys.push(`url:${downloadItem.url.toLowerCase()}`);

  for (const k of keys) {
    const last = recentInterceptedDownloads.get(k);
    if (last && (now - last < 4000)) {
      return true; // Debounced
    }
  }

  for (const k of keys) {
    recentInterceptedDownloads.set(k, now);
  }
  return false;
}

// Intercept standard browser downloads
chrome.downloads.onCreated.addListener((downloadItem) => {
  chrome.storage.local.get({ interceptEnabled: true }, (res) => {
    if (!res.interceptEnabled) return;

    if (shouldIgnoreDownload(downloadItem)) {
      return;
    }

    if (isDownloadDebounced(downloadItem)) {
      console.log("[Krolix] Skipping duplicate/debounced download interception:", downloadItem.url);
      chrome.downloads.cancel(downloadItem.id, () => {
        chrome.downloads.erase({ id: downloadItem.id });
      });
      return;
    }

    const isTorrent = (downloadItem.url || "").toLowerCase().includes(".torrent") ||
                      (downloadItem.filename || "").toLowerCase().endsWith(".torrent");

    if (isTorrent) {
      // Allow browser to natively complete the small .torrent file using active session / Cloudflare clearance.
      // Once completed, chrome.downloads.onChanged immediately forwards the completed local .torrent file to Zero.
      console.log("[Krolix] Allowing browser to complete authenticated .torrent file download:", downloadItem.url);
      return;
    }

    // Cancel browser download
    chrome.downloads.cancel(downloadItem.id, () => {
      chrome.downloads.erase({ id: downloadItem.id });
    });

    sendToZero({
      url: downloadItem.url,
      filename: downloadItem.filename,
      referer: downloadItem.referrer || "",
      is_media: false
    });
  });
});

// Listener for completed browser downloads (forward completed .torrent files to Zero)
chrome.downloads.onChanged.addListener((delta) => {
  if (delta.state && delta.state.current === "complete") {
    chrome.downloads.search({ id: delta.id }, (items) => {
      if (items && items.length > 0) {
        const item = items[0];
        if (item.filename && item.filename.toLowerCase().endsWith(".torrent")) {
          console.log("[Krolix] Authenticated .torrent download completed in browser, forwarding to Zero:", item.filename);
          sendToZero({
            url: item.filename,
            filename: item.filename,
            referer: item.referrer || "",
            is_media: false,
            force: true
          });
        }
      }
    });
  }
});

// Media request sniffer via webRequest
const DIRECT_MEDIA_EXTENSIONS = [".mp4", ".webm", ".mp3", ".m4a", ".mkv", ".flv", ".aac", ".ogg"];
const STREAM_MIMES = [
  "application/x-mpegurl",
  "application/vnd.apple.mpegurl",
  "application/dash+xml",
  "audio/x-mpegurl",
  "video/x-mpegurl"
];
const DIRECT_MEDIA_MIMES = [
  "video/mp4",
  "video/webm",
  "video/x-matroska",
  "video/quicktime",
  "audio/mpeg",
  "audio/mp4",
  "audio/aac",
  "audio/ogg"
];

// Per-tab cache of detected streams to prevent duplicate notifications
const tabStreamHistory = new Map(); // tabId -> Map(url -> mediaObject)

// 1. Blurred, thumbnail previews, teaser loops, storyboard video streams
const JUNK_PREVIEW_PATTERNS = [
  "blurred",
  "_blur",
  "-blur",
  "/blur",
  "blur.m3u8",
  "preview_blur",
  "hover_preview",
  "hover-preview",
  "hoverpreview",
  "thumb_preview",
  "thumb-preview",
  "thumbnail_preview",
  "trailer_preview",
  "short_preview",
  "preview.m3u8",
  "preview.mp4",
  "teaser.m3u8",
  "storyboard",
  "storyboard.m3u8",
  "sprite.m3u8",
  "spritesheet",
  "160p_blurred",
  "144p_blurred",
  "120p_blurred"
];

// 2. Video Advertising Networks & Ad Servers
const AD_DOMAINS_AND_SERVERS = [
  // Google & YouTube Ads
  "doubleclick.net",
  "googleads",
  "googlesyndication.com",
  "adservice.google",
  "pagead",
  "g.doubleclick",
  "video-ad-stats",
  "adwords",
  "youtube.com/api/stats/ads",
  "youtube.com/pagead",
  "youtube.com/ptracking",

  // Amazon Ads
  "amazon-adsystem.com",
  "aax.amazon-adsystem.com",
  "aax-us-east.amazon-adsystem.com",
  "advertising.amazon.com",
  "aps.amazon.com",

  // Microsoft / Xandr / AppNexus
  "adnxs.com",
  "adnxs-simple.com",
  "bingads",
  "bat.bing.com",

  // Major SSPs, DSPs, Exchanges & VAST/VPAID
  "spotx.tv",
  "spotxchange.com",
  "springserve.com",
  "teads.tv",
  "aniview.com",
  "freewheel.tv",
  "fwmrm.net",
  "tremorhub.com",
  "tremormedia.com",
  "unruly.co",
  "exponential.com",
  "innovid.com",
  "videologygroup.com",
  "brightroll.com",
  "adkernel.com",
  "adform.net",
  "smartadserver.com",
  "bidswitch.net",
  "rubiconproject.com",
  "pubmatic.com",
  "openx.net",
  "criteo.com",
  "criteo.net",
  "adroll.com",
  "casalemedia.com",
  "indexww.com",
  "contextweb.com",
  "pulsepoint.com",
  "yieldmo.com",
  "sharethrough.com",
  "triplelift.com",
  "nativo.com",
  "kargo.com",
  "sovrn.com",
  "adtech.de",
  "adtechus.com",
  "conversantmedia.com",

  // Mobile / In-App Video Ad SDKs
  "applovin.com",
  "unityads",
  "vungle.com",
  "inmobi.com",
  "chartboost.com",
  "ironsource.com",
  "fyber.com",
  "mintegral.com",
  "liftoff.io",
  "pangleglobal.com",
  "tapjoy.com",
  "adcolony.com",

  // Native & Recommendation Video Ads
  "outbrain.com",
  "taboola.com",
  "mgid.com",
  "revcontent.com",
  "content-ad.net",
  "zemanta.com",
  "zergnet.com",

  // Video Ad & Pop Ad Networks (Common on free streaming & adult media sites)
  "trafficjunky.com",
  "trafficjunky.net",
  "trafficfactory.biz",
  "exoclick.com",
  "exosrv.com",
  "exdynsrv.com",
  "adsterra.com",
  "adsterracdn.com",
  "adsterratech.com",
  "popads.net",
  "popcash.net",
  "juicyads.com",
  "ero-advertising.com",
  "hubtraffic.com",
  "ht-ads.com",
  "stripchat-ads",
  "chaturbate-ads",
  "plugrush.com",
  "clickadu.com",
  "propellerads.com",
  "propellerclick.com",
  "adcash.com",
  "hilltopads.net",
  "evadav.com",
  "monetag.com",
  "clickaine.com",
  "rollerads.com",
  "bidgear.com",
  "coinhive.com",

  // Live Cam Affiliate Widgets & Ad Streams (DoppioCDN / Stripchat / BongaCams / Chaturbate / tsyndicate)
  "doppiocdn.com",
  "doppiocdn.net",
  "doppiocdn.org",
  "doppiocdn.live",
  "edge-hls.doppiocdn",
  "b-hls-",
  "strpst.com",
  "xlivrdr.com",
  "tsyndicate.com",
  "realsrv.com",
  "bcrncdn.com",
  "mmcdn.com",
  "cbjpeg.com",
  "dditscdn.com",
  "wmcdns.com",
  "sacdnssedge.com",
  "livejasmin.com",
  "bongacams.com",
  "xhamsterlive.com",
  "myfreecams.com",
  "cam4.com",
  "cambaddies.com",
  "jerkmate.com",
  "flirt4free.com",
  "imlive.com",
  "streamate.com",
  "chaturbate.com/affiliates",
  "chaturbate.com/in/",
  "stripchat.com/checkUrl",

  // Verification & Measurement
  "moatads.com",
  "doubleverify.com",
  "scorecardresearch.com",
  "iasds01.com",
  "integralads.com",
  "meetrics.net",
  "adloox.com"
];

// 3. Ad URL & Query regex
const AD_URL_REGEX = /(?:^|[/?&_#.-])(?:vast|vpaid|ima3|imasdk|interactive-media-ads|preroll|midroll|postroll|popunder|interstitial|ad_unit|adunit|ad_banner|ad_video|ad-video|advideo|ad_stream|adstream|ad_system|ad_tag|adtag|video-ad|video_ad|videoad|videoads|advert|advertisement|sponsored|promo_video|promoted|commercial|adformat|ad_format|ad_cpn|ad_type|adurl|ad_network|ad_client|ad_slot|ad_channel|ad_companion|ad_provider)(?:[/?&=_#.-]|$)/i;
const AD_PATH_REGEX = /\/(?:ads|ad|advert|advertising|banners?|commercials?|promos?|sponsors?)\/(?:video|stream|vast|vpaid|m3u8|mp4|hls|dash|delivery)/i;
const AD_QUERY_PARAM_REGEX = /[?&](?:adformat|ad_format|ad_type|ad_tag|adtag|ad_id|adurl|ad_network|ad_client|ad_slot|ad_channel|ad_companion|ad_provider|ad_cpn|is_ad|isad|ctas|gvi)=/i;
// Live-cam widget stream pattern (e.g. 480p.m3u8_270084900, 240p.m3u8_223164248, auto.m3u8_223164248)
const LIVE_CAM_WIDGET_REGEX = /(?:\b(?:auto|\d{3,4}p)\.m3u8_\d{5,15}|\.m3u8_\d{6,15}(?:$|[?&])|\/hls\/\d{6,12}\/(?:master\/)?\d{6,12}(?:_auto|_\d{3,4}p)?\.m3u8)/i;

function isAdOrJunkMedia(url, name, payload) {
  if (!url) return false;
  const u = (url || "").toLowerCase();
  const n = (name || "").toLowerCase();
  const full = u + " " + n;

  // 0. Live-cam affiliate widget streams (e.g. 480p.m3u8_270084900, auto.m3u8_223164248)
  if (LIVE_CAM_WIDGET_REGEX.test(u) || LIVE_CAM_WIDGET_REGEX.test(n) || LIVE_CAM_WIDGET_REGEX.test(full)) {
    return true;
  }

  // 1. Blurred, thumbnail previews, teaser loops, storyboard video streams
  if (JUNK_PREVIEW_PATTERNS.some((p) => full.includes(p))) {
    return true;
  }

  // 2. Video Advertising Networks & Ad Servers (URL or initiator domain)
  const initiator = (payload && payload.initiator) ? (payload.initiator || "").toLowerCase() : "";
  if (AD_DOMAINS_AND_SERVERS.some((ad) => u.includes(ad) || initiator.includes(ad))) {
    return true;
  }

  // 3. Ad keywords & protocols in URL paths or filenames or query params
  if (AD_URL_REGEX.test(u) || AD_URL_REGEX.test(n) || AD_PATH_REGEX.test(u) || AD_QUERY_PARAM_REGEX.test(u)) {
    return true;
  }

  // 4. Low resolution preview filters: <= 180p with blur or preview
  if (payload) {
    const h = payload.height || 0;
    const dur = payload.duration || 0;
    if (h > 0 && h <= 180 && (full.includes("blur") || full.includes("preview") || (dur > 0 && dur < 30))) {
      return true;
    }
  }

  return false;
}

const capturedM3u8Content = new Map();

async function recordStream(tabId, mediaPayload) {
  if (tabId < 0 || !mediaPayload || !mediaPayload.url) return;
  if (!captureHlsEnabled && (mediaPayload.is_hls || mediaPayload.is_dash)) {
    return;
  }
  if (isAdOrJunkMedia(mediaPayload.url, mediaPayload.name, mediaPayload)) {
    return; // Block advertising and blurred preview media streams
  }
  if (mediaPayload.m3u8Content && mediaPayload.m3u8Content.includes("#EXTM3U")) {
    capturedM3u8Content.set(mediaPayload.url, mediaPayload.m3u8Content);
    const cleanU = (mediaPayload.url || "").split("?")[0].split("#")[0];
    capturedM3u8Content.set(cleanU, mediaPayload.m3u8Content);
  }
  if (!tabStreamHistory.has(tabId)) {
    tabStreamHistory.set(tabId, new Map());
  }
  const tabHistory = tabStreamHistory.get(tabId);
  if (tabHistory.has(mediaPayload.url)) {
    const existing = tabHistory.get(mediaPayload.url);
    if ((mediaPayload.size || 0) > (existing.size || 0)) existing.size = mediaPayload.size;
    if ((mediaPayload.filesize || 0) > (existing.filesize || 0)) existing.filesize = mediaPayload.filesize;
    if ((mediaPayload.height || 0) > (existing.height || 0)) existing.height = mediaPayload.height;
    if ((mediaPayload.width || 0) > (existing.width || 0)) existing.width = mediaPayload.width;
    if ((mediaPayload.bitrate || 0) > (existing.bitrate || 0)) existing.bitrate = mediaPayload.bitrate;
    if ((mediaPayload.bandwidth || 0) > (existing.bandwidth || 0)) existing.bandwidth = mediaPayload.bandwidth;
    if (mediaPayload.resolution) existing.resolution = mediaPayload.resolution;
    if (mediaPayload.display_name) existing.display_name = mediaPayload.display_name;
    if (mediaPayload.m3u8Content) existing.m3u8Content = mediaPayload.m3u8Content;
    tabHistory.set(mediaPayload.url, existing);
    try {
      if (chrome.storage && chrome.storage.session) {
        const storageKey = `tab_streams_${tabId}`;
        chrome.storage.session.set({ [storageKey]: Array.from(tabHistory.values()) });
      }
    } catch (e) {}
    return;
  }

  // Attach any captured request headers (FetchV methodology)
  const cleanUrl = (mediaPayload.url || "").split("?")[0].split("#")[0];
  const cachedHeaders = capturedStreamHeaders.get(mediaPayload.url) || capturedStreamHeaders.get(cleanUrl) || {};
  mediaPayload.requestHeaders = Object.assign({}, cachedHeaders, mediaPayload.requestHeaders || {});

  tabHistory.set(mediaPayload.url, mediaPayload);

  // Persist to session storage so service worker restarts don't lose captured streams
  try {
    if (chrome.storage && chrome.storage.session) {
      const storageKey = `tab_streams_${tabId}`;
      const streamsArr = Array.from(tabHistory.values());
      chrome.storage.session.set({ [storageKey]: streamsArr });
    }
  } catch (e) {}

  // Update extension badge with detected video count (Zero Video Sniffer)
  const count = tabHistory.size;
  if (count > 0 && chrome.action?.setBadgeText) {
    try {
      const p1 = chrome.action.setBadgeText({ tabId: tabId, text: String(count) });
      if (p1 && typeof p1.catch === "function") p1.catch(() => {});
      const p2 = chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: "#10b981" });
      if (p2 && typeof p2.catch === "function") p2.catch(() => {});
    } catch (e) {}
  }

  // Send to content scripts across frames
  try {
    const p3 = chrome.tabs.sendMessage(tabId, {
      action: "MEDIA_SNIFFED",
      media: mediaPayload
    });
    if (p3 && typeof p3.catch === "function") p3.catch(() => {});
  } catch (e) {}
}

chrome.tabs.onRemoved.addListener((tabId) => {
  tabStreamHistory.delete(tabId);
  try {
    if (chrome.storage?.session) {
      const p = chrome.storage.session.remove(`tab_streams_${tabId}`);
      if (p && typeof p.catch === "function") p.catch(() => {});
    }
  } catch (e) {}
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading" && changeInfo.url) {
    tabStreamHistory.delete(tabId);
    try {
      if (chrome.storage?.session) {
        const p1 = chrome.storage.session.remove(`tab_streams_${tabId}`);
        if (p1 && typeof p1.catch === "function") p1.catch(() => {});
      }
      if (chrome.action?.setBadgeText) {
        const p2 = chrome.action.setBadgeText({ tabId: tabId, text: "" });
        if (p2 && typeof p2.catch === "function") p2.catch(() => {});
      }
    } catch (e) {}
  }
});

// Cache to store exact HTTP request headers (Referer, Origin, Cookie, Authorization) captured from the player
const capturedStreamHeaders = new Map();

// Intercept streaming headers via onBeforeSendHeaders (FetchV methodology)
try {
  if (typeof chrome !== "undefined" && chrome?.webRequest?.onBeforeSendHeaders) {
    chrome.webRequest.onBeforeSendHeaders.addListener(
      (details) => {
        const urlLower = (details.url || "").toLowerCase();
        if (isAdOrJunkMedia(details.url, "", { initiator: details.initiator || "" })) {
          return;
        }

        const isStream = urlLower.includes(".m3u8") || urlLower.includes(".mpd") ||
                         urlLower.includes("/hls/") || urlLower.includes("playlist.m3u8");

        if (isStream || DIRECT_MEDIA_EXTENSIONS.some((e) => urlLower.includes(e))) {
          const hdrs = {};
          if (details.requestHeaders) {
            for (const h of details.requestHeaders) {
              const nameLow = h.name.toLowerCase();
              if (["referer", "origin", "user-agent", "cookie", "authorization", "accept-language"].includes(nameLow)) {
                hdrs[h.name] = h.value;
              }
            }
          }
          if (Object.keys(hdrs).length > 0) {
            capturedStreamHeaders.set(details.url, hdrs);
            const cleanUrl = details.url.split("?")[0].split("#")[0];
            capturedStreamHeaders.set(cleanUrl, hdrs);

            const tabHistory = tabStreamHistory.get(details.tabId);
            if (tabHistory && tabHistory.has(details.url)) {
              const item = tabHistory.get(details.url);
              item.requestHeaders = Object.assign(item.requestHeaders || {}, hdrs);
            }
          }
        }
      },
      { urls: ["<all_urls>"] },
      ["requestHeaders", "extraHeaders"]
    );
  }
} catch (e) {
  console.warn("[Krolix] onBeforeSendHeaders setup:", e);
}

// Intercept streaming manifests (HLS .m3u8, DASH .mpd) on before request
try {
  if (typeof chrome !== "undefined" && chrome?.webRequest?.onBeforeRequest) {
    chrome.webRequest.onBeforeRequest.addListener(
      (details) => {
        if (details.tabId < 0 || details.type === "main_frame") {
          return;
        }

        const urlLower = (details.url || "").toLowerCase();
        if (isAdOrJunkMedia(details.url, "", { initiator: details.initiator || "" })) {
          return;
        }

        const cleanPath = urlLower.split("?")[0];
        const isHls = cleanPath.endsWith(".m3u8") || urlLower.includes(".m3u8");
        const isDash = cleanPath.endsWith(".mpd") || urlLower.includes(".mpd");

        if (isHls || isDash) {
          const cleanUrl = details.url.split("?")[0].split("#")[0];
          const parts = cleanUrl.split("/");
          const rawName = parts[parts.length - 1] || (isHls ? "stream.m3u8" : "stream.mpd");
          let name = rawName;
          try { name = decodeURIComponent(rawName); } catch (e) {}
          recordStream(details.tabId, {
            url: details.url,
            name: name,
            ext: isHls ? "m3u8" : "mpd",
            mime: isHls ? "application/x-mpegurl" : "application/dash+xml",
            size: -1,
            is_hls: isHls,
            is_dash: isDash,
            is_stream: true,
            initiator: details.initiator || ""
          });
        }
      },
      { urls: ["<all_urls>"] }
    );
  }
} catch (e) {
  console.warn("[Krolix] onBeforeRequest setup:", e);
}

try {
  if (typeof chrome !== "undefined" && chrome?.webRequest?.onHeadersReceived) {
    chrome.webRequest.onHeadersReceived.addListener(
      (details) => {
        if (details.tabId < 0) {
          return;
        }

        const urlLower = (details.url || "").toLowerCase();
        if (isAdOrJunkMedia(details.url, "", { initiator: details.initiator || "" })) {
          return;
        }

        let mimeType = "";
        let contentLength = 0;

        if (details.responseHeaders) {
          for (const h of details.responseHeaders) {
            const name = h.name.toLowerCase();
            if (name === "content-type" && h.value) {
              mimeType = h.value.toLowerCase();
            } else if (name === "content-length" && h.value) {
              contentLength = parseInt(h.value, 10) || 0;
            }
          }
        }

        const cleanPath = urlLower.split("?")[0];

        // 1. Check for HLS (.m3u8) or DASH (.mpd) playlists
        const isHls = cleanPath.endsWith(".m3u8") ||
                      cleanPath.endsWith(".m3u") ||
                      urlLower.includes(".m3u8") ||
                      urlLower.includes("/hls/") ||
                      urlLower.includes("playlist.m3u8") ||
                      urlLower.includes("master.m3u8") ||
                      STREAM_MIMES.some((m) => mimeType.includes(m));
        const isDash = cleanPath.endsWith(".mpd") ||
                       urlLower.includes(".mpd") ||
                       mimeType.includes("dash+xml");

        // 2. Filter out individual chunk fragments (.ts, .m4s, .m4f, video/mp2t, fMP4 init)
        const isFragment = cleanPath.endsWith(".ts") ||
                           cleanPath.endsWith(".m4s") ||
                           cleanPath.endsWith(".m4f") ||
                           cleanPath.endsWith(".key") ||
                           cleanPath.endsWith(".aac") ||
                           mimeType.includes("mp2t") ||
                           mimeType.includes("video/mp2t") ||
                           urlLower.includes("/segment") ||
                           urlLower.includes("/seg-") ||
                           urlLower.includes("/seg_") ||
                           urlLower.includes("/frag-") ||
                           urlLower.includes("/frag_") ||
                           urlLower.includes("/chunk-") ||
                           urlLower.includes("/chunk_") ||
                           urlLower.includes("/slice-") ||
                           urlLower.includes("/part-") ||
                           urlLower.includes("_init_") ||
                           urlLower.includes("-init-") ||
                           urlLower.includes("/init_") ||
                           urlLower.includes("_init.") ||
                           urlLower.includes("-init.") ||
                           urlLower.includes("_header_") ||
                           urlLower.includes("-header-") ||
                           cleanPath.endsWith("init.mp4") ||
                           cleanPath.endsWith("header.mp4") ||
                           /_\d{3,6}_/i.test(urlLower) ||
                           /\/(?:\d{3,4}p?\/)?\d{1,6}\.(?:mp4|m4s|ts)(\?|$)/i.test(urlLower) ||
                           /(?:seg|frag|chunk|slice|part|piece)[-_/0-9]+\.(?:mp4|m4s|ts)/i.test(urlLower) ||
                           /[?&](?:range|bytes|bytestart)=/i.test(urlLower);

        if (isFragment && !isHls) {
          return; // Silently ignore transport stream chunks
        }

        let isMedia = false;
        let ext = "mp4";
        let isStream = false;

        if (isHls) {
          isMedia = true;
          isStream = true;
          ext = "m3u8";
        } else if (isDash) {
          isMedia = true;
          isStream = true;
          ext = "mpd";
        } else {
          // Check direct video/audio extensions & mimes
          const matchedExt = DIRECT_MEDIA_EXTENSIONS.find((e) => cleanPath.endsWith(e));
          if (matchedExt) {
            isMedia = true;
            ext = matchedExt.replace(".", "");
          } else if (DIRECT_MEDIA_MIMES.some((m) => mimeType.includes(m))) {
            isMedia = true;
            ext = mimeType.split("/")[1] || "mp4";
          }

          // Filter out tiny video fragments (< 3MB) to prevent flooding with fMP4 segments
          if (isMedia) {
            const isVideo = ext === "mp4" || ext === "webm" || ext === "mkv" || mimeType.startsWith("video/");
            if (isVideo && contentLength > 0 && contentLength < 3145728) {
              isMedia = false;
            } else if (contentLength > 0 && contentLength < 65536) {
              isMedia = false;
            }
          }
        }

        if (isMedia) {
          const cleanUrl = details.url.split("?")[0].split("#")[0];
          const parts = cleanUrl.split("/");
          const rawName = parts[parts.length - 1] || ("video." + ext);
          let name = rawName;
          try { name = decodeURIComponent(rawName); } catch (e) {}
          if (isAdOrJunkMedia(details.url, name, { initiator: details.initiator || "" })) {
            return;
          }
          const isLive = isHls && (
            urlLower.includes("chaturbate.com") ||
            urlLower.includes("stripchat.com")
          );
          recordStream(details.tabId, {
            url: details.url,
            name: name,
            ext: ext,
            mime: mimeType,
            size: contentLength,
            is_hls: isHls,
            is_dash: isDash,
            is_stream: isStream,
            is_live: isLive,
            initiator: details.initiator || ""
          });
        }
      },
      { urls: ["<all_urls>"] },
      ["responseHeaders"]
    );
  }
} catch (e) {
  console.warn("[Krolix] onHeadersReceived setup:", e);
}

// Listen to messages from content scripts and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.action === "STORE_STREAM") {
    const tabId = (message.tabId !== undefined) ? message.tabId : (sender.tab ? sender.tab.id : -1);
    if (tabId >= 0 && message.stream) {
      if (isAdOrJunkMedia(message.stream.url, message.stream.name, message.stream)) {
        sendResponse({ success: false, reason: "ad_or_junk_filtered" });
        return true;
      }
      recordStream(tabId, message.stream);
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false });
    }
    return true;
  } else if (message && message.action === "GET_TAB_STREAMS") {
    const tabId = (message.tabId !== undefined) ? message.tabId : (sender.tab ? sender.tab.id : -1);
    (async () => {
      let streams = [];
      if (tabId >= 0) {
        if (tabStreamHistory.has(tabId) && tabStreamHistory.get(tabId).size > 0) {
          streams = Array.from(tabStreamHistory.get(tabId).values());
        } else if (chrome.storage && chrome.storage.session) {
          try {
            const storageKey = `tab_streams_${tabId}`;
            const res = await chrome.storage.session.get(storageKey);
            if (res && res[storageKey] && Array.isArray(res[storageKey])) {
              streams = res[storageKey];
              // Restore into in-memory map
              if (!tabStreamHistory.has(tabId)) {
                tabStreamHistory.set(tabId, new Map());
              }
              const tabMap = tabStreamHistory.get(tabId);
              streams.forEach(s => tabMap.set(s.url, s));
            }
          } catch (e) {}
        }
      }
      // Strictly filter out any ads or junk previews before returning to UI
      const cleanStreams = streams.filter(s => !isAdOrJunkMedia(s.url, s.name, s));
      if (tabId >= 0) {
        const cleanMap = new Map();
        cleanStreams.forEach(s => cleanMap.set(s.url, s));
        tabStreamHistory.set(tabId, cleanMap);
        try {
          if (chrome.storage?.session) {
            chrome.storage.session.set({ [`tab_streams_${tabId}`]: cleanStreams });
          }
          if (chrome.action?.setBadgeText) {
            chrome.action.setBadgeText({ tabId: tabId, text: cleanStreams.length > 0 ? String(cleanStreams.length) : "" });
          }
        } catch (e) {}
      }
      sendResponse({ streams: cleanStreams });
    })();
    return true;
  } else if (message && message.action === "CLEAR_TAB_STREAMS") {
    const tabId = (message.tabId !== undefined) ? message.tabId : (sender.tab ? sender.tab.id : -1);
    if (tabId >= 0) {
      tabStreamHistory.delete(tabId);
      try {
        if (chrome.storage?.session) {
          chrome.storage.session.remove(`tab_streams_${tabId}`);
        }
        if (chrome.action?.setBadgeText) {
          chrome.action.setBadgeText({ tabId: tabId, text: "" });
        }
      } catch (e) {}
    }
    sendResponse({ success: true });
    return true;
  } else if (message && message.action === "DOWNLOAD_MEDIA") {
    (async () => {
      try {
        const streamData = message.data || {};
        const cleanStreamUrl = (streamData.url || "").split("?")[0].split("#")[0];
        const sniffed = capturedStreamHeaders.get(streamData.url) || capturedStreamHeaders.get(cleanStreamUrl) || streamData.requestHeaders || {};

        const cachedM3u8 = streamData.m3u8Content || capturedM3u8Content.get(streamData.url) || capturedM3u8Content.get(cleanStreamUrl) || "";

        const result = await sendToZero({
          url: streamData.url,
          filename: streamData.filename || "",
          referer: streamData.referer || sniffed["Referer"] || sniffed["referer"] || streamData.initiator || streamData.pageUrl || (sender.tab ? sender.tab.url : ""),
          initiator: streamData.initiator || "",
          pageUrl: streamData.pageUrl || "",
          masterUrl: streamData.masterUrl || "",
          fallbackUrls: streamData.fallbackUrls || [],
          title: streamData.title || "",
          filesize: streamData.filesize || streamData.size || -1,
          resolution: streamData.resolution || "",
          bitrate: streamData.bitrate || 0,
          height: streamData.height || 0,
          width: streamData.width || 0,
          variants: streamData.variants || [],
          m3u8Content: cachedM3u8,
          companion_audio: streamData.companion_audio || null,
          format_id: streamData.format_id || "",
          is_media: true,
          is_hls: !!streamData.is_hls,
          is_dash: !!streamData.is_dash,
          is_live: !!streamData.is_live,
          audio_only: !!streamData.audio_only,
          open_grabber: !!streamData.open_grabber,
          requestHeaders: sniffed
        });
        sendResponse({ success: result });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true; // Keep message channel open for async response
  } else if (message && message.action === "GET_MEDIA_INFO") {
    (async () => {
      try {
        const response = await fetch("http://127.0.0.1:9666/api/media_info", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: message.url })
        });
        if (response.ok) {
          const data = await response.json();
          sendResponse({ success: true, data: data });
        } else {
          sendResponse({ success: false, error: response.statusText });
        }
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true;
  } else if (message && message.action === "BATCH_DOWNLOAD_STREAMS") {
    const items = Array.isArray(message.items) ? message.items : [];
    if (items.length > 0) {
      sendBatchToZero({
        referer: message.referer || (sender.tab ? sender.tab.url : ""),
        user_agent: navigator.userAgent,
        items
      });
    }
    sendResponse({ success: items.length > 0, count: items.length });
    return true;
  } else if (message && message.action === "OPEN_OPTIONS") {
    try {
      if (chrome.runtime?.openOptionsPage) {
        chrome.runtime.openOptionsPage();
      }
    } catch (e) {}
    sendResponse({ success: true });
    return true;
  }
});

// Debounce guard for sendToZero to prevent duplicate popups / multiple process spawns
const _recentlyDispatchedUrls = new Map();

// Helper to communicate with Zero desktop application (with auto-launch & cookie forwarding)
async function sendToZero(options) {
  try {
    const now = Date.now();
    const normUrl = (options.url || "").trim();
    if (!options.force && normUrl) {
      // Clean up entries older than 5000ms
      for (const [u, t] of _recentlyDispatchedUrls.entries()) {
        if (now - t > 5000) _recentlyDispatchedUrls.delete(u);
      }
      const lastTime = _recentlyDispatchedUrls.get(normUrl);
      if (lastTime && (now - lastTime) < 2500) {
        console.log("[Krolix] Debounced duplicate sendToZero request:", normUrl);
        return true;
      }
      _recentlyDispatchedUrls.set(normUrl, now);
    }

    let finalReferer = options.referer || "";
    const urlLower = (options.url || "").toLowerCase();

    // Auto-fix referer for anti-hotlink CDN & streaming hosts
    if (urlLower.includes("mxcontent.net") || urlLower.includes("mixdrop") || urlLower.includes("mxdrop")) {
      if (options.initiator && (options.initiator.includes("mixdrop") || options.initiator.includes("mxdrop"))) {
        finalReferer = options.initiator.endsWith("/") ? options.initiator : options.initiator + "/";
      } else {
        finalReferer = "https://mxdrop.top/";
      }
    } else if (urlLower.includes("tapecontent.net") || urlLower.includes("streamtape")) {
      finalReferer = "https://streamtape.com/";
    } else if (urlLower.includes("dood.") || urlLower.includes("doodstream") || urlLower.includes("ds202.club")) {
      finalReferer = "https://doodstream.com/";
    } else if (urlLower.includes("voe.sx")) {
      finalReferer = "https://voe.sx/";
    } else if (urlLower.includes("cdn-tnmr.org") || urlLower.includes("tnmr.org")) {
      if (!finalReferer || (!finalReferer.includes("missav") && !finalReferer.includes("netflav") && !finalReferer.includes("lulu"))) {
        finalReferer = "https://missav.ws/";
      }
    }

    const cleanUrl = (options.url || "").split("?")[0].split("#")[0];
    const sniffed = capturedStreamHeaders.get(options.url) || capturedStreamHeaders.get(cleanUrl) || options.requestHeaders || {};
    const m3u8Text = options.m3u8Content || capturedM3u8Content.get(options.url) || capturedM3u8Content.get(cleanUrl) || "";

    // Strip bulky m3u8Content from each variant item so JSON payload stays lean
    const cleanVariants = Array.isArray(options.variants)
      ? options.variants.map((v) => {
          const copy = Object.assign({}, v);
          delete copy.m3u8Content;
          return copy;
        })
      : [];

    const payload = {
      url: options.url,
      filename: options.filename || "",
      title: options.title || "",
      filesize: options.filesize || -1,
      resolution: options.resolution || "",
      bitrate: options.bitrate || 0,
      height: options.height || 0,
      width: options.width || 0,
      variants: cleanVariants,
      m3u8_content: m3u8Text,
      companion_audio: options.companion_audio || null,
      format_id: options.format_id || "",
      is_media: !!options.is_media,
      is_hls: !!options.is_hls,
      is_dash: !!options.is_dash,
      is_live: !!options.is_live,
      audio_only: !!options.audio_only,
      open_grabber: !!options.open_grabber,
      headers: {
        "Referer": sniffed["Referer"] || sniffed["referer"] || finalReferer,
        "User-Agent": sniffed["User-Agent"] || sniffed["user-agent"] || navigator.userAgent,
        "master_url": options.masterUrl || "",
        "fallback_urls": Array.isArray(options.fallbackUrls) ? options.fallbackUrls.join("|||") : (options.fallbackUrls || ""),
        "page_url": options.pageUrl || finalReferer,
        "is_dash": options.is_dash ? "true" : "false"
      }
    };

    if (sniffed["Origin"] || sniffed["origin"]) {
      payload.headers["Origin"] = sniffed["Origin"] || sniffed["origin"];
    }
    if (sniffed["Authorization"] || sniffed["authorization"]) {
      payload.headers["Authorization"] = sniffed["Authorization"] || sniffed["authorization"];
    }
    if (sniffed["Cookie"] || sniffed["cookie"]) {
      payload.headers["Cookie"] = sniffed["Cookie"] || sniffed["cookie"];
    }
    if (sniffed["Accept-Language"] || sniffed["accept-language"]) {
      payload.headers["Accept-Language"] = sniffed["Accept-Language"] || sniffed["accept-language"];
    }

    // Extract cookies for the target URL or referer domain to prevent 403 Forbidden on CDNs & stream hosts
    if (chrome.cookies && !payload.headers["Cookie"]) {
      try {
        const cookies1 = options.url ? await chrome.cookies.getAll({ url: options.url }).catch(() => []) : [];
        const cookies2 = options.referer ? await chrome.cookies.getAll({ url: options.referer }).catch(() => []) : [];
        const allCookies = [...(cookies1 || []), ...(cookies2 || [])];
        if (allCookies.length > 0) {
          const cookieMap = new Map();
          allCookies.forEach((c) => cookieMap.set(c.name, c.value));
          payload.headers["Cookie"] = Array.from(cookieMap.entries()).map(([k, v]) => `${k}=${v}`).join("; ");
        }
      } catch (cookieErr) {
        console.warn("[Krolix] Could not read cookies:", cookieErr);
      }
    }

    // Slim payload without m3u8_content / variants for fallback / auto-launch
    const slimPayload = Object.assign({}, payload, {
      m3u8_content: "",
      variants: []
    });

    // Step 1: Fast HTTP attempt if Zero desktop app is already open
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3500);

      const response = await fetch(ZERO_API, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zero-Client": "extension"
        },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        console.log("[Krolix] Successfully sent download to running desktop app.");
        return true;
      }

      // If desktop app responded with HTTP error (e.g. 413), retry with slimPayload over HTTP and DO NOT auto-launch duplicate exes
      const retryResp = await fetch(ZERO_API, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zero-Client": "extension"
        },
        body: JSON.stringify(slimPayload)
      });
      if (retryResp.ok) {
        return true;
      }
      return false;
    } catch (httpErr) {
      console.log("[Krolix] Desktop app is offline or unreachable via HTTP. Trying auto-launch fallback...");
    }

    // Step 2: Desktop app is closed -> Sequential Auto-Launch using slimPayload!
    let launched = false;

    // A. Native Messaging Host (try com.krolix.downloader, fallback to com.zero.downloader)
    if (chrome.runtime?.sendNativeMessage) {
      const sendNative = (hostName) => new Promise((resolve) => {
        try {
          chrome.runtime.sendNativeMessage(hostName, slimPayload, (res) => {
            if (chrome.runtime.lastError) {
              resolve(false);
            } else if (res && res.status === "ok") {
              console.log("[Krolix] Native messaging successfully dispatched download:", res);
              if (res.license) {
                chrome.storage.local.set({ krolixLicense: res.license, zeroLicense: res.license });
              }
              resolve(true);
            } else {
              resolve(false);
            }
          });
        } catch (e) {
          resolve(false);
        }
      });
      launched = await sendNative("com.krolix.downloader");
      if (!launched) {
        launched = await sendNative("com.zero.downloader");
      }
    }

    // B. Custom Protocol URL (krolix-dl://) ONLY if Native Messaging was not successful
    if (!launched) {
      try {
        const jsonStr = JSON.stringify(slimPayload);
        const bytes = new TextEncoder().encode(jsonStr);
        let binStr = "";
        for (let i = 0; i < bytes.length; i++) {
          binStr += String.fromCharCode(bytes[i]);
        }
        const b64 = btoa(binStr).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
        const protocolUrl = `krolix-dl://download?data=${b64}`;

        const tabs = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
        let launchedViaTab = false;
        if (tabs && tabs.length > 0 && tabs[0]?.id) {
          try {
            await chrome.tabs.sendMessage(tabs[0].id, {
              action: "LAUNCH_PROTOCOL_URL",
              url: protocolUrl
            }, { frameId: 0 }); // Target only the main top-level frame (frameId: 0)!
            launchedViaTab = true;
            launched = true;
          } catch (err) {}
        }

        if (!launchedViaTab) {
          chrome.tabs.create({ url: protocolUrl, active: false }, (newTab) => {
            if (chrome.runtime?.lastError || !newTab || !newTab.id) return;
            const tempId = newTab.id;
            setTimeout(() => {
              try {
                chrome.tabs.get(tempId, (tab) => {
                  if (chrome.runtime?.lastError || !tab) return;
                  const p = chrome.tabs.remove(tempId);
                  if (p && typeof p.catch === "function") p.catch(() => {});
                });
              } catch (e) {}
            }, 1500);
          });
          launched = true;
        }
      } catch (protoErr) {
        console.log("[Krolix] Protocol trigger notice:", protoErr);
      }
    }

    return launched;
  } catch (err) {
    console.warn("[Krolix] Failed to send download to Zero:", err);
    return false;
  }
}
