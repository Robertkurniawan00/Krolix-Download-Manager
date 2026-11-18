/**
 * Zero Download Assistant - Content Script (Floating Video Engine)
 * Injects Zero floating "Download this video" button with format dropdown (1080p, 720p, 480p | bitrate | size/duration).
 */

(function () {
  if (window.__zero_float_injected) return;
  window.__zero_float_injected = true;

  const IS_YOUTUBE = window.location.hostname.includes("youtube.com");
  let activePanel = null;
  let activeVideo = null;
  let hideTimer = null;
  let isHoveringPanel = false;
  let isMenuOpen = false;
  let isDismissedForCurrentUrl = false;
  let lastUrl = window.location.href;

  // Media info cache keyed by video URL: { title, duration, thumbnail, formats: [...] }
  const mediaInfoCache = {};
  let isFetchingFormats = false;

  // Background media sniffer streams
  const sniffedStreams = [];
  const parsedPlaylistsCache = new Map();

  let scanInterval = null;
  let observer = null;

  function isExtensionValid() {
    try {
      return typeof chrome !== "undefined" && !!chrome.runtime && !!chrome.runtime.id;
    } catch (e) {
      return false;
    }
  }

  function cleanupOrphanedScript() {
    if (scanInterval) {
      clearInterval(scanInterval);
      scanInterval = null;
    }
    if (observer) {
      try {
        observer.disconnect();
      } catch (e) {}
      observer = null;
    }
    if (activePanel) {
      try {
        activePanel.remove();
      } catch (e) {}
      activePanel = null;
    }
  }

  function safeSendMessage(message, callback) {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    try {
      chrome.runtime.sendMessage(message, (response) => {
        if (!isExtensionValid() || chrome.runtime?.lastError) {
          return;
        }
        if (typeof callback === "function") {
          callback(response);
        }
      });
    } catch (err) {
      cleanupOrphanedScript();
    }
  }


  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

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

    // Live Cam Affiliate Widgets & Ad Streams
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
  const LIVE_CAM_WIDGET_REGEX = /(?:\b(?:auto|\d{3,4}p)\.m3u8_\d{5,15}|\.m3u8_\d{6,15}(?:$|[?&])|\/hls\/\d{6,12}\/(?:master\/)?\d{6,12}(?:_auto|_\d{3,4}p)?\.m3u8)/i;

  function isAdIframe() {
    try {
      if (window === window.top) return false;
      const host = (window.location.hostname || "").toLowerCase();
      const href = (window.location.href || "").toLowerCase();

      // Check if iframe location itself matches ad domains
      if (AD_DOMAINS_AND_SERVERS.some((ad) => host.includes(ad) || href.includes(ad))) {
        return true;
      }
      if (AD_URL_REGEX.test(href) || AD_PATH_REGEX.test(href) || AD_QUERY_PARAM_REGEX.test(href) || LIVE_CAM_WIDGET_REGEX.test(href)) {
        return true;
      }

      // Check frameElement if accessible (same-origin iframe)
      if (window.frameElement) {
        const id = (window.frameElement.id || "").toLowerCase();
        const cls = (window.frameElement.className || "").toLowerCase();
        const name = (window.frameElement.name || "").toLowerCase();
        const full = id + " " + cls + " " + name;
        if (/(?:google_ads_iframe|aswift|ad-frame|ad_frame|adframe|banner|sponsor|advert)/i.test(full)) {
          return true;
        }
        const rect = window.frameElement.getBoundingClientRect();
        if ((rect.width > 0 && rect.width <= 320 && rect.height > 0 && rect.height <= 250) || (rect.width > 0 && rect.width <= 728 && rect.height > 0 && rect.height <= 90)) {
          return true;
        }
      }
    } catch (e) {
      try {
        const href = (window.location.href || "").toLowerCase();
        if (AD_DOMAINS_AND_SERVERS.some((ad) => href.includes(ad))) return true;
      } catch (e2) {}
    }
    return false;
  }

  // Terminate immediately if running inside a third-party ad iframe
  if (isAdIframe()) return;

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

    // 2. Video Advertising Networks & Ad Servers
    const initiator = (payload && payload.initiator) ? (payload.initiator || "").toLowerCase() : "";
    if (AD_DOMAINS_AND_SERVERS.some((ad) => u.includes(ad) || initiator.includes(ad))) {
      return true;
    }

    // 3. Ad keywords & protocols in URL paths or filenames or query params
    if (AD_URL_REGEX.test(u) || AD_URL_REGEX.test(n) || AD_PATH_REGEX.test(u) || AD_QUERY_PARAM_REGEX.test(u)) {
      return true;
    }

    // 4. YouTube ad state check: if on YouTube and movie_player is showing ad, googlevideo URLs are ads!
    if (IS_YOUTUBE) {
      const moviePlayer = document.querySelector("#movie_player");
      if (moviePlayer && moviePlayer.classList && (moviePlayer.classList.contains("ad-showing") || moviePlayer.classList.contains("ad-interrupting"))) {
        if (u.includes("googlevideo.com")) {
          return true;
        }
      }
      if (document.querySelector(".ytp-ad-module, .ytp-ad-player-overlay, .ytp-ad-text, .video-ads.ytp-ad-module")) {
        if (u.includes("googlevideo.com")) {
          return true;
        }
      }
    }

    // 5. Low resolution preview filters: <= 180p with blur or preview
    if (payload) {
      const h = payload.height || 0;
      const dur = payload.duration || 0;
      if (h > 0 && h <= 180 && (full.includes("blur") || full.includes("preview") || (dur > 0 && dur < 30))) {
        return true;
      }
    }

    return false;
  }

  function isAdVideoElement(video) {
    if (!video) return false;

    // 1. Check video src & currentSrc
    const src = video.currentSrc || video.src || "";
    if (src && isAdOrJunkMedia(src)) return true;

    // 2. YouTube active ad state
    if (IS_YOUTUBE) {
      const moviePlayer = document.querySelector("#movie_player");
      if (moviePlayer && moviePlayer.classList) {
        if (moviePlayer.classList.contains("ad-showing") || moviePlayer.classList.contains("ad-interrupting")) {
          return true;
        }
      }
      if (document.querySelector(".ytp-ad-module, .ytp-ad-player-overlay, .ytp-ad-text, .ytp-ad-preview-container, .video-ads.ytp-ad-module")) {
        return true;
      }
    }

    // 3. Check classes, IDs, and attributes on video element and parents up to 10 levels
    const adClassOrIdRegex = /(?:^|[\s_-])(?:ad|ads|advert|video-ads|video-ad|videoad|ad-container|ad-showing|ad-interrupting|ad-module|ytp-ad|ima-ad|ima-ad-container|preroll|midroll|postroll|sponsor|commercial|banner-video|jw-flag-ads|jw-state-ad|jw-ad-showing|vjs-ad-playing|vjs-ad-loading|vjs-ad-showing|fluid_ad_showing|plyr--ads)(?:[\s_-]|$)/i;

    let curr = video;
    let depth = 0;
    while (curr && curr !== document.body && depth < 10) {
      const cls = (typeof curr.className === "string") ? curr.className : "";
      const id = curr.id || "";
      if (adClassOrIdRegex.test(cls) || adClassOrIdRegex.test(id)) {
        return true;
      }
      if (curr.hasAttribute) {
        if (
          curr.hasAttribute("data-ad") ||
          curr.hasAttribute("data-is-ad") ||
          curr.hasAttribute("data-ad-unit") ||
          (curr.hasAttribute("data-role") && curr.getAttribute("data-role") === "ad-video") ||
          curr.getAttribute("aria-label") === "Advertisement" ||
          curr.getAttribute("aria-label") === "Iklan"
        ) {
          return true;
        }
      }
      curr = curr.parentElement;
      depth++;
    }

    // 4. Video dimensions: tiny tracking / banner video
    try {
      const rect = video.getBoundingClientRect();
      if ((rect.width > 0 && rect.width < 160) || (rect.height > 0 && rect.height < 120)) {
        return true;
      }
      const style = window.getComputedStyle(video);
      if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity || "1") < 0.1) {
        return true;
      }
    } catch (e) {}

    // 5. Ad iframe check
    if (isAdIframe()) {
      return true;
    }

    return false;
  }

  // Handle background requests, e.g. "Download all links with Zero"
  if (isExtensionValid()) {
    try {
      chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request && request.type === "EXTRACT_PAGE_LINKS") {
          const links = new Set();
          const items = [];

          // 1. Collect anchor links (excluding ads)
          const anchors = document.querySelectorAll("a[href]");
          anchors.forEach((a) => {
            const href = a.href;
            if (href && (href.startsWith("http://") || href.startsWith("https://") || href.startsWith("ftp://") || href.startsWith("magnet:"))) {
              if (!links.has(href) && !isAdOrJunkMedia(href)) {
                links.add(href);
                const desc = (a.innerText || "").trim().slice(0, 120) || a.title || "";
                items.push({ url: href, description: desc });
              }
            }
          });

          // 2. Collect media elements (excluding ad videos and junk previews)
          const media = document.querySelectorAll("img[src], video[src], audio[src], source[src]");
          media.forEach((m) => {
            const src = m.src;
            if (src && (src.startsWith("http://") || src.startsWith("https://")) && !links.has(src)) {
              const parentVid = m.tagName === "SOURCE" ? m.closest("video") : (m.tagName === "VIDEO" ? m : null);
              if (!isAdOrJunkMedia(src) && (!parentVid || !isAdVideoElement(parentVid))) {
                links.add(src);
                const desc = (m.alt || m.title || "").trim().slice(0, 120);
                items.push({ url: src, description: desc });
              }
            }
          });

          sendResponse({ items: items.slice(0, 500) });
          return true;
        }
      });
    } catch (e) {}
  }

  function isFragment(url) {
    if (!url) return true;
    if (isAdOrJunkMedia(url)) return true;

    const u = url.toLowerCase();
    const clean = u.split("?")[0].split("#")[0];

    // Master / Variant HLS or DASH manifests are NEVER fragments!
    if (
      clean.endsWith(".m3u8") ||
      u.includes(".m3u8") ||
      clean.endsWith(".mpd") ||
      u.includes(".mpd") ||
      u.includes("playlist.m3u8") ||
      u.includes("master.m3u8") ||
      u.includes("chunklist")
    ) {
      return false;
    }

    // Known segment extensions
    if (
      clean.endsWith(".ts") ||
      clean.endsWith(".m4s") ||
      clean.endsWith(".m4f") ||
      clean.endsWith(".aac") ||
      clean.endsWith(".key")
    ) {
      return true;
    }

    // Ads and trackers
    if (
      u.includes("googleads") ||
      u.includes("doubleclick") ||
      u.includes("/pagead/") ||
      u.includes("googlesyndication")
    ) {
      return true;
    }

    // Common chunk/fragment naming patterns (HLS / CMAF / fMP4)
    if (
      u.includes("/segment") ||
      u.includes("/seg-") ||
      u.includes("/seg_") ||
      u.includes("/frag-") ||
      u.includes("/frag_") ||
      u.includes("/chunk-") ||
      u.includes("/chunk_") ||
      u.includes("/slice-") ||
      u.includes("/part-") ||
      u.includes("_init_") ||
      u.includes("-init-") ||
      u.includes("/init_") ||
      u.includes("_init.") ||
      u.includes("-init.") ||
      u.includes("_header_") ||
      u.includes("-header-") ||
      clean.endsWith("init.mp4") ||
      clean.endsWith("header.mp4") ||
      /_\d{3,6}_/i.test(u)
    ) {
      return true;
    }

    // Segment regex: numbered chunks e.g. /0001.mp4, /123.mp4, /720/1.mp4, seg-1.mp4
    if (/\/(?:\d{3,4}p?\/)?\d{1,6}\.(?:mp4|m4s|ts)(\?|$)/i.test(u)) {
      return true;
    }
    if (/(?:seg|frag|chunk|slice|part|piece)[-_/0-9]+\.(?:mp4|m4s|ts)/i.test(u)) {
      return true;
    }

    // Byte-range streaming
    if (/[?&](?:range|bytes|bytestart)=/i.test(u)) {
      return true;
    }

    return false;
  }

  const m3u8TextCache = new Map();

  // Parse HLS master/media playlist into resolution variants with bandwidth, duration, and cached m3u8Content
  async function parseM3u8Variants(m3u8Url, videoDuration) {
    if (parsedPlaylistsCache.has(m3u8Url)) {
      return parsedPlaylistsCache.get(m3u8Url);
    }
    try {
      let text = m3u8TextCache.get(m3u8Url) || "";
      if (!text || !text.includes("#EXTM3U")) {
        const resp = await fetch(m3u8Url, { method: "GET" });
        if (!resp.ok) return null;
        text = await resp.text();
      }
      if (!text || !text.includes("#EXTM3U")) return null;
      m3u8TextCache.set(m3u8Url, text);

      if (!text.includes("#EXT-X-STREAM-INF")) {
        // Single Media Playlist with #EXTINF segments
        if (text.includes("#EXTINF")) {
          let sumDur = 0;
          const matches = text.matchAll(/#EXTINF:([\d.]+)/g);
          for (const m of matches) {
            sumDur += parseFloat(m[1]) || 0;
          }
          const dur = sumDur || videoDuration || (activeVideo ? activeVideo.duration : 0) || 0;
          const h = (activeVideo ? activeVideo.videoHeight : 0) || 0;
          const w = (activeVideo ? activeVideo.videoWidth : 0) || 0;
          const resStr = (w && h) ? `${w}x${h}` : (h ? `${h}p` : "Original");
          const isLiveStream = !text.includes("#EXT-X-ENDLIST") || window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");
          const vLabel = h ? `${h}p` : "Original";
          const singleVariant = [{
            url: m3u8Url,
            masterUrl: m3u8Url,
            height: h,
            width: w,
            resolution: resStr,
            bandwidth: 0,
            bitrate: 0,
            filesize: -1,
            size: -1,
            total_bytes: -1,
            duration: dur,
            ext: "mp4",
            is_hls: true,
            is_stream: true,
            is_live: isLiveStream,
            label: vLabel,
            name: vLabel,
            display_name: h ? `${h}p (${resStr})` : "Original",
            m3u8Content: text
          }];
          parsedPlaylistsCache.set(m3u8Url, singleVariant);
          return singleVariant;
        }
        return null;
      }

      const variants = [];
      const lines = text.split("\n");
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line.startsWith("#EXT-X-STREAM-INF:")) {
          const bwMatch = line.match(/BANDWIDTH=(\d+)/);
          const avgBwMatch = line.match(/AVERAGE-BANDWIDTH=(\d+)/);
          const resMatch = line.match(/RESOLUTION=(\d+)x(\d+)/);

          const bandwidth = avgBwMatch ? parseInt(avgBwMatch[1], 10) : (bwMatch ? parseInt(bwMatch[1], 10) : 0);
          const width = resMatch ? parseInt(resMatch[1], 10) : 0;
          const height = resMatch ? parseInt(resMatch[2], 10) : 0;

          let uri = "";
          for (let j = i + 1; j < lines.length; j++) {
            const nextLine = lines[j].trim();
            if (nextLine && !nextLine.startsWith("#")) {
              uri = nextLine;
              break;
            }
          }

          if (uri) {
            let resolvedUrl = uri;
            try {
              const uObj = new URL(uri, m3u8Url);
              // FetchV methodology: inherit CDN auth tokens/query params from parent playlist
              if (!uObj.search && m3u8Url.includes("?")) {
                const parentSearch = new URL(m3u8Url).search;
                if (parentSearch) {
                  uObj.search = parentSearch;
                }
              }
              resolvedUrl = uObj.href;
            } catch (uErr) {
              resolvedUrl = uri;
            }

            if (isAdOrJunkMedia(resolvedUrl, uri, { height, width })) {
              continue;
            }

            const dur = videoDuration || (activeVideo ? activeVideo.duration : 0) || 0;
            const estimatedBytes = (bandwidth && dur > 0) ? Math.round((bandwidth * dur) / 8) : -1;
            const resStr = (width && height) ? `${width}x${height}` : (height ? `${height}p` : "");
            const bitKbps = bandwidth ? Math.round(bandwidth / 1000) : 0;

            const isLiveStream = !text.includes("#EXT-X-ENDLIST") || window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");

            const vLabel = height ? `${height}p` : "HLS Stream";
            const parts = [];
            if (height) parts.push(`${height}p` + (resStr ? ` (${resStr})` : ""));
            if (bitKbps > 0) parts.push(bitKbps >= 1000 ? `${(bitKbps/1000).toFixed(1)} Mbps` : `${bitKbps} kbps`);
            if (estimatedBytes > 0) parts.push(`~${formatBytes(estimatedBytes)}`);
            else if (isLiveStream) parts.push("Live Stream");
            const dispName = parts.length > 0 ? parts.join(" • ") : vLabel;

            variants.push({
              url: resolvedUrl,
              masterUrl: m3u8Url,
              height: height,
              width: width,
              resolution: resStr,
              bandwidth: bandwidth,
              bitrate: bitKbps,
              filesize: estimatedBytes,
              size: estimatedBytes,
              total_bytes: estimatedBytes,
              duration: dur,
              ext: "mp4",
              is_hls: true,
              is_stream: true,
              is_live: isLiveStream,
              label: vLabel,
              name: vLabel,
              display_name: dispName,
              m3u8Content: m3u8TextCache.get(resolvedUrl) || ""
            });
          }
        }
      }

      if (variants.length > 0) {
        variants.sort((a, b) => (b.height || 0) - (a.height || 0) || (b.bandwidth || 0) - (a.bandwidth || 0));

        // Fetch top variant media playlist to compute exact duration, filesize, AND cache its #EXTM3U text!
        let activeDur = videoDuration || (activeVideo ? activeVideo.duration : 0) || 0;
        if (variants[0].url) {
          try {
            let vText = m3u8TextCache.get(variants[0].url) || "";
            if (!vText || !vText.includes("#EXTM3U")) {
              const vResp = await fetch(variants[0].url, { method: "GET" });
              if (vResp.ok) {
                vText = await vResp.text();
              }
            }
            if (vText && vText.includes("#EXTINF")) {
              const vIsLive = !vText.includes("#EXT-X-ENDLIST") || window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");
              if (vIsLive) {
                variants.forEach((v) => {
                  v.is_live = true;
                  v.duration = 0;
                  v.filesize = -1;
                  v.size = -1;
                  v.total_bytes = -1;
                  v.m3u8Content = "";
                  const p = [];
                  if (v.height) p.push(`${v.height}p` + (v.resolution ? ` (${v.resolution})` : ""));
                  if (v.bitrate > 0) p.push(v.bitrate >= 1000 ? `${(v.bitrate/1000).toFixed(1)} Mbps` : `${v.bitrate} kbps`);
                  p.push("LIVE");
                  v.display_name = p.join(" • ");
                });
              } else {
                m3u8TextCache.set(variants[0].url, vText);
                variants[0].m3u8Content = vText;
                let sumDur = 0;
                const matches = vText.matchAll(/#EXTINF:([\d.]+)/g);
                for (const m of matches) {
                  sumDur += parseFloat(m[1]) || 0;
                }
                if (sumDur > 0) {
                  activeDur = sumDur;
                  variants.forEach((v) => {
                    v.is_live = false;
                    v.duration = activeDur;
                    if (m3u8TextCache.has(v.url)) {
                      v.m3u8Content = m3u8TextCache.get(v.url);
                    }
                    if (v.bandwidth && v.bandwidth > 0) {
                      const est = Math.round((v.bandwidth * activeDur) / 8);
                      v.filesize = est;
                      v.size = est;
                      v.total_bytes = est;
                      const p = [];
                      if (v.height) p.push(`${v.height}p` + (v.resolution ? ` (${v.resolution})` : ""));
                      if (v.bitrate > 0) p.push(v.bitrate >= 1000 ? `${(v.bitrate/1000).toFixed(1)} Mbps` : `${v.bitrate} kbps`);
                      p.push(`~${formatBytes(est)}`);
                      v.display_name = p.join(" • ");
                    }
                  });
                }
              }
            }
          } catch (e) {}
        }

        if (!variants[0].is_live) {
          parsedPlaylistsCache.set(m3u8Url, variants);
        }
        return variants;
      }
    } catch (e) {}
    return null;
  }

  // Handle stream detected from any source
  async function handleStreamDetected(mediaPayload) {
    if (!mediaPayload || !mediaPayload.url) return;
    if (isAdOrJunkMedia(mediaPayload.url, mediaPayload.name, mediaPayload)) return;
    const u = mediaPayload.url;
    if (isFragment(u)) return;

    if (mediaPayload.m3u8Content && mediaPayload.m3u8Content.includes("#EXTM3U")) {
      m3u8TextCache.set(u, mediaPayload.m3u8Content);
    }

    const uLower = u.toLowerCase();
    const cleanPath = uLower.split("?")[0].split("#")[0];
    const isHls = mediaPayload.is_hls || cleanPath.endsWith(".m3u8") || uLower.includes(".m3u8");

    // Check if this URL is an HLS Master or Media Playlist
    if (isHls && !mediaPayload.is_variant) {
      const dur = (activeVideo ? activeVideo.duration : 0) || mediaPayload.duration || 0;
      const variants = await parseM3u8Variants(u, dur);
      if (variants && variants.length > 0) {
        variants.forEach((v) => {
          const existingIdx = sniffedStreams.findIndex((s) => s.url === v.url);
          if (existingIdx < 0) {
            sniffedStreams.push(v);
            safeSendMessage({ action: "STORE_STREAM", stream: v });
          } else {
            Object.assign(sniffedStreams[existingIdx], v);
            safeSendMessage({ action: "STORE_STREAM", stream: sniffedStreams[existingIdx] });
          }
        });
        if (activePanel && isMenuOpen) {
          renderDropdownMenu(activePanel);
        }
        return;
      }
    }

    // Filter out segment chunks and MSE blob-fed video chunks
    if (!isHls && !mediaPayload.is_dash) {
      const sz = mediaPayload.size || mediaPayload.filesize || -1;
      if (sz > 0 && sz < 3145728) {
        return; // Exclude direct files under 3 MB
      }
      const isBlobActive = activeVideo && (activeVideo.src || "").startsWith("blob:");
      if (isBlobActive && (sz <= 0 || sz < 10485760)) {
        return; // If playing from MSE blob, reject direct video chunks under 10MB
      }
    }

    if (!sniffedStreams.some((s) => s.url === u)) {
      const h = mediaPayload.height || (activeVideo ? activeVideo.videoHeight : 0) || 0;
      const dur = mediaPayload.duration || (activeVideo ? activeVideo.duration : 0) || 0;

      let bitrate = mediaPayload.bitrate || 0;
      let size = mediaPayload.size || mediaPayload.filesize || -1;
      if (size > 0 && dur > 0 && !bitrate) {
        bitrate = Math.round((size * 8 / dur) / 1000);
      }

      const isLiveStream = mediaPayload.is_live || window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");

      const enriched = {
        url: u,
        name: mediaPayload.name || (h ? `${h}p` : "Video"),
        ext: mediaPayload.ext || (isHls ? "mp4" : "mp4"),
        mime: mediaPayload.mime || "",
        height: h,
        bitrate: bitrate,
        size: size,
        filesize: size,
        duration: dur,
        is_hls: isHls,
        is_dash: mediaPayload.is_dash || false,
        is_stream: isHls || mediaPayload.is_dash || false,
        is_live: isLiveStream,
        m3u8Content: mediaPayload.m3u8Content || m3u8TextCache.get(u) || ""
      };

      sniffedStreams.push(enriched);
      safeSendMessage({ action: "STORE_STREAM", stream: enriched });

      if (activePanel && isMenuOpen) {
        renderDropdownMenu(activePanel);
      }
    }
  }

  // Listen for media events dispatched by in-page inject.js
  window.addEventListener("__zero_media_detected__", (e) => {
    if (!isExtensionValid()) return;
    const d = e.detail;
    if (d && d.url) {
      if (isAdOrJunkMedia(d.url, d.name, d)) return;
      if (d.m3u8Content && d.m3u8Content.includes("#EXTM3U")) {
        m3u8TextCache.set(d.url, d.m3u8Content);
      }
      const isLive = d.is_live || window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");
      handleStreamDetected({
        url: d.url,
        mime: d.mime,
        ext: d.type === "hls" ? "m3u8" : (d.type === "dash" ? "mpd" : "mp4"),
        is_hls: d.type === "hls",
        is_dash: d.type === "dash",
        is_live: isLive,
        filesize: d.filesize || -1,
        m3u8Content: d.m3u8Content || ""
      });
    }
  });

  // Listen for sniffed streams from background service worker
  try {
    if (isExtensionValid() && chrome.runtime?.onMessage) {
      chrome.runtime.onMessage.addListener((message) => {
        if (!isExtensionValid()) {
          cleanupOrphanedScript();
          return;
        }
        if (message && message.action === "LAUNCH_PROTOCOL_URL" && message.url) {
          if (window !== window.top) {
            return;
          }
          try {
            const a = document.createElement("a");
            a.href = message.url;
            a.style.display = "none";
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
              try { a.remove(); } catch (err) {}
            }, 1200);
          } catch (err) {
            try { window.location.assign(message.url); } catch (e) {}
          }
          return;
        }
        if (message && message.action === "MEDIA_SNIFFED" && message.media) {
          handleStreamDetected(message.media);
        }
      });
    }
  } catch (e) {
    cleanupOrphanedScript();
  }

  // Zero Download Assistant Vector Icons (Crisp Soft Chrome Aesthetic)
  const DOWNLOAD_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none">
      <path d="M12 3v11m0 0l-3.5-3.5M12 14l3.5-3.5" stroke="#cbd5e1" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M4 15.5v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" stroke="#94a3b8" stroke-width="2" stroke-linecap="round"/>
    </svg>
  `;

  const DRAG_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
      <circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/>
      <circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/>
      <circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/>
    </svg>
  `;

  const CLOCK_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="11" height="11" fill="none" style="vertical-align: middle;">
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/>
      <path d="M12 7v5l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </svg>
  `;

  const FILM_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" style="vertical-align: middle;">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
      <path d="M7 4v16M17 4v16M3 8h4M17 8h4M3 12h18M3 16h4M17 16h4" stroke="currentColor" stroke-width="1.8"/>
    </svg>
  `;

  const VIDEO_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" style="vertical-align: middle;">
      <rect x="2" y="4" width="20" height="16" rx="3" stroke="currentColor" stroke-width="1.8"/>
      <polygon points="10,8 16,12 10,16" fill="currentColor"/>
    </svg>
  `;

  const AUDIO_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" style="vertical-align: middle;">
      <path d="M9 18V5l12-2v13" stroke="currentColor" stroke-width="2"/>
      <circle cx="6" cy="18" r="3" fill="currentColor"/><circle cx="18" cy="16" r="3" fill="currentColor"/>
    </svg>
  `;

  const LOCK_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" style="vertical-align: middle;">
      <rect x="5" y="11" width="14" height="10" rx="2" stroke="currentColor" stroke-width="2"/>
      <path d="M8 11V7a4 4 0 0 1 8 0v4" stroke="currentColor" stroke-width="2"/>
    </svg>
  `;

  const DOWNLOAD_TRAY_SVG = `
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" style="vertical-align: middle;">
      <path d="M12 4v10m0 0l-3-3m3 3l3-3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" stroke="currentColor" stroke-width="2"/>
    </svg>
  `;

  const GEAR_ICON_SVG = `
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" style="vertical-align: middle;">
      <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" stroke="currentColor" stroke-width="1.8"/>
    </svg>
  `;

  function getVideoTitle() {
    let rawTitle = "";

    if (IS_YOUTUBE) {
      const ytTitle = document.querySelector("h1.ytd-watch-metadata yt-formatted-string") ||
                      document.querySelector("#title h1 yt-formatted-string") ||
                      document.querySelector("h1.title");
      if (ytTitle && ytTitle.innerText && ytTitle.innerText.trim()) {
        rawTitle = ytTitle.innerText.trim();
      } else {
        rawTitle = document.title.replace(" - YouTube", "").trim();
      }
    } else if (window.location.hostname.includes("chaturbate.com")) {
      const match = window.location.pathname.match(/\/([a-zA-Z0-9_\-]+)/);
      if (match && match[1] && !["b", "p", "tags", "auth", "accounts"].includes(match[1].toLowerCase())) {
        rawTitle = `Chaturbate - ${match[1]} (Live)`;
      }
    } else if (window.location.hostname.includes("stripchat.com")) {
      const match = window.location.pathname.match(/\/([a-zA-Z0-9_\-]+)/);
      if (match && match[1] && !["tags", "auth", "login", "signup", "categories"].includes(match[1].toLowerCase())) {
        rawTitle = `Stripchat - ${match[1]} (Live)`;
      }
    }

    if (!rawTitle) {
      // 1. Check Open Graph & Twitter meta tags
      const ogTitle = document.querySelector('meta[property="og:title"]')?.content ||
                      document.querySelector('meta[name="twitter:title"]')?.content ||
                      document.querySelector('meta[name="title"]')?.content;
      if (ogTitle && ogTitle.trim()) {
        rawTitle = ogTitle.trim();
      }
    }

    if (!rawTitle && activeVideo) {
      // 2. Check active video element attributes or player container
      const vTitle = activeVideo.getAttribute("title") ||
                     activeVideo.getAttribute("aria-label") ||
                     activeVideo.getAttribute("data-title");
      if (vTitle && vTitle.trim()) {
        rawTitle = vTitle.trim();
      }
      if (!rawTitle) {
        const playerContainer = activeVideo.closest("[class*='player'], [id*='player'], .video-js, .jwplayer");
        if (playerContainer) {
          const cTitle = playerContainer.getAttribute("title") || playerContainer.getAttribute("aria-label");
          if (cTitle && cTitle.trim()) rawTitle = cTitle.trim();
        }
      }
    }

    if (!rawTitle) {
      // 3. Check page headings
      const h1 = document.querySelector("h1:not(.hidden)");
      if (h1 && h1.innerText && h1.innerText.trim().length > 2 && h1.innerText.trim().length < 140) {
        rawTitle = h1.innerText.trim();
      } else {
        const itemTitle = document.querySelector(".entry-title, .movie-title, .film-title, .post-title, .title-film");
        if (itemTitle && itemTitle.innerText && itemTitle.innerText.trim()) {
          rawTitle = itemTitle.innerText.trim();
        }
      }
    }

    if (!rawTitle) {
      rawTitle = document.title.trim();
    }

    // Clean spam, website suffixes, advertising fluff, and illegal characters
    let clean = (rawTitle || "Video")
      .replace(/\s*[-–|•]\s*(nonton film|lk21|layarkaca21|rebahin|indoxxi|dutafilm|idlix|bilibili|youtube|vimeo|dailymotion|facebook|tiktok|instagram|xxi|cinemaindo).*/i, "")
      .replace(/nonton film\s+/i, "")
      .replace(/sub(title)?\s+indo(nesia)?/i, "")
      .replace(/watch online free/i, "")
      .replace(/full (movie|episode|hd)/i, "")
      .replace(/[\\/*?:"<>|]/g, "_")
      .trim();

    if (!clean || clean.length < 2 || clean.toLowerCase() === "video" || clean.toLowerCase() === "video player") {
      try {
        const host = window.location.hostname.replace(/^www\./, "");
        clean = `Video_${host}`;
      } catch (e) {
        clean = "Video";
      }
    }

    return clean;
  }

  function getCleanTargetUrl() {
    if (IS_YOUTUBE) {
      try {
        const url = new URL(window.location.href);
        if (url.pathname.includes("/watch") && url.searchParams.has("v")) {
          return `https://www.youtube.com/watch?v=${url.searchParams.get("v")}`;
        } else if (url.pathname.includes("/shorts/")) {
          const shortId = url.pathname.split("/shorts/")[1].split("/")[0].split("?")[0];
          return `https://www.youtube.com/watch?v=${shortId}`;
        }
        // Skip homepage, search results, channel tabs - no single video to extract
        return null;
      } catch (e) {
        return null;
      }
    }
    return window.location.href;
  }

  // Pre-fetch formats from desktop API
  function prefetchMediaInfo(force = false) {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    const targetUrl = getCleanTargetUrl();
    if (!targetUrl || isAdOrJunkMedia(targetUrl)) return;

    const cached = mediaInfoCache[targetUrl];
    if (!force && cached) {
      if (Array.isArray(cached.formats) && cached.formats.length > 0) return;
      if (cached._cachedAt && (Date.now() - cached._cachedAt) < 15000) return;
    }
    if (isFetchingFormats) return;

    isFetchingFormats = true;
    safeSendMessage({
      action: "GET_MEDIA_INFO",
      url: targetUrl
    }, (response) => {
      isFetchingFormats = false;
      if (response && response.success && response.data && Array.isArray(response.data.formats) && response.data.formats.length > 0) {
        mediaInfoCache[targetUrl] = response.data;
        if (activePanel && isMenuOpen) {
          renderDropdownMenu(activePanel);
        }
      } else {
        // Negative cache with 15-second TTL so subsequent retries or starting Zero later can succeed
        mediaInfoCache[targetUrl] = { formats: [], _cachedAt: Date.now() };
      }
    });
  }

  // Create floating download panel
  function createPanel() {
    const isLiveSite = window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");
    const container = document.createElement("div");
    container.className = "zero-float-container";
    const mainIconSvg = isLiveSite
      ? `<svg viewBox="0 0 24 24" width="14" height="14" fill="#f87171"><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="9" stroke="#f87171" stroke-width="2" fill="none"/></svg>`
      : DOWNLOAD_ICON_SVG;
    const mainText = isLiveSite ? "Record Live Stream" : "Download this video";
    const barTitle = isLiveSite ? "Klik untuk merekam siaran langsung webcam ke MP4" : "Click to view available video qualities (1080p, 720p, 480p...)";

    container.innerHTML = `
      <div class="zero-float-bar">
        <span class="zero-float-drag" title="Drag to reposition">${DRAG_ICON_SVG}</span>
        <div class="zero-float-main-btn" title="${barTitle}">
          <span class="zero-float-icon">${mainIconSvg}</span>
          <span class="zero-float-text">${mainText}</span>
        </div>
        <div class="zero-float-dropdown-toggle" title="Select format / quality">▼</div>
        <div class="zero-float-close" title="Hide for this video">&times;</div>
      </div>
      <div class="zero-float-menu"></div>
    `;

    const bar = container.querySelector(".zero-float-bar");
    const mainBtn = container.querySelector(".zero-float-main-btn");
    const toggleBtn = container.querySelector(".zero-float-dropdown-toggle");
    const closeBtn = container.querySelector(".zero-float-close");

    // Isolate container from host webpage: prevent clicks and interactions from bubbling to host video player
    ["click", "dblclick", "mousedown", "mouseup", "pointerdown", "pointerup", "touchstart", "touchend", "contextmenu"].forEach((evtName) => {
      container.addEventListener(evtName, (e) => {
        e.stopPropagation();
      }, false);
    });

    // Primary action: Clicking "Download this video" / "Record Live Stream" directly triggers download to Zero!
    let lastDownloadTrigger = 0;
    const triggerDownload = (e) => {
      if (e) {
        e.stopPropagation();
        if (e.preventDefault) e.preventDefault();
      }
      const now = Date.now();
      if (now - lastDownloadTrigger < 600) return;
      lastDownloadTrigger = now;
      handlePrimaryDownload();
    };

    mainBtn.addEventListener("click", triggerDownload);
    mainBtn.addEventListener("pointerup", (e) => {
      if (e.button === 0) triggerDownload(e);
    });

    // Clicking dropdown arrow toggles quality selection menu
    let lastToggleTrigger = 0;
    const triggerToggle = (e) => {
      if (e) {
        e.stopPropagation();
        if (e.preventDefault) e.preventDefault();
      }
      const now = Date.now();
      if (now - lastToggleTrigger < 300) return;
      lastToggleTrigger = now;
      toggleMenu(container);
    };

    toggleBtn.addEventListener("click", triggerToggle);
    toggleBtn.addEventListener("pointerup", (e) => {
      if (e.button === 0) triggerToggle(e);
    });

    // Clicking bar background toggles menu
    bar.addEventListener("click", (e) => {
      if (e.target.closest(".zero-float-close") || e.target.closest(".zero-float-drag") || e.target.closest(".zero-float-main-btn") || e.target.closest(".zero-float-dropdown-toggle")) return;
      triggerToggle(e);
    });

    // Close button
    const triggerClose = (e) => {
      if (e) {
        e.stopPropagation();
        if (e.preventDefault) e.preventDefault();
      }
      isDismissedForCurrentUrl = true;
      hidePanel(container, true);
    };

    closeBtn.addEventListener("click", triggerClose);
    closeBtn.addEventListener("pointerup", (e) => {
      if (e.button === 0) triggerClose(e);
    });

    // Hover management
    container.addEventListener("mouseenter", () => {
      isHoveringPanel = true;
      clearTimeout(hideTimer);
      container.classList.add("zero-visible");
      // Pre-fetch formats on hover for zero-lag menu
      prefetchMediaInfo();
    });

    container.addEventListener("mouseleave", () => {
      isHoveringPanel = false;
      if (!isMenuOpen) {
        startHideTimer();
      }
    });

    makeDraggable(container);
    return container;
  }

  function handlePrimaryDownload() {
    const isLiveSite = window.location.hostname.includes("chaturbate.com") || window.location.hostname.includes("stripchat.com");
    const title = getVideoTitle();
    const targetUrl = getCleanTargetUrl();
    const cached = targetUrl ? mediaInfoCache[targetUrl] : null;

    if (activePanel) {
      showToast(activePanel, isLiveSite ? "Memulai perekaman di Zero..." : "Mengirim ke Zero Download Assistant...");
    }

    // 1. Check probed yt-dlp formats
    if (cached && cached.formats && cached.formats.length > 0) {
      const bestVideo = [...cached.formats].sort((a, b) => {
        if (a.has_video !== b.has_video) return a.has_video ? -1 : 1;
        if ((b.height || 0) !== (a.height || 0)) return (b.height || 0) - (a.height || 0);
        return (b.filesize || 0) - (a.filesize || 0);
      })[0];
      if (bestVideo) {
        triggerFormatDownload(bestVideo, title, targetUrl);
        return;
      }
    }

    // 2. Check valid sniffed streams (HLS, direct MP4)
    const validStreams = sniffedStreams.filter((s) => !isFragment(s.url) && !isAdOrJunkMedia(s.url, s.name, s));
    if (validStreams.length > 0) {
      const bestStream = [...validStreams].sort((a, b) => {
        const aH = a.height || 0;
        const bH = b.height || 0;
        if (bH !== aH) return bH - aH;
        return (b.bandwidth || 0) - (a.bandwidth || 0);
      })[0];
      if (bestStream) {
        triggerStreamDownload(bestStream, title, bestStream.name || "Video");
        return;
      }
    }

    // 3. Check active video direct source
    if (activeVideo && (activeVideo.currentSrc || activeVideo.src)) {
      const vSrc = activeVideo.currentSrc || activeVideo.src;
      if (vSrc && !vSrc.startsWith("blob:") && !isAdOrJunkMedia(vSrc)) {
        triggerStreamDownload({ url: vSrc, is_direct: true, is_live: isLiveSite }, title, "Video");
        return;
      }
    }

    // Check if video is DRM-protected (Encrypted Media Extensions / EME)
    const isDrmProtected = (activeVideo && !!activeVideo.mediaKeys) ||
                           window.location.hostname.includes("netflix.com") ||
                           window.location.hostname.includes("disneyplus.com") ||
                           window.location.hostname.includes("primevideo.com") ||
                           (window.location.hostname.includes("iq.com") && (!cached && validStreams.length === 0));

    if (isDrmProtected) {
      if (activePanel) {
        showToast(activePanel, "Video ini dilindungi enkripsi DRM (Widevine) dan tidak dapat diunduh.", 3500);
      }
      return;
    }

    // 4. Fallback: forward page URL to Zero desktop app to probe & record/download directly
    safeSendMessage({
      action: "DOWNLOAD_MEDIA",
      data: {
        url: targetUrl || window.location.href,
        pageUrl: window.location.href,
        title: title,
        is_live: isLiveSite,
        open_grabber: true
      }
    });
  }

  function makeDraggable(container) {
    const dragHandle = container.querySelector(".zero-float-drag");
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let initialLeft = 0;
    let initialTop = 0;

    dragHandle.addEventListener("mousedown", (e) => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = container.getBoundingClientRect();
      const parentRect = container.offsetParent ? container.offsetParent.getBoundingClientRect() : { left: 0, top: 0 };
      initialLeft = rect.left - parentRect.left;
      initialTop = rect.top - parentRect.top;
      e.preventDefault();
      e.stopPropagation();
    });

    window.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      container.style.left = `${initialLeft + dx}px`;
      container.style.top = `${initialTop + dy}px`;
      container.style.right = "auto";
    });

    window.addEventListener("mouseup", () => {
      if (isDragging) isDragging = false;
    });
  }

  function toggleMenu(container) {
    if (!container || !container.classList) return;
    const menu = container.querySelector(".zero-float-menu");
    if (!menu || !menu.classList) return;
    isMenuOpen = !isMenuOpen;
    if (isMenuOpen) {
      // Position menu: if near bottom of viewport, flip upwards to prevent clipping
      try {
        const rect = container.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        if (spaceBelow < 280 && rect.top > 250) {
          menu.style.top = "auto";
          menu.style.bottom = "calc(100% + 5px)";
        } else {
          menu.style.top = "calc(100% + 5px)";
          menu.style.bottom = "auto";
        }
      } catch (posErr) {}

      // Sync any streams captured by background service worker
      safeSendMessage({ action: "GET_TAB_STREAMS" }, (resp) => {
        if (resp && resp.streams && resp.streams.length > 0) {
          resp.streams.forEach((s) => {
            const uLower = (s.url || "").toLowerCase();
            const ext = (s.ext || "").toLowerCase();
            const isFrag = ext.includes("ts") || ext.includes("mp2t") || uLower.endsWith(".ts") || uLower.includes(".ts?") || uLower.includes("/segment");
            if (!isFrag && !isAdOrJunkMedia(s.url, s.name, s) && !sniffedStreams.some((existing) => existing.url === s.url)) {
              sniffedStreams.push(s);
            }
          });
          if (activePanel && isMenuOpen) {
            renderDropdownMenu(activePanel);
          }
        }
      });
      const tUrl = getCleanTargetUrl();
      if (tUrl && (!mediaInfoCache[tUrl] || !mediaInfoCache[tUrl].formats || mediaInfoCache[tUrl].formats.length === 0)) {
        prefetchMediaInfo(true);
      }
      renderDropdownMenu(container);
      menu.classList.add("zero-menu-open");
      container.classList.add("zero-visible");
    } else {
      menu.classList.remove("zero-menu-open");
    }
  }

  function renderDropdownMenu(container) {
    const menu = container.querySelector(".zero-float-menu");
    if (!menu) return;

    menu.innerHTML = "";
    const title = getVideoTitle();
    const targetUrl = getCleanTargetUrl();
    const cached = targetUrl ? mediaInfoCache[targetUrl] : null;

    const durationSec = (cached && cached.duration) || (activeVideo ? activeVideo.duration : 0) || 0;
    const durationStr = durationSec ? formatDuration(durationSec) : "";

    // Sleek Compact Header (Zero Soft Chrome)
    const header = document.createElement("div");
    header.className = "zero-float-menu-header";
    header.innerHTML = `
      <span class="zero-float-header-label">Download video from this page:</span>
      <span class="zero-float-header-meta">${durationStr ? `${CLOCK_ICON_SVG} ${durationStr}` : "Zero"}</span>
    `;
    menu.appendChild(header);

    // Video Title Banner
    const titleBanner = document.createElement("div");
    titleBanner.className = "zero-float-title-banner";
    titleBanner.title = title;
    titleBanner.innerHTML = `
      <span class="zero-float-title-icon">${FILM_ICON_SVG}</span>
      <span class="zero-float-title-text">${escapeHtml(title)}</span>
    `;
    menu.appendChild(titleBanner);

    const hasProbedFormats = cached && cached.formats && cached.formats.length > 0;
    const validStreams = sniffedStreams.filter((s) => !isFragment(s.url) && !isAdOrJunkMedia(s.url, s.name, s));

    if (hasProbedFormats) {
      // Sort: Video (higher resolution first, MP4 before WEBM), then Audio
      const displayFormats = [...cached.formats].sort((a, b) => {
        if (a.has_video !== b.has_video) return a.has_video ? -1 : 1;
        if ((b.height || 0) !== (a.height || 0)) return (b.height || 0) - (a.height || 0);
        const aExt = (a.ext || "").toLowerCase();
        const bExt = (b.ext || "").toLowerCase();
        if (aExt !== bExt) {
          if (aExt === "mp4") return -1;
          if (bExt === "mp4") return 1;
        }
        return (b.filesize || 0) - (a.filesize || 0);
      });

      displayFormats.forEach((fmt) => {
        const isAudio = !fmt.has_video && fmt.has_audio;
        const h = fmt.height || 0;

        let resLabel = "";
        let pillTag = "";

        if (isAudio) {
          resLabel = "Audio";
          pillTag = '<span class="zero-pill zero-pill-audio">HQ</span>';
        } else if (h >= 2160) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-4k">4K</span>';
        } else if (h >= 1440) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-2k">2K</span>';
        } else if (h >= 1080) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-fhd">FHD</span>';
        } else if (h >= 720) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-hd">HD</span>';
        } else if (h >= 480) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-sd">SD</span>';
        } else {
          resLabel = h ? `${h}p` : "Video";
          pillTag = '<span class="zero-pill zero-pill-sd">SD</span>';
        }

        const bitrateStr = (fmt.bitrate && fmt.bitrate > 0) ? formatBitrate(fmt.bitrate) : "";
        const sizeStr = fmt.filesize && fmt.filesize > 0 ? formatBytes(fmt.filesize) : "--";
        const extStr = (fmt.ext || (isAudio ? "m4a" : "mp4")).toUpperCase();

        const item = document.createElement("div");
        item.className = "zero-float-menu-item";
        item.innerHTML = `
          <div class="zero-float-item-left">
            <span class="zero-float-media-icon">${isAudio ? AUDIO_ICON_SVG : VIDEO_ICON_SVG}</span>
            <span class="zero-float-res-text">${resLabel}</span>
            ${pillTag}
          </div>
          <div class="zero-float-item-right">
            ${bitrateStr ? `<span class="zero-float-col zero-col-bitrate">${bitrateStr}</span>` : ""}
            <span class="zero-float-col zero-col-size">${sizeStr}</span>
            <span class="zero-float-col zero-col-ext">${extStr}</span>
          </div>
        `;

        item.addEventListener("click", (e) => {
          e.stopPropagation();
          if (menu && menu.classList) menu.classList.remove("zero-menu-open");
          isMenuOpen = false;
          triggerFormatDownload(fmt, title, targetUrl);
        });

        menu.appendChild(item);
      });
    } else if (validStreams.length > 0 && !IS_YOUTUBE) {
      // Sort sniffed streams: Highest resolution first, then highest bitrate/filesize
      const sortedStreams = [...validStreams].sort((a, b) => {
        const aH = a.height || 0;
        const bH = b.height || 0;
        if (bH !== aH) return bH - aH;
        const aBw = a.bandwidth || a.bitrate || 0;
        const bBw = b.bandwidth || b.bitrate || 0;
        if (bBw !== aBw) return bBw - aBw;
        return (b.filesize || b.size || 0) - (a.filesize || a.size || 0);
      });

      sortedStreams.forEach((s) => {
        let h = s.height || (activeVideo ? activeVideo.videoHeight : 0) || 0;
        let resLabel = "";
        let pillTag = "";

        if (h >= 2160) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-4k">4K</span>';
        } else if (h >= 1440) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-2k">2K</span>';
        } else if (h >= 1080) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-fhd">FHD</span>';
        } else if (h >= 720) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-hd">HD</span>';
        } else if (h >= 480) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-sd">SD</span>';
        } else if (h > 0) {
          resLabel = `${h}p`;
          pillTag = '<span class="zero-pill zero-pill-sd">SD</span>';
        } else {
          const uLower = (s.url || "").toLowerCase();
          if (uLower.includes("1080p")) { resLabel = "1080p"; pillTag = '<span class="zero-pill zero-pill-fhd">FHD</span>'; }
          else if (uLower.includes("720p")) { resLabel = "720p"; pillTag = '<span class="zero-pill zero-pill-hd">HD</span>'; }
          else if (uLower.includes("480p")) { resLabel = "480p"; pillTag = '<span class="zero-pill zero-pill-sd">SD</span>'; }
          else if (uLower.includes("360p")) { resLabel = "360p"; pillTag = '<span class="zero-pill zero-pill-sd">SD</span>'; }
          else {
            resLabel = s.name && !s.name.includes(".m3u8") ? s.name : "Full Video";
            pillTag = s.is_hls ? '<span class="zero-pill zero-pill-hls">HLS</span>' : '<span class="zero-pill zero-pill-hd">DIRECT</span>';
          }
        }

        // Bitrate calculation
        let bitrateKbps = s.bitrate || (s.bandwidth ? Math.round(s.bandwidth / 1000) : 0);
        if (!bitrateKbps && (s.filesize || s.size) > 0 && durationSec > 0) {
          bitrateKbps = Math.round(((s.filesize || s.size) * 8 / durationSec) / 1000);
        }
        const bitrateStr = (bitrateKbps && bitrateKbps > 0) ? formatBitrate(bitrateKbps) : "";

        // Size calculation
        let bytes = (s.filesize && s.filesize > 0) ? s.filesize : ((s.size && s.size > 0) ? s.size : 0);
        if (!bytes && bitrateKbps > 0 && durationSec > 0) {
          bytes = Math.round((bitrateKbps * 1000 * durationSec) / 8);
        }
        const sizeStr = bytes > 0 ? formatBytes(bytes) : (durationStr ? `${durationStr}` : "Auto MP4");
        const extStr = (s.ext || "mp4").toUpperCase();

        const item = document.createElement("div");
        item.className = "zero-float-menu-item";
        item.innerHTML = `
          <div class="zero-float-item-left">
            <span class="zero-float-media-icon">${VIDEO_ICON_SVG}</span>
            <span class="zero-float-res-text" title="${resLabel}">${resLabel}</span>
            ${pillTag}
          </div>
          <div class="zero-float-item-right">
            ${bitrateStr ? `<span class="zero-float-col zero-col-bitrate">${bitrateStr}</span>` : ""}
            <span class="zero-float-col zero-col-size">${sizeStr}</span>
            <span class="zero-float-col zero-col-ext">${extStr}</span>
          </div>
        `;

        item.addEventListener("click", (e) => {
          e.stopPropagation();
          if (menu && menu.classList) menu.classList.remove("zero-menu-open");
          isMenuOpen = false;
          triggerStreamDownload(s, title, resLabel);
        });

        menu.appendChild(item);
      });

      // Footer Actions
      const divider = document.createElement("div");
      divider.className = "zero-float-menu-divider";
      menu.appendChild(divider);

      const downloadAllItem = document.createElement("div");
      downloadAllItem.className = "zero-float-menu-footer-item";
      downloadAllItem.innerHTML = `
        <span class="zero-float-footer-icon">${DOWNLOAD_TRAY_SVG}</span>
        <span class="zero-float-footer-text">Download all video links from this page</span>
      `;
      downloadAllItem.addEventListener("click", (e) => {
        e.stopPropagation();
        if (menu && menu.classList) menu.classList.remove("zero-menu-open");
        isMenuOpen = false;
        if (sortedStreams.length > 0) {
          triggerStreamDownload(sortedStreams[0], title, sortedStreams[0].name || "Video");
        }
      });
      menu.appendChild(downloadAllItem);

      const optionsItem = document.createElement("div");
      optionsItem.className = "zero-float-menu-footer-item";
      optionsItem.innerHTML = `
        <span class="zero-float-footer-icon">${GEAR_ICON_SVG}</span>
        <span class="zero-float-footer-text">Video Panel Options...</span>
      `;
      optionsItem.addEventListener("click", (e) => {
        e.stopPropagation();
        if (menu && menu.classList) menu.classList.remove("zero-menu-open");
        isMenuOpen = false;
        safeSendMessage({ action: "OPEN_OPTIONS" });
      });
      menu.appendChild(optionsItem);
    } else if (isFetchingFormats) {
      const loading = document.createElement("div");
      loading.className = "zero-float-menu-loading";
      loading.innerHTML = `
        <div class="zero-float-spinner"></div>
        <span>Memuat daftar resolusi...</span>
      `;
      menu.appendChild(loading);
    } else if (activeVideo && (activeVideo.currentSrc || activeVideo.duration > 0)) {
      const currentSrc = activeVideo.currentSrc || activeVideo.src;
      if (currentSrc && !currentSrc.startsWith("blob:")) {
        handleStreamDetected({
          url: currentSrc,
          height: activeVideo.videoHeight || 720,
          duration: activeVideo.duration,
          ext: "mp4",
          is_direct: true
        });
      }
      const loadingNote = document.createElement("div");
      loadingNote.className = "zero-float-menu-loading";
      loadingNote.innerHTML = `
        <div class="zero-float-spinner"></div>
        <span>Mendeteksi stream video...</span>
      `;
      menu.appendChild(loadingNote);
    } else {
      const isDrmProtected = (activeVideo && !!activeVideo.mediaKeys) ||
                             window.location.hostname.includes("netflix.com") ||
                             window.location.hostname.includes("disneyplus.com") ||
                             window.location.hostname.includes("primevideo.com") ||
                             (window.location.hostname.includes("iq.com") && validStreams.length === 0);

      if (isDrmProtected) {
        const drmNote = document.createElement("div");
        drmNote.className = "zero-float-menu-item";
        drmNote.style.cssText = "padding: 10px 14px; margin: 6px 8px; border-radius: 6px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12); color: #cbd5e1; font-size: 11px; line-height: 1.4; text-align: center;";
        drmNote.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;gap:6px;font-weight:600;margin-bottom:3px;">${LOCK_ICON_SVG} Dilindungi DRM (Widevine)</div><span style="color: #94a3b8; font-size: 10px;">Video ini dienkripsi hak cipta dan tidak dapat diunduh langsung.</span>`;
        menu.appendChild(drmNote);
        return;
      }

      const emptyNote = document.createElement("div");
      emptyNote.className = "zero-float-menu-loading";
      emptyNote.style.color = "#94a3b8";
      emptyNote.innerHTML = `<span>Putar video untuk mendeteksi stream...</span>`;
      menu.appendChild(emptyNote);

      const directAction = document.createElement("div");
      directAction.className = "zero-float-menu-item";
      directAction.style.cssText = "padding: 8px 12px; margin: 4px 8px; border-radius: 5px; background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.16); color: #f1f5f9; font-weight: 600; text-align: center; cursor: pointer;";
      directAction.innerHTML = `Unduh Video Ini Sekarang (Krolix)`;
      directAction.addEventListener("click", (e) => {
        e.stopPropagation();
        if (menu && menu.classList) menu.classList.remove("zero-menu-open");
        isMenuOpen = false;
        handlePrimaryDownload();
      });
      menu.appendChild(directAction);
    }
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return "--";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function formatBitrate(kbps) {
    if (!kbps || kbps <= 0) return "--";
    if (kbps >= 1000) {
      return (kbps / 1000).toFixed(1) + " Mbps";
    }
    return Math.round(kbps) + " kbps";
  }

  function formatDuration(sec) {
    if (!sec || sec <= 0) return "--:--";
    const totalSec = Math.floor(sec);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = Math.floor(totalSec % 60);
    if (h > 0) {
      return `${h}:${m < 10 ? "0" : ""}${m}:${s < 10 ? "0" : ""}${s}`;
    }
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  }

  // Trigger download for a selected format
  function triggerFormatDownload(fmt, title, targetUrl) {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    if (activePanel) {
      showToast(activePanel, "Membuka Krolix...");
    }

    const cleanTitle = title.replace(/[\\/*?:"<>|]/g, "_");
    const ext = fmt.ext || (fmt.has_video ? "mp4" : "m4a");
    const filename = `${cleanTitle} (${fmt.label}).${ext}`;

    safeSendMessage({
      action: "DOWNLOAD_MEDIA",
      data: {
        url: fmt.url,
        pageUrl: window.location.href,
        filename: filename,
        filesize: fmt.filesize || -1,
        title: cleanTitle,
        companion_audio: fmt.companion_audio || null,
        format_id: fmt.format_id || "",
        is_media: true
      }
    }, (response) => {
      if (!isExtensionValid()) return;
      if (response && response.success === false) {
        if (activePanel) {
          showToast(activePanel, "Pastikan Krolix terpasang di PC", true);
        }
      }
    });
  }

  function triggerDirectDownload(directUrl, filename, filesize) {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    if (activePanel) {
      showToast(activePanel, "Membuka Krolix...");
    }

    safeSendMessage({
      action: "DOWNLOAD_MEDIA",
      data: {
        url: directUrl,
        pageUrl: window.location.href,
        filename: filename,
        filesize: filesize || -1,
        title: filename,
        is_media: true
      }
    }, (response) => {
      if (!isExtensionValid()) return;
      if (response && response.success === false) {
        if (activePanel) {
          showToast(activePanel, "Pastikan Krolix terpasang di PC", true);
        }
      }
    });
  }

  function triggerStreamDownload(stream, title, label) {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    const isLive = !!(
      stream.is_live ||
      window.location.hostname.includes("chaturbate.com") ||
      window.location.hostname.includes("stripchat.com")
    );

    if (activePanel) {
      showToast(activePanel, isLive ? "Memulai perekaman di Krolix..." : "Membuka Krolix...");
    }

    const cleanTitle = (title || (isLive ? "Live Stream" : "Video")).replace(/[\\/*?:"<>|]/g, "_").trim();
    const isHls = !!(isLive || stream.is_hls || stream.ext === "m3u8" || (stream.url && stream.url.toLowerCase().includes(".m3u8")));
    
    let filename = "";
    if (stream.name) {
      const baseName = stream.name.replace(/\.[a-zA-Z0-9]+$/, "");
      filename = `${cleanTitle} [${baseName}].mp4`;
    } else if (label && !label.includes("Stream #")) {
      filename = `${cleanTitle} (${label}).mp4`;
    } else {
      filename = `${cleanTitle}.mp4`;
    }

    // Collect fallback variant URLs from streams detected on this page
    const fallbackUrls = [];
    if (typeof detectedStreams !== "undefined" && detectedStreams && detectedStreams.size > 0) {
      for (const st of detectedStreams.values()) {
        if (st && st.url && st.url !== stream.url && (st.is_hls || (st.url && st.url.includes(".m3u8")))) {
          fallbackUrls.push(st.url);
        }
      }
    }

    const streamVariants = (typeof sniffedStreams !== "undefined" && sniffedStreams)
      ? sniffedStreams.filter((s) => s.is_hls || (s.url && s.url.includes(".m3u8")))
      : [];

    safeSendMessage({
      action: "DOWNLOAD_MEDIA",
      data: {
        url: stream.url,
        masterUrl: stream.masterUrl || "",
        fallbackUrls: fallbackUrls,
        pageUrl: window.location.href,
        referer: window.location.href,
        filename: filename,
        filesize: (stream.filesize && stream.filesize > 0) ? stream.filesize : (stream.size && stream.size > 0 ? stream.size : -1),
        height: stream.height || 0,
        width: stream.width || 0,
        resolution: stream.resolution || (stream.height ? `${stream.height}p` : ""),
        bitrate: stream.bitrate || (stream.bandwidth ? Math.round(stream.bandwidth / 1000) : 0),
        bandwidth: stream.bandwidth || 0,
        duration: stream.duration || 0,
        title: cleanTitle,
        is_media: true,
        is_hls: isHls,
        is_live: isLive,
        variants: streamVariants,
        requestHeaders: stream.requestHeaders || null
      }
    }, (response) => {
      if (!isExtensionValid()) return;
      if (response && response.success === false) {
        if (activePanel) {
          showToast(activePanel, "Pastikan Krolix terpasang di PC", true);
        }
      }
    });
  }

  function showToast(container, text, isError = false) {
    const existing = container.querySelector(".zero-float-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "zero-float-toast";
    if (isError) {
      toast.style.borderColor = "rgba(239, 68, 68, 0.4)";
      toast.style.color = "#fca5a5";
    }
    toast.innerText = text;
    container.appendChild(toast);

    setTimeout(() => {
      toast.remove();
    }, 2400);
  }

  function isFullscreen() {
    return !!(
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.mozFullScreenElement ||
      document.msFullscreenElement
    );
  }

  function showPanel(container) {
    if (isDismissedForCurrentUrl || isFullscreen() || document.hidden || !container || !container.classList) return;
    container.classList.add("zero-visible");
    startHideTimer();
  }

  function hidePanel(container, immediate = false) {
    if ((isHoveringPanel || isMenuOpen) && !immediate && !isFullscreen() && !document.hidden) return;
    if (container && container.classList) {
      container.classList.remove("zero-visible");
    }
  }

  document.addEventListener("fullscreenchange", () => {
    if (isFullscreen() && activePanel) {
      hidePanel(activePanel, true);
    }
  });
  document.addEventListener("webkitfullscreenchange", () => {
    if (isFullscreen() && activePanel) {
      hidePanel(activePanel, true);
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && activePanel) {
      hidePanel(activePanel, true);
    }
  });
  window.addEventListener("blur", () => {
    if (activePanel) {
      isMenuOpen = false;
      const menu = activePanel.querySelector(".zero-float-menu");
      if (menu) menu.style.display = "none";
      hidePanel(activePanel, true);
    }
  });

  function startHideTimer() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (activePanel && !isHoveringPanel && !isMenuOpen) {
        hidePanel(activePanel);
      }
    }, 6000);
  }

  function attachPanelToVideo(video, autoShow = true) {
    if (!video || !video.isConnected) return;
    if (isAdVideoElement(video)) return;
    activeVideo = video;

    if (!activePanel) {
      activePanel = createPanel();
    }
    if (!activePanel) return;

    if (IS_YOUTUBE) {
      const ytPlayer = document.querySelector("#movie_player") ||
                       document.querySelector(".html5-video-player") ||
                       video.closest(".html5-video-player");

      if (ytPlayer && activePanel.parentNode !== ytPlayer) {
        ytPlayer.appendChild(activePanel);
        activePanel.style.top = "16px";
        activePanel.style.right = "16px";
        activePanel.style.left = "auto";

        if (!ytPlayer.__zero_attached) {
          ytPlayer.__zero_attached = true;
          ytPlayer.addEventListener("mousemove", () => {
            if (activePanel) showPanel(activePanel);
          });
          ytPlayer.addEventListener("mouseenter", () => {
            if (activePanel) {
              showPanel(activePanel);
              prefetchMediaInfo();
            }
          });
          ytPlayer.addEventListener("mouseleave", () => {
            if (activePanel && !isHoveringPanel && !isMenuOpen) {
              hidePanel(activePanel);
            }
          });
        }
      }
    } else {
      const parent = video.parentElement;
      if (parent && activePanel.parentNode !== parent) {
        const computed = window.getComputedStyle(parent);
        if (computed.position === "static") {
          parent.style.position = "relative";
        }
        parent.appendChild(activePanel);
        activePanel.style.top = "12px";
        activePanel.style.right = "12px";
        activePanel.style.left = "auto";

        if (!parent.__zero_attached) {
          parent.__zero_attached = true;
          parent.addEventListener("mousemove", () => {
            if (activePanel) showPanel(activePanel);
          });
          parent.addEventListener("mouseenter", () => {
            if (activePanel) showPanel(activePanel);
          });
          parent.addEventListener("mouseleave", () => {
            if (activePanel && !isHoveringPanel && !isMenuOpen) {
              hidePanel(activePanel);
            }
          });
        }
      }
    }

    if (!video.__zero_attached) {
      video.__zero_attached = true;
      const onVideoActive = () => {
        if (activePanel) {
          showPanel(activePanel);
          prefetchMediaInfo();
        }
      };
      ["play", "playing", "canplay", "loadeddata", "loadedmetadata"].forEach((evt) => {
        video.addEventListener(evt, onVideoActive);
      });
      video.addEventListener("mousemove", onVideoActive);
    }

    // Faster Automatic Video Detection: Immediately display the floating widget above the player!
    if (autoShow && activePanel) {
      showPanel(activePanel);
      prefetchMediaInfo();
    }
  }

  function scanPerformanceEntries() {
    try {
      if (typeof performance === "undefined" || !performance.getEntriesByType) return;
      const entries = performance.getEntriesByType("resource");
      for (const entry of entries) {
        const name = entry.name;
        if (!name || isFragment(name)) continue;

        const uLower = name.toLowerCase();
        const cleanPath = uLower.split("?")[0].split("#")[0];
        const isHls = cleanPath.endsWith(".m3u8") || uLower.includes(".m3u8");
        const isDash = cleanPath.endsWith(".mpd") || uLower.includes(".mpd");
        const isDirect = cleanPath.endsWith(".mp4") ||
                         cleanPath.endsWith(".webm") ||
                         cleanPath.endsWith(".mkv") ||
                         cleanPath.endsWith(".mov") ||
                         cleanPath.endsWith(".flv");

        if (isHls || isDash || isDirect) {
          if (!isFragment(name) && !isAdOrJunkMedia(name)) {
            const pathSegs = cleanPath.split("/");
            const lastSeg = pathSegs[pathSegs.length - 1] || "video";
            const bytes = entry.encodedBodySize || entry.transferSize || -1;

            handleStreamDetected({
              url: name,
              name: decodeURIComponent(lastSeg),
              ext: isHls ? "m3u8" : (isDash ? "mpd" : "mp4"),
              is_hls: isHls,
              is_dash: isDash,
              is_stream: isHls || isDash,
              filesize: bytes > 65536 ? bytes : -1
            });
          }
        }
      }
    } catch (e) {}
  }

  function scanForVideos() {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      isDismissedForCurrentUrl = false;
      sniffedStreams.length = 0;
      prefetchMediaInfo();
    }

    scanPerformanceEntries();

    if (activeVideo && isAdVideoElement(activeVideo)) {
      if (activePanel) hidePanel(activePanel, true);
    }

    const videos = document.querySelectorAll("video");
    for (const v of videos) {
      if (isAdVideoElement(v)) continue;
      const vSrc = v.currentSrc || v.src;
      if (vSrc && !vSrc.startsWith("blob:") && !vSrc.startsWith("data:") && !isAdOrJunkMedia(vSrc)) {
        const uLower = vSrc.toLowerCase();
        const cleanPath = uLower.split("?")[0].split("#")[0];
        const isHls = cleanPath.endsWith(".m3u8") || uLower.includes(".m3u8");
        const isDash = cleanPath.endsWith(".mpd") || uLower.includes(".mpd");
        const isDirect = cleanPath.endsWith(".mp4") || cleanPath.endsWith(".webm") || cleanPath.endsWith(".mkv");

        if (isHls || isDash || isDirect) {
          const pathSegs = cleanPath.split("/");
          const lastSeg = pathSegs[pathSegs.length - 1] || "video";
          handleStreamDetected({
            url: vSrc,
            name: decodeURIComponent(lastSeg),
            ext: isHls ? "m3u8" : (isDash ? "mpd" : "mp4"),
            height: v.videoHeight || 0,
            duration: v.duration || 0,
            is_hls: isHls,
            is_dash: isDash,
            is_stream: isHls || isDash
          });
        }
      }

      // Also inspect child <source> elements
      const sources = v.querySelectorAll("source");
      for (const s of sources) {
        const sSrc = s.src;
        if (sSrc && !sSrc.startsWith("blob:") && !sSrc.startsWith("data:") && !isAdOrJunkMedia(sSrc)) {
          handleStreamDetected({
            url: sSrc,
            height: v.videoHeight || 0,
            duration: v.duration || 0,
            ext: "mp4"
          });
        }
      }

      if (v.offsetWidth >= 160 && v.offsetHeight >= 90) {
        if (!isAdVideoElement(v)) {
          observeVideoElement(v);
          attachPanelToVideo(v, true);
          return;
        }
      }
    }
  }

  let videoIntersectionObserver = null;
  function observeVideoElement(v) {
    if (!v) return;
    if (!videoIntersectionObserver && typeof IntersectionObserver !== "undefined") {
      try {
        videoIntersectionObserver = new IntersectionObserver((entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting && entry.intersectionRatio >= 0.15) {
              const targetVid = entry.target;
              if (!isAdVideoElement(targetVid) && targetVid.offsetWidth >= 160 && targetVid.offsetHeight >= 90) {
                attachPanelToVideo(targetVid, true);
              }
            }
          });
        }, { threshold: [0.15, 0.4] });
      } catch (e) {}
    }
    if (videoIntersectionObserver) {
      try {
        videoIntersectionObserver.observe(v);
      } catch (e) {}
    }
  }

  scanInterval = setInterval(scanForVideos, 1200);
  scanForVideos();

  // YouTube SPA navigation events
  window.addEventListener("yt-navigate-finish", () => {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    isDismissedForCurrentUrl = false;
    sniffedStreams.length = 0;
    setTimeout(() => {
      if (!isExtensionValid()) { cleanupOrphanedScript(); return; }
      scanForVideos();
      prefetchMediaInfo();
    }, 500);
  });
  window.addEventListener("yt-page-data-updated", () => {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    setTimeout(() => {
      if (!isExtensionValid()) { cleanupOrphanedScript(); return; }
      scanForVideos();
    }, 500);
  });
  window.addEventListener("popstate", () => {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    isDismissedForCurrentUrl = false;
    setTimeout(() => {
      if (!isExtensionValid()) { cleanupOrphanedScript(); return; }
      scanForVideos();
    }, 500);
  });

  observer = new MutationObserver(() => {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    scanForVideos();
  });
  try {
    observer.observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}

  // Close dropdown menu when clicking outside
  window.addEventListener("click", (e) => {
    if (!isExtensionValid()) {
      cleanupOrphanedScript();
      return;
    }
    if (activePanel && isMenuOpen && !activePanel.contains(e.target)) {
      const menu = activePanel.querySelector(".zero-float-menu");
      if (menu && menu.classList) menu.classList.remove("zero-menu-open");
      isMenuOpen = false;
    }
  });

  // Message listener for background events like "Download all links with Zero"
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!isExtensionValid()) return false;
    if (message && message.type === "EXTRACT_PAGE_LINKS") {
      try {
        const seen = new Set();
        const items = [];

        // 1. Scan <a> links
        const anchors = document.querySelectorAll("a[href]");
        for (const a of anchors) {
          const href = a.getAttribute("href");
          if (!href) continue;
          if (href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:") || href.startsWith("#")) continue;

          let absUrl;
          try {
            absUrl = new URL(href, document.baseURI).href;
          } catch {
            continue;
          }

          if (absUrl.startsWith("http://") || absUrl.startsWith("https://") || absUrl.startsWith("ftp://") || absUrl.startsWith("magnet:")) {
            if (!seen.has(absUrl)) {
              seen.add(absUrl);
              const text = (a.innerText || a.textContent || a.title || a.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ");
              items.push({
                url: absUrl,
                description: text,
                cookies: document.cookie || ""
              });
            }
          }
        }

        // 2. Scan media (<video>, <audio>, <source>, <img>)
        const mediaNodes = document.querySelectorAll("video[src], audio[src], source[src], img[src]");
        for (const el of mediaNodes) {
          const src = el.getAttribute("src");
          if (!src || src.startsWith("data:") || src.startsWith("blob:")) continue;
          let absUrl;
          try {
            absUrl = new URL(src, document.baseURI).href;
          } catch {
            continue;
          }
          if ((absUrl.startsWith("http://") || absUrl.startsWith("https://")) && !seen.has(absUrl)) {
            if (isAdOrJunkMedia(absUrl)) continue;
            seen.add(absUrl);
            const desc = (el.getAttribute("alt") || el.getAttribute("title") || "").trim();
            items.push({
              url: absUrl,
              description: desc,
              cookies: document.cookie || ""
            });
          }
        }

        sendResponse({ items: items });
      } catch (err) {
        console.error("[Krolix Extension] Error extracting page links:", err);
        sendResponse({ items: [] });
      }
      return true;
    }
  });

})();
