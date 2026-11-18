document.addEventListener("DOMContentLoaded", () => {
  const chkIntercept = document.getElementById("chkIntercept");
  const chkFloating = document.getElementById("chkFloating");
  const chkHls = document.getElementById("chkHls");
  const statusCard = document.getElementById("statusCard");
  const statusText = document.getElementById("statusText");
  const btnTestConn = document.getElementById("btnTestConn");

  // Load saved preferences
  chrome.storage.local.get(
    {
      interceptEnabled: true,
      showVideoPanel: true,
      captureHls: true
    },
    (res) => {
      chkIntercept.checked = !!res.interceptEnabled;
      chkFloating.checked = res.showVideoPanel !== false;
      chkHls.checked = res.captureHls !== false;
    }
  );

  chkIntercept.addEventListener("change", () => {
    chrome.storage.local.set({ interceptEnabled: chkIntercept.checked });
  });

  chkFloating.addEventListener("change", () => {
    chrome.storage.local.set({ showVideoPanel: chkFloating.checked });
  });

  chkHls.addEventListener("change", () => {
    chrome.storage.local.set({ captureHls: chkHls.checked });
  });

  async function checkConnection() {
    statusText.innerText = "Checking...";
    try {
      const resp = await fetch("http://127.0.0.1:9666/status", {
        method: "GET",
        signal: AbortSignal.timeout(2000)
      });
      if (resp.ok) {
        statusCard.classList.remove("offline");
        statusText.innerText = "Connected to Krolix Desktop (Port 9666)";
      } else {
        throw new Error("Bad status");
      }
    } catch (e) {
      statusCard.classList.add("offline");
      statusText.innerText = "Krolix Desktop Offline (Port 9666)";
    }
  }

  btnTestConn.addEventListener("click", checkConnection);
  checkConnection();
});
