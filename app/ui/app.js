const $ = id => document.getElementById(id);
let pending = false;
for (const action of ["start", "pause", "land"]) {
  $(action).onclick = async () => {
    if (pending) return;
    pending = true;
    try {
      const response = await fetch(`/api/${action}`, {method:"POST", headers:{"X-Drone137-Control":"local"}});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Control failed");
    } catch (error) { $("notice").textContent = error.message; }
    finally { pending = false; }
  };
}
async function refresh() {
  try {
    const response = await fetch("/api/status", {cache:"no-store"});
    if (!response.ok) throw new Error("Status unavailable");
    const s = await response.json();
    $("mode").textContent = s.mode === "fixture" ? "FIXTURE DEMO" : "NATIVE SIMULATION";
    $("notice").textContent = s.error || (s.mode === "fixture"
      ? "Fixture demo · prerecorded images, scripted decisions and kinematic movement. No real inference or flight dynamics."
      : "Simulation integration · acceptance checks remain pending. Physical transport disabled.");
    $("state").textContent = s.state;
    $("view").textContent = s.view;
    $("position").textContent = s.telemetry.position.map(n => n.toFixed(1)).join(" / ");
    $("observation").textContent = s.decision?.observation || "—";
    $("action").textContent = s.decision?.action || "—";
    $("reason").textContent = s.decision?.reason || "Waiting for an observation.";
    $("start").disabled = pending || !["idle","complete"].includes(s.state);
    $("pause").disabled = pending || !["moving","observing"].includes(s.state);
    $("report").hidden = !["complete","failed"].includes(s.state);
    if (s.report) $("report").href = s.report;
    $("camera").src = `/api/frame?t=${Date.now()}`;
  } catch (error) {
    $("notice").textContent = "Application connection lost. Inspect the local process logs.";
    $("start").disabled = $("pause").disabled = true;
  }
  setTimeout(refresh, 500);
}
refresh();
