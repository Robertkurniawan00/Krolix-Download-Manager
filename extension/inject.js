/**
 * Zero Download Assistant - In-Page Stream Sniffer (MAIN World)
 * Hooks window.fetch, XMLHttpRequest, Hls.prototype, and HTMLMediaElement
 * to catch HLS (.m3u8), DASH (.mpd), and Direct Media directly in the webpage context.
 * Performs #EXTM3U payload sniffing for 100% detection regardless of URL obfuscation.
 * Strictly filters out video ads, ad network manifests, VAST/VPAID payloads, and blurred previews.
 */

(function () {
  if (window.__zero_sniffer_hooked) return;
  window.__zero_sniffer_hooked = true;

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

  function isAdIframe() {
    try {
      if (window === window.top) return false;
      const host = (window.location.hostname || "").toLowerCase();
      const href = (window.location.href || "").toLowerCase();

      // Check if iframe location itself matches ad domains
      if (AD_DOMAINS_AND_SERVERS.some((ad) => host.includes(ad) || href.includes(ad))) {
        return true;
      }
      if (AD_URL_REGEX.test(href) || AD_PATH_REGEX.test(href) || AD_QUERY_PARAM_REGEX.test(href)) {
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

  // If this script is running inside a third-party ad iframe, do NOT hook or sniff anything!
  if (isAdIframe()) return;

  function isAdPayloadText(text) {
    if (!text || typeof text !== "string") return false;
    const t = text.slice(0, 5000).toLowerCase();
    // VAST XML signatures
    if (
      t.includes("<vast") ||
      t.includes("<inline") ||
      t.includes("<adsystem") ||
      (t.includes("<ad ") && t.includes("<mediafile")) ||
      t.includes("<videoclicks") ||
      t.includes("<vpaid")
    ) {
      return true;
    }
    // Video Ad JSON / VAST JSON signatures
    if (
      t.includes('"adbreak"') ||
      t.includes('"vasturl"') ||
      t.includes('"adunits"') ||
      t.includes('"ad_video_url"') ||
      t.includes('"ad_tag"') ||
      t.includes('"video_ads"') ||
      t.includes('"companionads"')
    ) {
      return true;
    }
    return false;
  }

  function isAdOrJunkMedia(url, name, payload) {
    if (!url) return false;
    const u = (url || "").toLowerCase();
    const n = (name || "").toLowerCase();
    const full = u + " " + n;

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
    if (typeof window !== "undefined" && window.location && window.location.hostname.includes("youtube.com")) {
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
    const isYouTube = window.location.hostname.includes("youtube.com");
    if (isYouTube) {
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
      clean.endsWith("init.mp4") ||
      clean.endsWith("header.mp4")
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

  const capturedUrls = new Set();

  function extractUrlsFromText(text) {
    if (!text || typeof text !== "string") return;
    if (isAdPayloadText(text)) return; // DO NOT EXTRACT AD / VAST URLS!
    const cleanText = text.replace(/\\u0026/g, "&").replace(/\\\//g, "/");

    // Match direct m3u8, mpd, or /hls/ stream URLs
    const matches = cleanText.match(/https?:\/\/[^\s"'<>\\]+?(?:\.m3u8|\.mpd|\/hls\/|\.m3u)[^\s"'<>\\]*/gi);
    if (matches) {
      for (const m of matches) {
        if (!isAdOrJunkMedia(m)) {
          checkUrl(m);
        }
      }
    }

    // Check JSON keys for HLS stream URLs (e.g. Chaturbate, Stripchat, Cam sites, Vimeo)
    const keyMatches = cleanText.match(/"(?:hls_source|stream_url|hlsUrl|url|manifestUrl|source)"\s*:\s*"(https?:\/\/[^"]+)"/gi);
    if (keyMatches) {
      for (const km of keyMatches) {
        const valMatch = km.match(/"(https?:\/\/[^"]+)"$/);
        if (valMatch && valMatch[1] && !isAdOrJunkMedia(valMatch[1])) {
          checkUrl(valMatch[1]);
        }
      }
    }
  }

  function emitMediaDetected(url, details = {}) {
    if (!url || typeof url !== "string") return;
    if (url.startsWith("blob:") || url.startsWith("data:")) return;
    if (isAdOrJunkMedia(url, details.name || "", details)) return;
    if (isFragment(url)) return;

    // Allow re-emitting if details now includes m3u8Content that wasn't sent before
    if (capturedUrls.has(url) && !details.m3u8Content) return;

    capturedUrls.add(url);
    if (capturedUrls.size > 200) {
      const first = capturedUrls.values().next().value;
      capturedUrls.delete(first);
    }

    try {
      window.dispatchEvent(
        new CustomEvent("__zero_media_detected__", {
          detail: {
            url: url,
            mime: details.mime || "",
            type: details.type || "unknown",
            filesize: details.filesize || -1,
            m3u8Content: details.m3u8Content || ""
          }
        })
      );
    } catch (e) {}
  }

  function checkUrl(url, mime = "", contentLength = -1) {
    if (!url || typeof url !== "string") return;
    if (isAdOrJunkMedia(url)) return;
    if (isFragment(url)) return;

    const uLower = url.toLowerCase();
    const cleanPath = uLower.split("?")[0].split("#")[0];
    const mimeLower = (mime || "").toLowerCase();

    const isHls =
      cleanPath.endsWith(".m3u8") ||
      cleanPath.endsWith(".m3u") ||
      uLower.includes(".m3u8") ||
      uLower.includes("/hls/") ||
      uLower.includes("playlist.m3u8") ||
      uLower.includes("master.m3u8") ||
      uLower.includes("format=hls") ||
      uLower.includes("output=m3u8") ||
      mimeLower.includes("mpegurl") ||
      mimeLower.includes("application/x-mpegurl") ||
      mimeLower.includes("application/vnd.apple.mpegurl");

    const isDash =
      cleanPath.endsWith(".mpd") ||
      uLower.includes(".mpd") ||
      mimeLower.includes("dash+xml");

    const isDirect =
      cleanPath.endsWith(".mp4") ||
      cleanPath.endsWith(".webm") ||
      cleanPath.endsWith(".mkv") ||
      cleanPath.endsWith(".mov") ||
      cleanPath.endsWith(".flv") ||
      cleanPath.endsWith(".m4v") ||
      mimeLower.startsWith("video/");

    if (isHls) {
      emitMediaDetected(url, { type: "hls", mime: mime || "application/vnd.apple.mpegurl" });
    } else if (isDash) {
      emitMediaDetected(url, { type: "dash", mime: mime || "application/dash+xml" });
    } else if (isDirect) {
      // Filter out small video chunks (< 3MB) to prevent flooding with fMP4 segments
      if (contentLength > 0 && contentLength < 3145728) {
        return;
      }
      // Check if page has an active blob video (MediaSource); if so, ignore direct chunks < 10MB
      try {
        const hasBlobVideo = !!document.querySelector("video[src^='blob:']");
        if (hasBlobVideo && (contentLength <= 0 || contentLength < 10485760)) {
          return;
        }
      } catch (e) {}

      emitMediaDetected(url, { type: "direct", mime: mime || "video/mp4", filesize: contentLength });
    }
  }

  // 1. Hook window.fetch
  if (typeof window.fetch === "function") {
    const origFetch = window.fetch;
    window.fetch = async function (...args) {
      try {
        const input = args[0];
        let reqUrl = "";
        if (typeof input === "string") {
          reqUrl = input;
        } else if (input instanceof URL) {
          reqUrl = input.href;
        } else if (input && typeof input.url === "string") {
          reqUrl = input.url;
        }

        // Fast URL pre-check (blocks known ad domains/patterns immediately)
        if (reqUrl && !isAdOrJunkMedia(reqUrl)) {
          checkUrl(reqUrl);
        }
      } catch (preErr) {}

      const response = await origFetch.apply(this, args);

      // Header check on response & body sniffing for #EXTM3U or manifest URLs
      try {
        const input = args[0];
        const reqUrl = (typeof input === "string") ? input : (input instanceof URL ? input.href : (input && typeof input.url === "string" ? input.url : ""));
        const respUrl = response.url || reqUrl;
        if (respUrl && !isAdOrJunkMedia(respUrl) && !isFragment(respUrl)) {
          const ct = (response.headers.get("content-type") || "").toLowerCase();
          const cl = parseInt(response.headers.get("content-length") || "-1", 10);
          checkUrl(respUrl, ct, cl);

          // Sniff response payload if textual, stream, or reasonable length
          const isTextual =
            ct.includes("json") ||
            ct.includes("javascript") ||
            ct.includes("mpegurl") ||
            ct.includes("text") ||
            ct.includes("octet-stream") ||
            respUrl.includes("ajax") ||
            respUrl.includes("get_edge") ||
            !ct;

          if (isTextual && (cl <= 0 || cl < 2097152)) {
            response.clone().text().then((txt) => {
              if (!txt) return;
              if (isAdPayloadText(txt)) return; // Strictly ignore VAST & ad payloads!
              const trimmed = txt.trimStart();
              if (trimmed.startsWith("#EXTM3U")) {
                if (!isAdOrJunkMedia(respUrl)) {
                  emitMediaDetected(respUrl, { type: "hls", mime: "application/vnd.apple.mpegurl", m3u8Content: txt });
                }
              } else if (trimmed.startsWith("<?xml") && trimmed.includes("<MPD")) {
                if (!isAdOrJunkMedia(respUrl)) {
                  emitMediaDetected(respUrl, { type: "dash", mime: "application/dash+xml" });
                }
              } else {
                extractUrlsFromText(txt);
              }
            }).catch(() => {});
          }
        }
      } catch (hErr) {}

      return response;
    };
  }

  // 2. Hook XMLHttpRequest
  if (typeof window.XMLHttpRequest === "function") {
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      try {
        this.__zero_url = (typeof url === "string") ? url : "";
        if (this.__zero_url && !isAdOrJunkMedia(this.__zero_url)) {
          checkUrl(this.__zero_url);
        }
      } catch (e) {}
      return origOpen.apply(this, [method, url, ...rest]);
    };

    XMLHttpRequest.prototype.send = function (...args) {
      try {
        this.addEventListener("load", function () {
          try {
            const u = this.responseURL || this.__zero_url;
            if (u && !isAdOrJunkMedia(u) && !isFragment(u)) {
              const ct = (this.getResponseHeader("content-type") || "").toLowerCase();
              const cl = parseInt(this.getResponseHeader("content-length") || "-1", 10);
              checkUrl(u, ct, cl);

              if (typeof this.responseText === "string") {
                const txt = this.responseText;
                if (isAdPayloadText(txt)) return; // Strictly ignore VAST & ad payloads!
                const trimmed = txt.trimStart();
                if (trimmed.startsWith("#EXTM3U")) {
                  if (!isAdOrJunkMedia(u)) {
                    emitMediaDetected(u, { type: "hls", mime: "application/vnd.apple.mpegurl", m3u8Content: txt });
                  }
                } else if (trimmed.startsWith("<?xml") && trimmed.includes("<MPD")) {
                  if (!isAdOrJunkMedia(u)) {
                    emitMediaDetected(u, { type: "dash", mime: "application/dash+xml" });
                  }
                } else if (ct.includes("json") || ct.includes("javascript") || u.includes("ajax") || u.includes("get_edge")) {
                  extractUrlsFromText(txt);
                }
              }
            }
          } catch (e) {}
        });
      } catch (e) {}
      return origSend.apply(this, args);
    };
  }

  // 3. Hook Hls.js prototype loadSource
  function hookHls() {
    try {
      if (window.Hls && window.Hls.prototype && !window.Hls.prototype.__zero_hooked) {
        window.Hls.prototype.__zero_hooked = true;
        const origLoadSource = window.Hls.prototype.loadSource;
        window.Hls.prototype.loadSource = function (sourceUrl) {
          if (sourceUrl && typeof sourceUrl === "string" && !isAdOrJunkMedia(sourceUrl)) {
            checkUrl(sourceUrl, "application/vnd.apple.mpegurl");
          }
          return origLoadSource.apply(this, arguments);
        };
      }
    } catch (e) {}
  }
  hookHls();
  setInterval(hookHls, 1500);

  // 4. Hook HTMLMediaElement.prototype.src and setAttribute
  try {
    const origSrcDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "src");
    if (origSrcDesc && origSrcDesc.set && !HTMLMediaElement.prototype.__zero_src_hooked) {
      HTMLMediaElement.prototype.__zero_src_hooked = true;
      const origSet = origSrcDesc.set;
      Object.defineProperty(HTMLMediaElement.prototype, "src", {
        set: function (val) {
          if (typeof val === "string" && !val.startsWith("blob:") && !val.startsWith("data:")) {
            if (!isAdVideoElement(this) && !isAdOrJunkMedia(val)) {
              checkUrl(val);
            }
          }
          return origSet.call(this, val);
        },
        get: origSrcDesc.get,
        configurable: true
      });
    }

    const origSetAttr = HTMLMediaElement.prototype.setAttribute;
    HTMLMediaElement.prototype.setAttribute = function (name, val) {
      if (name && name.toLowerCase() === "src" && typeof val === "string" && !val.startsWith("blob:") && !val.startsWith("data:")) {
        if (!isAdVideoElement(this) && !isAdOrJunkMedia(val)) {
          checkUrl(val);
        }
      }
      return origSetAttr.apply(this, arguments);
    };
  } catch (e) {}
})();