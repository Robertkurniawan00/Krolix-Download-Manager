function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", async () => {
  const toggle = document.getElementById("toggleIntercept");
  const connectionBadge = document.getElementById("connectionBadge");
  const connectionText = document.getElementById("connectionText");
  const badgeCount = document.getElementById("badgeCount");
  const streamsList = document.getElementById("streamsList");
  const btnSmartGroup = document.getElementById("btnSmartGroup");
  const btnClearStreams = document.getElementById("btnClearStreams");

  let smartGroupEnabled = true;
  let cachedStreams = [];
  let cachedTab = null;

  // Load intercept switch state & smart dedup state
  chrome.storage.local.get({ interceptEnabled: true, smartGroupEnabled: true }, (res) => {
    toggle.checked = res.interceptEnabled;
    smartGroupEnabled = res.smartGroupEnabled !== false;
    if (btnSmartGroup) {
      btnSmartGroup.classList.toggle("active", smartGroupEnabled);
    }
  });

  toggle.addEventListener("change", () => {
    chrome.storage.local.set({ interceptEnabled: toggle.checked });
  });

  if (btnSmartGroup) {
    btnSmartGroup.addEventListener("click", () => {
      smartGroupEnabled = !smartGroupEnabled;
      btnSmartGroup.classList.toggle("active", smartGroupEnabled);
      chrome.storage.local.set({ smartGroupEnabled });
      renderStreams(cachedStreams, cachedTab);
    });
  }

  if (btnClearStreams) {
    btnClearStreams.addEventListener("click", () => {
      if (!cachedTab) return;
      chrome.runtime.sendMessage({ action: "CLEAR_TAB_STREAMS", tabId: cachedTab.id }, () => {
        cachedStreams = [];
        renderStreams([], cachedTab);
      });
    });
  }

  const licenseBadge = document.getElementById("licenseBadge");

  // Load cached license badge if present
  chrome.storage.local.get(["krolixLicense", "zeroLicense"], (res) => {
    const lic = (res && (res.krolixLicense || res.zeroLicense));
    if (lic && licenseBadge) {
      if (lic.is_master) {
        licenseBadge.innerText = "MASTER";
        licenseBadge.className = "license-badge badge-master";
        licenseBadge.style.display = "inline-flex";
      } else if (lic.is_full) {
        licenseBadge.innerText = "PRO";
        licenseBadge.className = "license-badge badge-pro";
        licenseBadge.style.display = "inline-flex";
      }
    }
  });

  // Check connection to Krolix Desktop App & sync license tier
  try {
    const res = await fetch("http://127.0.0.1:9666/status");
    if (res.ok) {
      const data = await res.json();
      connectionBadge.classList.remove("status-offline");
      connectionText.innerText = "App Active";
      if (licenseBadge && data.license) {
        chrome.storage.local.set({ krolixLicense: data.license, zeroLicense: data.license });
        if (data.license.is_master) {
          licenseBadge.innerText = "MASTER";
          licenseBadge.className = "license-badge badge-master";
          licenseBadge.style.display = "inline-flex";
          licenseBadge.title = "Advance Master Mode: 64 Turbo Threads Enabled";
        } else if (data.license.is_full) {
          licenseBadge.innerText = "PRO";
          licenseBadge.className = "license-badge badge-pro";
          licenseBadge.style.display = "inline-flex";
          licenseBadge.title = "Full Registered License";
        } else {
          licenseBadge.style.display = "none";
        }
      }
    } else {
      throw new Error("HTTP " + res.status);
    }
  } catch (e) {
    connectionBadge.classList.add("status-offline");
    connectionText.innerText = "App Offline";
  }

  // Query active tab and fetch captured streams
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || !tabs[0]) {
      renderStreams([], null);
      return;
    }
    const activeTab = tabs[0];
    cachedTab = activeTab;
    chrome.runtime.sendMessage(
      { action: "GET_TAB_STREAMS", tabId: activeTab.id },
      (response) => {
        const streams = (response && response.streams) ? response.streams : [];
        cachedStreams = streams;
        renderStreams(streams, activeTab);
      }
    );
  });

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

    // Video Ad & Pop Ad Networks
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

  function deduplicateStreams(streams) {
    if (!smartGroupEnabled || streams.length <= 1) return streams;
    const grouped = new Map();
    for (const s of streams) {
      let key = s.url || "";
      try {
        const uObj = new URL(s.url);
        // Group HLS sub-playlists in the same parent folder or sharing a stream base
        const dirPath = uObj.pathname.replace(/\/[^/]+$/, "");
        if ((s.is_hls || uObj.pathname.endsWith(".m3u8")) && dirPath.length > 4) {
          key = uObj.origin + dirPath;
        }
      } catch (e) {}

      if (!grouped.has(key)) {
        grouped.set(key, s);
      } else {
        const prev = grouped.get(key);
        const prevScore = (prev.height || 0) * 1000 + (prev.bitrate || 0) + ((prev.name || "").includes("master") ? 500000 : 0);
        const currScore = (s.height || 0) * 1000 + (s.bitrate || 0) + ((s.name || "").includes("master") ? 500000 : 0);
        if (currScore >= prevScore) {
          grouped.set(key, s);
        }
      }
    }
    return Array.from(grouped.values());
  }

  function renderStreams(streams, activeTab) {
    streamsList.innerHTML = "";

    // Strictly filter out ads, junk previews, and .ts / .m4s / mp2t fragments
    const rawValidStreams = (streams || []).filter((s) => {
      if (!s || !s.url) return false;
      if (isAdOrJunkMedia(s.url, s.name, s)) return false;
      const u = (s.url || "").toLowerCase();
      const ext = (s.ext || "").toLowerCase();
      const isFragment = ext.includes("ts") ||
                         ext.includes("mp2t") ||
                         u.endsWith(".ts") ||
                         u.includes(".ts?") ||
                         u.includes("/segment") ||
                         u.includes("/seg-") ||
                         u.includes("/frag-") ||
                         u.includes("_init_") ||
                         u.includes("-init-") ||
                         u.includes("/init_") ||
                         u.includes("_init.") ||
                         u.includes("-init.") ||
                         u.includes("_header_") ||
                         u.includes("-header-") ||
                         /_\d{3,6}_/i.test(u);
      return !isFragment;
    });

    const validStreams = deduplicateStreams(rawValidStreams);

    badgeCount.innerText = String(validStreams.length);

    if (validStreams.length === 0) {
      streamsList.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
          </div>
          <div class="empty-title">No Media Streams Detected</div>
          <div class="empty-desc">Play a video in this tab to capture HLS (.m3u8) playlists and MP4 streams automatically. (Ad streams are blocked)</div>
        </div>
      `;
      return;
    }

    validStreams.forEach((s, idx) => {
      const u = s.url || "";
      const uLower = u.toLowerCase();
      const isDash = !!(s.is_dash || s.ext === "mpd" || uLower.includes(".mpd"));
      const isHls = !isDash && !!(s.is_hls || s.ext === "m3u8" || uLower.includes(".m3u8"));

      // Display name
      let displayName = s.name || "";
      if (!displayName) {
        try {
          const pathSegments = new URL(u).pathname.split("/");
          displayName = pathSegments[pathSegments.length - 1] || (isDash ? "dash_stream" : "video_stream");
        } catch (e) {
          displayName = `Stream #${idx + 1}`;
        }
      }

      // Format pill, resolution, bitrate, and size
      const pillClass = isDash ? "pill-dash" : (isHls ? "pill-hls" : "pill-direct");
      const pillText = isDash ? "DASH → MP4" : (isHls ? "HLS → MP4" : (s.ext || "MP4").toUpperCase());
      const bytesVal = (s.filesize && s.filesize > 0) ? s.filesize : (s.size && s.size > 0 ? s.size : 0);
      const bitrateVal = s.bitrate || (s.bandwidth ? Math.round(s.bandwidth / 1000) : 0);
      const bitrateText = bitrateVal > 0 ? (bitrateVal >= 1000 ? `${(bitrateVal/1000).toFixed(1)} Mbps` : `${bitrateVal} kbps`) : "";
      const resText = s.resolution || (s.height ? `${s.height}p` : "");
      const sizeText = bytesVal > 0 ? `~${formatBytes(bytesVal)}` : ((isHls || isDash) ? "Auto MP4" : "--");

      const metaParts = [];
      if (resText) metaParts.push(resText);
      if (bitrateText) metaParts.push(bitrateText);
      metaParts.push(sizeText);

      const card = document.createElement("div");
      card.className = "stream-card";
      card.innerHTML = `
        <div class="stream-info">
          <div class="stream-name" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</div>
          <div class="stream-meta">
            <span class="pill ${escapeHtml(pillClass)}">${escapeHtml(pillText)}</span>
            <span class="stream-size">${escapeHtml(metaParts.join(" • "))}</span>
          </div>
        </div>
        <div class="card-btns">
          <button class="btn-copy" title="Copy stream URL">Copy</button>
          <button class="btn-download" title="Download this stream as MP4">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>Download</span>
          </button>
        </div>
      `;

      const btnCopy = card.querySelector(".btn-copy");
      if (btnCopy) {
        btnCopy.addEventListener("click", (e) => {
          e.stopPropagation();
          navigator.clipboard.writeText(s.url).then(() => {
            btnCopy.innerText = "Copied";
            setTimeout(() => { btnCopy.innerText = "Copy"; }, 1200);
          });
        });
      }

      const btn = card.querySelector(".btn-download");
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        btn.disabled = true;
        btn.classList.add("sent");
        btn.innerHTML = `Opening...`;

        const tabTitle = activeTab ? activeTab.title : "Video";
        const cleanTitle = (tabTitle || "Video").replace(/[\\/*?:"<>|]/g, "_").trim();
        const baseName = displayName.replace(/\.[a-zA-Z0-9]+$/, "");
        const isStream = isHls || isDash;
        const outFilename = isStream ? `${cleanTitle} [${baseName}].mp4` : `${cleanTitle}.${s.ext || 'mp4'}`;

        let finished = false;
        function finishButton(success) {
          if (finished) return;
          finished = true;
          if (success) {
            btn.innerHTML = `Sent to Krolix!`;
            setTimeout(() => {
              try { window.close(); } catch (e) {}
            }, 800);
          } else {
            btn.classList.remove("sent");
            btn.disabled = false;
            btn.innerHTML = `
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              <span>Download</span>
            `;
          }
        }

        // Safety fallback timer: avoid hanging spinner or falsely claiming success
        const timer = setTimeout(() => finishButton(false), 4500);

        const hlsVariants = validStreams.filter((st) => st.is_hls || (st.url && st.url.includes(".m3u8")));

        try {
          chrome.runtime.sendMessage({
            action: "DOWNLOAD_MEDIA",
            data: {
              url: s.url,
              masterUrl: s.masterUrl || "",
              pageUrl: activeTab ? activeTab.url : "",
              initiator: s.initiator || "",
              filename: outFilename,
              filesize: bytesVal || -1,
              height: s.height || 0,
              width: s.width || 0,
              resolution: resText,
              bitrate: bitrateVal,
              bandwidth: s.bandwidth || 0,
              duration: s.duration || 0,
              title: cleanTitle,
              is_media: true,
              is_hls: isHls || isDash,
              is_dash: isDash,
              variants: hlsVariants
            }
          }, (res) => {
            clearTimeout(timer);
            const isOk = !chrome.runtime.lastError && (res ? res.success !== false : true);
            finishButton(isOk);
          });
        } catch (err) {
          clearTimeout(timer);
          finishButton(false);
        }
      });

      streamsList.appendChild(card);
    });
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return "--";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }
});
