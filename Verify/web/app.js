// VeriSol Verify: installer page logic. Plain JavaScript, no build step.
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var session = null;
  var scanning = false;

  function say(text, ok) {
    var m = $("msg");
    m.textContent = text;
    m.className = ok ? "ok" : "bad";
  }

  function api(method, path, body) {
    return fetch(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var detail = data && data.detail;
          if (Array.isArray(detail)) { detail = detail.map(function (d) { return d.msg; }).join("; "); }
          throw new Error(detail || ("Request failed (" + res.status + ")"));
        }
        return data;
      });
    });
  }

  function position() {
    return new Promise(function (resolve, reject) {
      if (!navigator.geolocation) { reject(new Error("This device has no location service")); return; }
      navigator.geolocation.getCurrentPosition(
        function (p) { resolve({ lat: p.coords.latitude, lon: p.coords.longitude }); },
        function () { reject(new Error("Location is off or was refused. Turn it on to scan.")); },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
      );
    });
  }

  function show(s) {
    session = s;
    ["s2", "s3", "s4"].forEach(function (id) { $(id).classList.toggle("off", s.status !== "open"); });
    $("s1").classList.add("off");
    $("ulaBox").style.display = s.scheme === "ULA" ? "flex" : "none";
    $("tally").innerHTML = "<b>" + s.modules_scanned + "</b> modules · <b>" + s.nameplate_kw.toFixed(2) +
      " kW</b> scanned of " + s.claimed_kw + " kW claimed";
    var list = $("mods");
    list.textContent = "";
    s.modules.forEach(function (m) {
      var li = document.createElement("li");
      li.textContent = m.serial + " · " + m.wp + " Wp · " + (m.manufacturer || "");
      list.appendChild(li);
    });
  }

  $("useGps").onclick = function () {
    position().then(function (p) { $("lat").value = p.lat.toFixed(6); $("lon").value = p.lon.toFixed(6); })
      .catch(function (e) { say(e.message, false); });
  };

  $("open").onclick = function () {
    api("POST", "/api/sessions", {
      consumer_id: $("consumer").value.trim(), scheme: $("scheme").value, vendor_id: $("vendor").value.trim(),
      claimed_kw: parseFloat($("kw").value), lat: parseFloat($("lat").value), lon: parseFloat($("lon").value)
    }).then(function (s) { show(s); say("Session open. Scan each module on the roof.", true); })
      .catch(function (e) { say(e.message, false); });
  };

  function addSerial(serial) {
    serial = (serial || "").trim();
    if (!serial) { say("Enter or scan a serial first", false); return Promise.resolve(); }
    return position().then(function (p) {
      return api("POST", "/api/sessions/" + session.session_id + "/scan", { serial: serial, lat: p.lat, lon: p.lon });
    }).then(function (s) { show(s); $("serial").value = ""; say("Added " + serial.toUpperCase(), true); })
      .catch(function (e) { say(e.message, false); });
  }

  $("add").onclick = function () { addSerial($("serial").value); };

  $("cam").onclick = function () {
    var video = $("video");
    if (scanning) { stopCamera(); return; }
    if (!("BarcodeDetector" in window)) { say("Camera scanning is not supported in this browser. Type the serial instead.", false); return; }
    var detector = new window.BarcodeDetector();
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (stream) {
      scanning = true;
      video.srcObject = stream; video.style.display = "block"; video.play();
      $("cam").textContent = "Stop camera";
      (function tick() {
        if (!scanning) { return; }
        detector.detect(video).then(function (codes) {
          if (codes.length) { stopCamera(); addSerial(codes[0].rawValue); } else { requestAnimationFrame(tick); }
        }).catch(function () { requestAnimationFrame(tick); });
      })();
    }).catch(function () { say("Camera not available. Type the serial instead.", false); });
  };

  function stopCamera() {
    var video = $("video");
    scanning = false;
    if (video.srcObject) { video.srcObject.getTracks().forEach(function (t) { t.stop(); }); video.srcObject = null; }
    video.style.display = "none";
    $("cam").textContent = "Scan with camera";
  }

  $("saveArr").onclick = function () {
    api("POST", "/api/sessions/" + session.session_id + "/array", {
      length_m: parseFloat($("len").value), width_m: parseFloat($("wid").value),
      tilt_deg: parseFloat($("tilt").value), azimuth_deg: parseFloat($("az").value)
    }).then(function (s) { show(s); say("Array measurement saved: " + s.array_area_m2 + " sq m", true); })
      .catch(function (e) { say(e.message, false); });
  };

  $("lock").onclick = function () {
    api("POST", "/api/sessions/" + session.session_id + "/lock", { undertaking_accepted: $("undertaking").checked })
      .then(function (s) { show(s); say("Locked. " + s.modules_scanned + " modules, " + s.nameplate_kw.toFixed(2) + " kW registered to " + s.consumer_id + ".", true); })
      .catch(function (e) { say(e.message, false); });
  };
})();
