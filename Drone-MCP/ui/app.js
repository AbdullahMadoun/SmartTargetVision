/* ── DOM Elements ─────────────────────────────────────────────── */
const dom = {
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  statusBox: document.getElementById("status-box"),
  chatState: document.getElementById("chat-state"),
  simFrame: document.getElementById("sim-frame"),
  openVnc: document.getElementById("open-vnc"),
  vncLoading: document.getElementById("vnc-loading"),
  vncLoadingMsg: document.getElementById("vnc-loading-msg"),
  statusBadge: document.getElementById("sim-status-badge"),
  connectionQuality: document.getElementById("connection-quality"),
  togglePanel: document.getElementById("btn-toggle-panel"),
  fullscreenBtn: document.getElementById("btn-fullscreen"),
  themeBtn: document.getElementById("btn-theme"),
  mainLayout: document.getElementById("main-layout"),
  viewport: document.getElementById("viewport"),
  controlPanel: document.getElementById("control-panel"),
  droneSelector: document.getElementById("drone-selector"),
  statusToggle: document.getElementById("status-toggle"),
  waypointMap: document.getElementById("waypoint-map"),
  mapFallback: document.getElementById("map-fallback"),
  waypointList: document.getElementById("waypoint-list"),
  waypointForm: document.getElementById("waypoint-form"),
  wpLat: document.getElementById("wp-lat"),
  wpLon: document.getElementById("wp-lon"),
  wpAlt: document.getElementById("wp-alt"),
  wpYaw: document.getElementById("wp-yaw"),
  btnCenterMap: document.getElementById("btn-center-map"),
  btnAddCurrent: document.getElementById("btn-add-current"),
  btnClearWaypoints: document.getElementById("btn-clear-waypoints"),
  btnExecuteMission: document.getElementById("btn-execute-mission"),
  geoAlt: document.getElementById("geo-alt"),
  geoDistance: document.getElementById("geo-distance"),
  geoBattery: document.getElementById("geo-battery"),
  btnApplyGeofence: document.getElementById("btn-apply-geofence"),
  launchModel: document.getElementById("launch-model"),
  launchCameraTopic: document.getElementById("launch-camera-topic"),
  launchPorts: document.getElementById("launch-ports"),
  launchEnvJson: document.getElementById("launch-env-json"),
  launchHeadless: document.getElementById("launch-headless"),
  launchRequireGui: document.getElementById("launch-require-gui"),
  launchRequireCamera: document.getElementById("launch-require-camera"),
  launchNetworkHost: document.getElementById("launch-network-host"),
  btnUseTemplateProfile: document.getElementById("btn-use-template-profile"),
  btnClearLaunchOverrides: document.getElementById("btn-clear-launch-overrides"),
  launchProfileSummary: document.getElementById("launch-profile-summary"),
  manualSpeed: document.getElementById("manual-speed"),
  manualYawRate: document.getElementById("manual-yaw-rate"),
  manualControlStatus: document.getElementById("manual-control-status"),
  cameraFrame: document.getElementById("camera-frame"),
  cameraPlaceholder: document.getElementById("camera-placeholder"),
  cameraMeta: document.getElementById("camera-meta"),
  btnRefreshCamera: document.getElementById("btn-refresh-camera"),
  btnFitCamera: document.getElementById("btn-fit-camera"),
  trackTargetClass: document.getElementById("track-target-class"),
  trackConfidence: document.getElementById("track-confidence"),
  trackLoop: document.getElementById("track-loop"),
  trackMaxForward: document.getElementById("track-max-forward"),
  btnTrackStart: document.getElementById("btn-track-start"),
  btnTrackStep: document.getElementById("btn-track-step"),
  btnTrackStop: document.getElementById("btn-track-stop"),
  trackingStatus: document.getElementById("tracking-status"),
  templateGrid: document.getElementById("template-grid"),
  templateSummary: document.getElementById("template-summary"),
  recordingSummary: document.getElementById("recording-summary"),
  recordingList: document.getElementById("recording-list"),
  btnStartRecording: document.getElementById("btn-start-recording"),
  btnStopRecording: document.getElementById("btn-stop-recording"),
  btnRefreshRecordings: document.getElementById("btn-refresh-recordings"),
  hudAltitude: document.getElementById("hud-altitude"),
  hudSpeed: document.getElementById("hud-speed"),
  hudBattery: document.getElementById("hud-battery"),
  hudMode: document.getElementById("hud-mode"),
  hudGps: document.getElementById("hud-gps"),
  hudArmed: document.getElementById("hud-armed"),
  compassArrow: document.getElementById("compass-arrow"),
  sessionSummaryTitle: document.getElementById("session-summary-title"),
  sessionSummaryCopy: document.getElementById("session-summary-copy"),
  sessionSummaryDetail: document.getElementById("session-summary-detail"),
};

const STORAGE_KEYS = {
  theme: "drone-mcp.theme",
  selectedDrone: "drone-mcp.selected-drone",
  selectedTemplate: "drone-mcp.selected-template",
  launchProfile: "drone-mcp.launch-profile",
  waypoints: "drone-mcp.waypoints",
  geofence: "drone-mcp.geofence",
  recordings: "drone-mcp.recordings",
  statusCollapsed: "drone-mcp.status-collapsed",
};

const DEFAULT_GEOFENCE = {
  maxAltitudeM: 120,
  maxDistanceM: 500,
  minBatteryPercent: 20,
};

const DEFAULT_SIMULATION_TEMPLATES = [
  {
    templateId: "default",
    name: "Balanced Single-Drone",
    description: "Recommended preset for the full operator console with standard camera support.",
    image: "drone-mcp/sim-monocam:local",
    containerName: "drone-mcp-sim-monocam",
    dockerfile: "docker/sim-monocam.Dockerfile",
    model: "gz_x500_mono_cam",
    cameraTopic: "",
    headless: true,
    requireGui: false,
    requireCamera: true,
    networkHost: false,
    ports: ["14540:14540/udp", "14550:14550/udp", "8888:8888/udp"],
    environment: {},
    recommended: true,
    tags: ["single-drone", "general-purpose"],
    launchNotes: "Balanced preset for map missions, telemetry, and camera validation.",
    missionDefaults: { altitude: 10, yaw: 0 },
    defaultGeofence: { ...DEFAULT_GEOFENCE },
    trackingDefaults: { targetClass: "person", confidenceThreshold: 0.4, loopIntervalS: 0.35, maxForwardSpeedMS: 1.2 },
  },
  {
    templateId: "fast",
    name: "Fast Headless",
    description: "Lighter-weight preset for quick backend iteration and faster restart cycles.",
    image: "drone-mcp/sim-monocam:local",
    containerName: "drone-mcp-sim-monocam-fast",
    dockerfile: "docker/sim-monocam.Dockerfile",
    model: "gz_x500_mono_cam",
    cameraTopic: "",
    headless: true,
    requireGui: false,
    requireCamera: false,
    networkHost: false,
    ports: ["14540:14540/udp", "14550:14550/udp", "8888:8888/udp"],
    environment: {},
    recommended: false,
    tags: ["fast", "headless"],
    launchNotes: "Quickest server preset when you only need autopilot and telemetry loops.",
    missionDefaults: { altitude: 8, yaw: 0 },
    defaultGeofence: { maxAltitudeM: 80, maxDistanceM: 250, minBatteryPercent: 25 },
    trackingDefaults: { targetClass: "person", confidenceThreshold: 0.45, loopIntervalS: 0.4, maxForwardSpeedMS: 1.0 },
  },
  {
    templateId: "visual",
    name: "Visual Debug",
    description: "Keeps the graphical path on for camera-heavy and inspection-heavy sessions.",
    image: "drone-mcp/sim-visual:local",
    containerName: "drone-mcp-sim-monocam-visual",
    dockerfile: "docker/sim-visual.Dockerfile",
    model: "gz_x500_mono_cam",
    cameraTopic: "",
    headless: false,
    requireGui: true,
    requireCamera: true,
    networkHost: true,
    ports: ["14540:14540/udp", "14550:14550/udp", "8888:8888/udp"],
    environment: {
      DRONE_MCP_REQUIRED_MODEL: "x500_mono_cam_0",
      DRONE_MCP_MODEL_WAIT_SECONDS: "180",
      VNC_GEOMETRY: "1920x1080",
    },
    recommended: false,
    tags: ["visual", "camera"],
    launchNotes: "Visual-first preset for Gazebo GUI inspection, camera debugging, and operator demos.",
    missionDefaults: { altitude: 10, yaw: 0 },
    defaultGeofence: { ...DEFAULT_GEOFENCE },
    trackingDefaults: { targetClass: "person", confidenceThreshold: 0.4, loopIntervalS: 0.35, maxForwardSpeedMS: 1.2 },
  },
];

const state = {
  config: {},
  statusSnapshot: null,
  runtimeText: "",
  telemetryText: "",
  telemetry: null,
  lastTelemetry: null,
  lastTelemetryAt: 0,
  selectedDroneId: "",
  selectedTemplateId: "",
  simulationTemplates: [],
  launchProfile: null,
  theme: "dark",
  panelCollapsed: false,
  statusCollapsed: false,
  missionRunning: false,
  missionAbort: false,
  waypoints: [],
  recordings: [],
  activeRecording: null,
  selectedRecordingId: "",
  geofence: { ...DEFAULT_GEOFENCE },
  homePosition: null,
  map: null,
  mapReady: false,
  mapFailed: false,
  waypointLayer: null,
  missionLayer: null,
  recordingLayer: null,
  currentTrack: [],
  statusMode: "polling",
  statusSocket: null,
  statusPollTimer: null,
  telemetryPollTimer: null,
  healthPollTimer: null,
  cameraTimer: null,
  manualControlTimer: null,
  manualControlCommand: null,
  pressedManualKeys: new Set(),
  tracking: null,
  configLoaded: false,
  latitudeFallback: 47.397742,
  longitudeFallback: 8.545594,
};

let chatHistory = [];

function storageGet(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function storageSet(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage failures.
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function formatNumber(value, digits = 2) {
  return Number.isFinite(value) ? Number(value).toFixed(digits) : "--";
}

function formatCoordinate(value) {
  return Number.isFinite(value) ? Number(value).toFixed(6) : "--";
}

function safeText(value, fallback = "--") {
  return value == null || value === "" ? fallback : String(value);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => (
    {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character] || character
  ));
}

function parseBoolean(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return fallback;
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    if (["0", "false", "no", "off"].includes(normalized)) return false;
  }
  return fallback;
}

function normalizeStringMap(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, entry]) => [String(key).trim(), entry == null ? "" : String(entry)])
      .filter(([key]) => key),
  );
}

function normalizeMissionDefaults(value) {
  if (!value || typeof value !== "object") return null;
  const altitude = Number(value.altitude ?? value.altitude_m ?? value.alt);
  const yaw = Number(value.yaw ?? value.yaw_deg);
  return {
    altitude: Number.isFinite(altitude) ? altitude : 10,
    yaw: Number.isFinite(yaw) ? yaw : 0,
  };
}

function normalizeTrackingDefaults(value) {
  if (!value || typeof value !== "object") return null;
  const confidenceThreshold = Number(value.confidenceThreshold ?? value.confidence_threshold);
  const loopIntervalS = Number(value.loopIntervalS ?? value.loop_interval_s);
  const maxForwardSpeedMS = Number(value.maxForwardSpeedMS ?? value.max_forward_speed_m_s);
  return {
    targetClass: safeText(value.targetClass ?? value.target_class, "person"),
    confidenceThreshold: Number.isFinite(confidenceThreshold) ? confidenceThreshold : 0.4,
    loopIntervalS: Number.isFinite(loopIntervalS) ? loopIntervalS : 0.35,
    maxForwardSpeedMS: Number.isFinite(maxForwardSpeedMS) ? maxForwardSpeedMS : 1.2,
  };
}

function launchProfileFromTemplate(template) {
  if (!template) return null;
  return {
    image: safeText(template.image, ""),
    containerName: safeText(template.containerName, ""),
    dockerfile: safeText(template.dockerfile, ""),
    model: safeText(template.model, ""),
    headless: Boolean(template.headless),
    requireGui: Boolean(template.requireGui),
    requireCamera: Boolean(template.requireCamera),
    networkHost: Boolean(template.networkHost),
    ports: Array.isArray(template.ports) ? template.ports.map((value) => String(value).trim()).filter(Boolean) : [],
    environment: normalizeStringMap(template.environment),
    cameraTopic: safeText(template.cameraTopic ?? template.camera_topic, ""),
  };
}

function normalizeLaunchProfile(value, fallbackTemplate = getSelectedTemplate()) {
  const fallback = launchProfileFromTemplate(fallbackTemplate) || {
    image: "",
    containerName: "",
    dockerfile: "",
    model: "gz_x500_mono_cam",
    headless: true,
    requireGui: false,
    requireCamera: true,
    networkHost: false,
    ports: ["14540:14540/udp", "14550:14550/udp", "8888:8888/udp"],
    environment: {},
    cameraTopic: "",
  };
  if (!value || typeof value !== "object") return { ...fallback };
  const ports = Array.isArray(value.ports)
    ? value.ports.map((entry) => String(entry).trim()).filter(Boolean)
    : typeof value.ports === "string"
      ? value.ports.split(",").map((entry) => entry.trim()).filter(Boolean)
      : fallback.ports;
  return {
    image: safeText(value.image ?? fallback.image, fallback.image),
    containerName: safeText(value.containerName ?? value.container_name ?? fallback.containerName, fallback.containerName),
    dockerfile: safeText(value.dockerfile ?? fallback.dockerfile, fallback.dockerfile),
    model: safeText(value.model ?? fallback.model, fallback.model),
    headless: parseBoolean(value.headless, fallback.headless),
    requireGui: parseBoolean(value.requireGui ?? value.require_gui, fallback.requireGui),
    requireCamera: parseBoolean(value.requireCamera ?? value.require_camera, fallback.requireCamera),
    networkHost: parseBoolean(value.networkHost ?? value.network_host, fallback.networkHost),
    ports,
    environment: normalizeStringMap(value.environment ?? fallback.environment),
    cameraTopic: safeText(value.cameraTopic ?? value.camera_topic ?? fallback.cameraTopic, fallback.cameraTopic),
  };
}

function haversineMeters(a, b) {
  if (!a || !b) return 0;
  const R = 6371000;
  const toRad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * toRad;
  const dLon = (b.lon - a.lon) * toRad;
  const lat1 = a.lat * toRad;
  const lat2 = b.lat * toRad;
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const c = 2 * Math.atan2(
    Math.sqrt(sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon),
    Math.sqrt(1 - (sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLon * sinLon)),
  );
  return R * c;
}

function bearingDegrees(a, b) {
  if (!a || !b) return 0;
  const toRad = Math.PI / 180;
  const toDeg = 180 / Math.PI;
  const lat1 = a.lat * toRad;
  const lat2 = b.lat * toRad;
  const dLon = (b.lon - a.lon) * toRad;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return (Math.atan2(y, x) * toDeg + 360) % 360;
}

function formatGpsPoint(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : "--";
}

function normalizeTemplate(raw, index) {
  if (!raw || typeof raw !== "object") return null;
  const templateId = String(raw.template_id ?? raw.id ?? `template-${index + 1}`).trim();
  if (!templateId) return null;
  const ports = Array.isArray(raw.ports)
    ? raw.ports.map((value) => String(value).trim()).filter(Boolean)
    : typeof raw.ports === "string"
      ? raw.ports.split(",").map((value) => value.trim()).filter(Boolean)
      : [];
  const tags = Array.isArray(raw.tags)
    ? raw.tags.map((value) => String(value).trim()).filter(Boolean)
    : [];
  return {
    templateId,
    name: safeText(raw.name ?? raw.title ?? templateId, templateId),
    description: safeText(raw.description ?? raw.summary, "Server-driven simulation preset."),
    image: String(raw.image ?? "").trim(),
    containerName: String(raw.container_name ?? raw.containerName ?? "").trim(),
    dockerfile: String(raw.dockerfile ?? "").trim(),
    model: String(raw.model ?? "").trim(),
    cameraTopic: String(raw.camera_topic ?? raw.cameraTopic ?? "").trim(),
    headless: parseBoolean(raw.headless, true),
    requireGui: parseBoolean(raw.require_gui ?? raw.requireGui, false),
    requireCamera: parseBoolean(raw.require_camera ?? raw.requireCamera, true),
    networkHost: parseBoolean(raw.network_host ?? raw.networkHost, false),
    environment: normalizeStringMap(raw.environment),
    ports,
    recommended: Boolean(raw.recommended),
    tags,
    launchNotes: safeText(raw.launch_notes ?? raw.launchNotes, ""),
    missionDefaults: normalizeMissionDefaults(raw.mission_defaults ?? raw.missionDefaults),
    defaultGeofence: normalizeGeofence(raw.default_geofence ?? raw.defaultGeofence),
    trackingDefaults: normalizeTrackingDefaults(raw.tracking_defaults ?? raw.trackingDefaults),
  };
}

function normalizeGeofence(raw) {
  if (!raw || typeof raw !== "object") return null;
  const altitude = Number(raw.maxAltitudeM ?? raw.max_altitude_m ?? raw.max_altitude);
  const distance = Number(raw.maxDistanceM ?? raw.max_distance_from_home_m ?? raw.max_distance);
  const battery = Number(raw.minBatteryPercent ?? raw.min_battery_percent_for_rtl ?? raw.min_battery);
  return {
    maxAltitudeM: clamp(Number.isFinite(altitude) ? altitude : DEFAULT_GEOFENCE.maxAltitudeM, 1, 10000),
    maxDistanceM: clamp(Number.isFinite(distance) ? distance : DEFAULT_GEOFENCE.maxDistanceM, 1, 100000),
    minBatteryPercent: clamp(Number.isFinite(battery) ? battery : DEFAULT_GEOFENCE.minBatteryPercent, 1, 100),
  };
}

function normalizeRecordingEntry(raw, index) {
  if (!raw || typeof raw !== "object") return null;
  return {
    id: String(raw.id ?? raw.recording_id ?? `recording-${index + 1}`),
    name: safeText(raw.name ?? raw.title, `Recording ${index + 1}`),
    createdAt: Number(raw.createdAt ?? raw.created_at ?? Date.now()),
    points: Array.isArray(raw.points ?? raw.track) ? (raw.points ?? raw.track) : [],
    active: Boolean(raw.active),
  };
}

function activeDronePayload(extra = {}) {
  return state.selectedDroneId ? { drone_id: state.selectedDroneId, ...extra } : extra;
}

function appendMessage(role, content) {
  if (!dom.chatLog) return;
  const node = document.createElement("div");
  node.className = `chat-entry ${role}`;
  node.textContent = content;
  dom.chatLog.appendChild(node);
  dom.chatLog.scrollTop = dom.chatLog.scrollHeight;
}

function parseMaybeJson(text) {
  if (typeof text !== "string") return text;
  const trimmed = text.trim();
  if (!(trimmed.startsWith("{") || trimmed.startsWith("["))) return text;
  try {
    return JSON.parse(trimmed);
  } catch {
    return text;
  }
}

async function fetchText(url, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json, text/plain, */*",
        ...(options.headers || {}),
      },
    });
    const raw = await response.text();
    if (!response.ok) throw new Error(raw || response.statusText);
    return { response, raw, data: parseMaybeJson(raw) };
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchJson(url, options = {}, timeoutMs = 10000) {
  const { data } = await fetchText(url, options, timeoutMs);
  return data;
}

function parseToolResponse(data) {
  if (data == null) return "";
  if (typeof data === "string") return data;
  if (typeof data.text === "string") return data.text;
  if (typeof data.message === "string") return data.message;
  if (typeof data.detail === "string") return data.detail;
  return JSON.stringify(data, null, 2);
}

function updateBadgeFromText(text) {
  if (!dom.statusBadge) return;
  const value = text || "";
  if (value.includes("GUI Ready: yes") || value.includes("Ready: yes")) {
    dom.statusBadge.textContent = "RUNNING";
    dom.statusBadge.className = "badge badge-running";
  } else if (value.includes("Running: yes")) {
    dom.statusBadge.textContent = "STARTING";
    dom.statusBadge.className = "badge badge-starting";
  } else {
    dom.statusBadge.textContent = "OFFLINE";
    dom.statusBadge.className = "badge badge-offline";
  }
}

function setLoadingState(text) {
  if (dom.vncLoadingMsg) dom.vncLoadingMsg.textContent = text;
}

function hideLoadingOverlay() {
  if (dom.vncLoading) dom.vncLoading.classList.add("hidden");
}

function showLoadingOverlay(text) {
  if (!dom.vncLoading) return;
  dom.vncLoading.classList.remove("hidden");
  if (text) setLoadingState(text);
}

function setPanelCollapsed(collapsed) {
  state.panelCollapsed = Boolean(collapsed);
  dom.mainLayout.classList.toggle("panel-collapsed", state.panelCollapsed);
}

function setStatusCollapsed(collapsed) {
  state.statusCollapsed = Boolean(collapsed);
  const section = dom.statusToggle?.closest(".status-section");
  if (section) section.classList.toggle("is-collapsed", state.statusCollapsed);
  storageSet(STORAGE_KEYS.statusCollapsed, state.statusCollapsed);
}

function setTheme(theme) {
  state.theme = theme === "light" ? "light" : "dark";
  document.body.classList.toggle("theme-light", state.theme === "light");
  storageSet(STORAGE_KEYS.theme, state.theme);
}

function updateConnectionQuality(mode, label, className) {
  state.statusMode = mode;
  if (!dom.connectionQuality) return;
  dom.connectionQuality.className = `quality-chip ${className}`;
  dom.connectionQuality.textContent = label;
}

function normalizeWaypoint(raw, index) {
  if (!raw) return null;
  const lat = Number(raw.lat ?? raw.latitude ?? raw.latitude_deg);
  const lon = Number(raw.lon ?? raw.lng ?? raw.longitude ?? raw.longitude_deg);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return {
    id: raw.id || `wp-${Date.now()}-${index}`,
    lat,
    lon,
    alt: Number(raw.alt ?? raw.altitude ?? raw.altitude_m ?? 10) || 10,
    yaw: Number(raw.yaw ?? raw.heading ?? raw.yaw_deg ?? 0) || 0,
  };
}

function loadWaypoints() {
  const raw = storageGet(STORAGE_KEYS.waypoints, []);
  state.waypoints = Array.isArray(raw) ? raw.map((item, index) => normalizeWaypoint(item, index)).filter(Boolean) : [];
}

function saveWaypoints() {
  storageSet(STORAGE_KEYS.waypoints, state.waypoints);
}

function loadGeofence() {
  const raw = storageGet(STORAGE_KEYS.geofence, null);
  state.geofence = { ...DEFAULT_GEOFENCE, ...(raw || {}) };
}

function saveGeofence() {
  storageSet(STORAGE_KEYS.geofence, state.geofence);
}

function loadLaunchProfile() {
  const raw = storageGet(STORAGE_KEYS.launchProfile, null);
  state.launchProfile = raw ? normalizeLaunchProfile(raw) : null;
}

function saveLaunchProfile() {
  storageSet(STORAGE_KEYS.launchProfile, state.launchProfile);
}

function loadRecordings() {
  const raw = storageGet(STORAGE_KEYS.recordings, []);
  state.recordings = Array.isArray(raw) ? raw : [];
}

function saveRecordings() {
  storageSet(STORAGE_KEYS.recordings, state.recordings);
}

function ensureDefaultInputs() {
  if (dom.geoAlt) dom.geoAlt.value = state.geofence.maxAltitudeM;
  if (dom.geoDistance) dom.geoDistance.value = state.geofence.maxDistanceM;
  if (dom.geoBattery) dom.geoBattery.value = state.geofence.minBatteryPercent;
  if (dom.wpAlt && !dom.wpAlt.value) dom.wpAlt.value = "10";
  if (dom.wpYaw && !dom.wpYaw.value) dom.wpYaw.value = "0";
}

function applyLaunchProfileToForm() {
  const profile = state.launchProfile || normalizeLaunchProfile(null);
  if (dom.launchModel) dom.launchModel.value = profile.model || "";
  if (dom.launchCameraTopic) dom.launchCameraTopic.value = profile.cameraTopic || "";
  if (dom.launchPorts) dom.launchPorts.value = Array.isArray(profile.ports) ? profile.ports.join(",") : "";
  if (dom.launchEnvJson) {
    dom.launchEnvJson.value = Object.keys(profile.environment || {}).length
      ? JSON.stringify(profile.environment, null, 2)
      : "";
  }
  if (dom.launchHeadless) dom.launchHeadless.checked = Boolean(profile.headless);
  if (dom.launchRequireGui) dom.launchRequireGui.checked = Boolean(profile.requireGui);
  if (dom.launchRequireCamera) dom.launchRequireCamera.checked = Boolean(profile.requireCamera);
  if (dom.launchNetworkHost) dom.launchNetworkHost.checked = Boolean(profile.networkHost);
}

function renderLaunchProfileSummary() {
  const template = getSelectedTemplate();
  const profile = state.launchProfile || normalizeLaunchProfile(null, template);
  if (!dom.launchProfileSummary) return;
  const envKeys = Object.keys(profile.environment || {});
  dom.launchProfileSummary.textContent =
    `Active profile: ${template?.name || "custom"} · model ${safeText(profile.model, "n/a")} · ${
      profile.headless ? "headless" : "visual"
    } · ${profile.requireCamera ? "camera required" : "camera optional"} · ${
      profile.networkHost ? "host networking" : `${profile.ports.length} mapped ports`
    }\nCamera topic: ${safeText(profile.cameraTopic, "auto-detect")}\nEnvironment: ${
      envKeys.length ? envKeys.join(", ") : "none"
    }`;
}

function syncLaunchProfile(profile, persist = true) {
  state.launchProfile = normalizeLaunchProfile(profile);
  applyLaunchProfileToForm();
  renderLaunchProfileSummary();
  if (persist) saveLaunchProfile();
}

function readLaunchProfileFromForm() {
  let environment = {};
  const envText = dom.launchEnvJson?.value?.trim() || "";
  if (envText) {
    try {
      environment = normalizeStringMap(JSON.parse(envText));
    } catch {
      environment = {};
    }
  }
  return normalizeLaunchProfile({
    ...(state.launchProfile || {}),
    model: dom.launchModel?.value?.trim() || "",
    cameraTopic: dom.launchCameraTopic?.value?.trim() || "",
    ports: dom.launchPorts?.value?.trim() || "",
    environment,
    headless: dom.launchHeadless?.checked,
    requireGui: dom.launchRequireGui?.checked,
    requireCamera: dom.launchRequireCamera?.checked,
    networkHost: dom.launchNetworkHost?.checked,
  });
}

function syncGeofenceState(rawGeofence, persist = true) {
  const geofence = normalizeGeofence(rawGeofence);
  if (!geofence) return;
  state.geofence = geofence;
  ensureDefaultInputs();
  renderMapState();
  if (persist) saveGeofence();
}

function syncRecordingsState(recordings, persist = true) {
  if (!Array.isArray(recordings)) return;
  state.recordings = recordings.map(normalizeRecordingEntry).filter(Boolean);
  if (persist) saveRecordings();
  renderRecordings();
  if (state.selectedRecordingId) {
    const selected = state.recordings.find((entry) => entry.id === state.selectedRecordingId);
    if (selected) {
      renderRecordingTrack(selected);
      renderRecordingSummary(selected);
    }
  }
}

function getSelectedTemplate() {
  return state.simulationTemplates.find((template) => template.templateId === state.selectedTemplateId) || null;
}

function getActiveLaunchProfile(template = getSelectedTemplate()) {
  return normalizeLaunchProfile(state.launchProfile, template);
}

function runtimeTemplateArguments(template = getSelectedTemplate()) {
  const profile = getActiveLaunchProfile(template);
  if (!profile) return {};
  const args = {};
  if (profile.image) args.image = profile.image;
  if (profile.containerName) args.container_name = profile.containerName;
  if (profile.dockerfile) args.dockerfile = profile.dockerfile;
  if (profile.model) args.model = profile.model;
  if (profile.ports?.length) args.ports = profile.ports;
  if (profile.environment && Object.keys(profile.environment).length) args.environment = profile.environment;
  args.headless = String(profile.headless);
  args.require_gui = String(profile.requireGui);
  args.require_camera = String(profile.requireCamera);
  args.network_host = String(profile.networkHost);
  return args;
}

function renderSessionSummary() {
  const template = getSelectedTemplate();
  const profile = getActiveLaunchProfile(template);
  const droneId = state.selectedDroneId || state.config.drone_id || "test-drone";
  if (dom.sessionSummaryTitle) {
    dom.sessionSummaryTitle.textContent = `Drone ${droneId}`;
  }
  if (dom.sessionSummaryCopy) {
    dom.sessionSummaryCopy.textContent = template
      ? `${template.name} preset selected on a server-driven runtime.`
      : "Single-drone simulation ops on a server-driven runtime";
  }
  if (dom.sessionSummaryDetail) {
    dom.sessionSummaryDetail.textContent = template
      ? `${template.description} ${profile.requireGui ? "GUI on" : "Headless"} · ${profile.requireCamera ? "camera on" : "camera optional"} · ${profile.networkHost ? "host networking" : "mapped ports"}.${template.launchNotes ? ` ${template.launchNotes}` : ""}`
      : "Heavy compute stays server-side. The UI stays focused, responsive, and easy to run.";
  }
}

function renderTemplateSummary() {
  if (!dom.templateSummary) return;
  const template = getSelectedTemplate();
  if (!template) {
    dom.templateSummary.textContent = "Choose a template to define how the simulator launches on the server.";
    return;
  }
  const profile = getActiveLaunchProfile(template);
  const mode = profile.requireGui ? "GUI" : "Headless";
  const camera = profile.requireCamera ? "camera on" : "camera optional";
  const network = profile.networkHost ? "host networking" : `${profile.ports.length} mapped ports`;
  dom.templateSummary.textContent =
    `${template.name} selected. ${mode}, ${camera}, ${network}. ${template.launchNotes || "Start or reset will use this preset on the server."}`;
}

function selectSimulationTemplate(templateId, announce = true, reseedLaunchProfile = true) {
  const template = state.simulationTemplates.find((entry) => entry.templateId === templateId) || state.simulationTemplates[0] || null;
  state.selectedTemplateId = template?.templateId || "";
  storageSet(STORAGE_KEYS.selectedTemplate, state.selectedTemplateId);
  if (template && reseedLaunchProfile) {
    syncLaunchProfile(launchProfileFromTemplate(template), true);
  } else {
    applyLaunchProfileToForm();
    renderLaunchProfileSummary();
  }
  if (template?.defaultGeofence) {
    syncGeofenceState(template.defaultGeofence, true);
  }
  if (template?.missionDefaults) {
    if (dom.wpAlt) dom.wpAlt.value = String(template.missionDefaults.altitude);
    if (dom.wpYaw) dom.wpYaw.value = String(template.missionDefaults.yaw);
  }
  if (template?.trackingDefaults) {
    if (dom.trackTargetClass) dom.trackTargetClass.value = template.trackingDefaults.targetClass;
    if (dom.trackConfidence) dom.trackConfidence.value = String(template.trackingDefaults.confidenceThreshold);
    if (dom.trackLoop) dom.trackLoop.value = String(template.trackingDefaults.loopIntervalS);
    if (dom.trackMaxForward) dom.trackMaxForward.value = String(template.trackingDefaults.maxForwardSpeedMS);
  }
  renderTemplates();
  renderTemplateSummary();
  renderSessionSummary();
  if (announce && template && dom.statusBox) {
    const profile = getActiveLaunchProfile(template);
    dom.statusBox.textContent =
      `Selected simulation template: ${template.name}\n${template.description}\n` +
      `Launch mode: ${profile.requireGui ? "GUI" : "Headless"} · Camera: ${profile.requireCamera ? "On" : "Optional"}\n` +
      `${template.launchNotes || "Preset defaults have been applied to the operator controls."}`;
  }
}

function renderTemplates() {
  if (!dom.templateGrid) return;
  const templates = state.simulationTemplates.length ? state.simulationTemplates : DEFAULT_SIMULATION_TEMPLATES;
  dom.templateGrid.innerHTML = templates
    .map((template) => {
      const kicker = template.recommended ? "Recommended" : "Simulation template";
      const tags = template.tags.length ? template.tags.join(" · ") : (template.requireGui ? "GUI" : "Headless");
      const activeClass = template.templateId === state.selectedTemplateId ? " is-active" : "";
      return `
        <button type="button" class="template-card${activeClass}" data-template-id="${escapeHtml(template.templateId)}">
          <small>${escapeHtml(kicker)}</small>
          <strong>${escapeHtml(template.name)}</strong>
          <span>${escapeHtml(template.description)}</span>
          <small>${escapeHtml(tags)}</small>
        </button>
      `;
    })
    .join("");
  dom.templateGrid.querySelectorAll("[data-template-id]").forEach((button) => {
    button.addEventListener("click", () => {
      selectSimulationTemplate(button.getAttribute("data-template-id") || "");
    });
  });
}

function loadSimulationTemplates(rawTemplates) {
  const normalized = Array.isArray(rawTemplates) ? rawTemplates.map(normalizeTemplate).filter(Boolean) : [];
  state.simulationTemplates = normalized.length ? normalized : DEFAULT_SIMULATION_TEMPLATES.map((template) => ({ ...template }));
  const savedTemplate = storageGet(STORAGE_KEYS.selectedTemplate, "");
  const savedLaunchProfile = storageGet(STORAGE_KEYS.launchProfile, null) || state.config?.runtime_profile || null;
  const preferred =
    state.simulationTemplates.find((template) => template.templateId === savedTemplate)?.templateId ||
    state.simulationTemplates.find((template) => template.recommended)?.templateId ||
    state.simulationTemplates[0]?.templateId ||
    "";
  if (savedLaunchProfile) {
    syncLaunchProfile(normalizeLaunchProfile(savedLaunchProfile), false);
    selectSimulationTemplate(preferred, false, false);
    return;
  }
  selectSimulationTemplate(preferred, false, true);
}

function telemetryFromText(text) {
  const result = {
    connected: /Connected:\s*yes/i.test(text),
    armed: /Armed:\s*yes/i.test(text),
    inAir: /In Air:\s*yes/i.test(text),
    lat: null,
    lon: null,
    absAlt: null,
    relAlt: null,
    battery: null,
    flightMode: null,
  };

  const position = text.match(/Position:\s*([-\d.]+)°([NS]),\s*([-\d.]+)°([EW])/i);
  if (position) {
    const lat = Number(position[1]);
    const lon = Number(position[3]);
    result.lat = position[2].toUpperCase() === "S" ? -lat : lat;
    result.lon = position[4].toUpperCase() === "W" ? -lon : lon;
  }

  const absAlt = text.match(/Absolute Altitude:\s*([-\d.]+)\s*m/i);
  if (absAlt) result.absAlt = Number(absAlt[1]);
  const relAlt = text.match(/Relative Altitude:\s*([-\d.]+)\s*m/i);
  if (relAlt) result.relAlt = Number(relAlt[1]);
  const battery = text.match(/Battery:\s*([-\d.]+)\s*%/i);
  if (battery) result.battery = Number(battery[1]);
  const mode = text.match(/Flight Mode:\s*(.+)$/im);
  if (mode) result.flightMode = mode[1].trim();

  return result;
}

function telemetryFromObject(payload) {
  const source = payload?.telemetry || payload?.drone || payload?.status || payload || {};
  const lat = Number(source.lat ?? source.latitude ?? source.latitude_deg ?? source.lat_deg);
  const lon = Number(source.lon ?? source.lng ?? source.longitude ?? source.longitude_deg ?? source.lon_deg);
  const absAlt = Number(
    source.absAlt ?? source.absolute_altitude_m ?? source.altitude_m ?? source.altitude ?? source.absoluteAltitude,
  );
  const relAlt = Number(source.relAlt ?? source.relative_altitude_m ?? source.relativeAltitude ?? source.relativeAltitudeM);
  const battery = Number(source.battery ?? source.battery_percent ?? source.batteryPercent);
  const mode = source.flight_mode ?? source.flightMode ?? source.mode ?? source.state;

  return {
    connected: source.connected !== false,
    armed: Boolean(source.armed),
    inAir: Boolean(source.inAir ?? source.in_air),
    lat: Number.isFinite(lat) ? lat : null,
    lon: Number.isFinite(lon) ? lon : null,
    absAlt: Number.isFinite(absAlt) ? absAlt : null,
    relAlt: Number.isFinite(relAlt) ? relAlt : null,
    battery: Number.isFinite(battery) ? battery : null,
    flightMode: mode != null ? String(mode) : null,
    speed: Number(source.speed ?? source.speed_m_s ?? source.speedMps),
    heading: Number(source.heading ?? source.heading_deg ?? source.headingDeg),
  };
}

function synthesizeTelemetry(next, previous) {
  const now = Date.now();
  const telemetry = { ...next };
  if (!Number.isFinite(telemetry.speed) || telemetry.speed == null) {
    if (previous && previous.lat != null && previous.lon != null && telemetry.lat != null && telemetry.lon != null) {
      const seconds = Math.max((now - (state.lastTelemetryAt || now)) / 1000, 0.001);
      const distance = haversineMeters(
        { lat: previous.lat, lon: previous.lon },
        { lat: telemetry.lat, lon: telemetry.lon },
      );
      telemetry.speed = distance / seconds;
    }
  }
  if (!Number.isFinite(telemetry.heading) || telemetry.heading == null) {
    if (previous && previous.lat != null && previous.lon != null && telemetry.lat != null && telemetry.lon != null) {
      telemetry.heading = bearingDegrees(
        { lat: previous.lat, lon: previous.lon },
        { lat: telemetry.lat, lon: telemetry.lon },
      );
    }
  }
  return telemetry;
}

function formatTelemetryText(telemetry) {
  if (!telemetry) return "No drone telemetry available yet.";
  return [
    `Connected: ${telemetry.connected ? "yes" : "no"}`,
    `Armed: ${telemetry.armed ? "yes" : "no"}`,
    `In Air: ${telemetry.inAir ? "yes" : "no"}`,
    `Position: ${formatCoordinate(telemetry.lat)}°, ${formatCoordinate(telemetry.lon)}°`,
    `Absolute Altitude: ${formatNumber(telemetry.absAlt, 1)} m`,
    `Relative Altitude: ${formatNumber(telemetry.relAlt, 1)} m`,
    `Battery: ${formatNumber(telemetry.battery, 0)}%`,
    `Flight Mode: ${safeText(telemetry.flightMode)}`,
    `Speed: ${formatNumber(telemetry.speed, 1)} m/s`,
    `Heading: ${formatNumber(telemetry.heading, 0)}°`,
  ].join("\n");
}

function updateHud(telemetry) {
  if (!telemetry) return;
  if (dom.hudAltitude) dom.hudAltitude.textContent = `${formatNumber(telemetry.relAlt ?? telemetry.absAlt, 1)} m`;
  if (dom.hudSpeed) dom.hudSpeed.textContent = `${formatNumber(telemetry.speed, 1)} m/s`;
  if (dom.hudBattery) dom.hudBattery.textContent = `${formatNumber(telemetry.battery, 0)}%`;
  if (dom.hudMode) dom.hudMode.textContent = safeText(telemetry.flightMode);
  if (dom.hudGps) dom.hudGps.textContent = formatGpsPoint(telemetry.lat, telemetry.lon);
  if (dom.hudArmed) dom.hudArmed.textContent = telemetry.armed ? "Armed" : "Disarmed";
  if (dom.compassArrow && Number.isFinite(telemetry.heading)) {
    dom.compassArrow.style.transform = `rotate(${telemetry.heading}deg)`;
  }
}

function waypointIcon(label, color) {
  if (!window.L) return null;
  return window.L.divIcon({
    className: "drone-waypoint-icon",
    html: `
      <div style="
        width: 22px;
        height: 22px;
        border-radius: 999px;
        background: ${color};
        border: 2px solid rgba(255,255,255,0.95);
        box-shadow: 0 4px 12px rgba(0,0,0,0.28);
        display: grid;
        place-items: center;
        color: #fff;
        font-size: 10px;
        font-weight: 800;
      ">${label}</div>
    `,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function droneIcon(color) {
  if (!window.L) return null;
  return window.L.divIcon({
    className: "drone-current-icon",
    html: `
      <div style="
        width: 18px;
        height: 18px;
        border-radius: 999px;
        background: ${color};
        border: 2px solid rgba(255,255,255,0.9);
        box-shadow: 0 0 0 8px rgba(93, 211, 255, 0.16);
      "></div>
    `,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function initMap() {
  if (!dom.waypointMap || !window.L || state.mapReady || state.mapFailed) return;

  try {
    state.map = window.L.map(dom.waypointMap, {
      zoomControl: true,
      attributionControl: true,
    }).setView([state.latitudeFallback, state.longitudeFallback], 17);

    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 20,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(state.map);

    state.waypointLayer = window.L.layerGroup().addTo(state.map);
    state.missionLayer = window.L.layerGroup().addTo(state.map);
    state.recordingLayer = window.L.layerGroup().addTo(state.map);

    state.map.on("click", (event) => {
      addWaypoint({
        lat: event.latlng.lat,
        lon: event.latlng.lng,
        alt: Number(dom.wpAlt?.value || 10),
        yaw: Number(dom.wpYaw?.value || 0),
      });
    });

    state.mapReady = true;
    dom.waypointMap.classList.add("map-canvas-ready");
    if (dom.mapFallback) dom.mapFallback.classList.add("is-hidden");
    renderMapState();
  } catch (error) {
    state.mapFailed = true;
    dom.waypointMap.classList.add("is-fallback");
    if (dom.mapFallback) {
      dom.mapFallback.classList.remove("is-hidden");
      dom.mapFallback.textContent = `Leaflet failed to initialize: ${error.message}`;
    }
  }
}

function setHomePosition(lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  if (!state.homePosition) {
    state.homePosition = { lat, lon };
  }
}

function getMapCenter() {
  if (state.homePosition) return [state.homePosition.lat, state.homePosition.lon];
  const firstWaypoint = state.waypoints[0];
  if (firstWaypoint) return [firstWaypoint.lat, firstWaypoint.lon];
  return [state.latitudeFallback, state.longitudeFallback];
}

function centerMap() {
  if (!state.mapReady || !state.map) return;
  state.map.setView(getMapCenter(), Math.max(state.map.getZoom(), 16));
}

function addWaypoint(raw) {
  const waypoint = normalizeWaypoint(raw, state.waypoints.length);
  if (!waypoint) return;
  state.waypoints.push(waypoint);
  saveWaypoints();
  renderWaypoints();
  renderMapState();
}

function removeWaypoint(id) {
  state.waypoints = state.waypoints.filter((wp) => wp.id !== id);
  saveWaypoints();
  renderWaypoints();
  renderMapState();
}

function clearWaypoints() {
  state.waypoints = [];
  saveWaypoints();
  renderWaypoints();
  renderMapState();
}

function addCurrentPositionAsWaypoint() {
  const t = state.telemetry;
  if (!t || !Number.isFinite(t.lat) || !Number.isFinite(t.lon)) {
    statusNotice("No current drone fix available to add.");
    return;
  }
  addWaypoint({
    lat: t.lat,
    lon: t.lon,
    alt: Number.isFinite(t.relAlt) ? t.relAlt : Number(dom.wpAlt?.value || 10),
    yaw: Number(dom.wpYaw?.value || 0),
  });
}

function statusNotice(text) {
  dom.statusBox.textContent = text;
}

function renderWaypoints() {
  if (!dom.waypointList) return;
  if (!state.waypoints.length) {
    dom.waypointList.innerHTML = `<div class="meta-box">No waypoints yet. Click the map or add one manually.</div>`;
    return;
  }

  dom.waypointList.innerHTML = "";
  state.waypoints.forEach((waypoint, index) => {
    const item = document.createElement("div");
    item.className = "waypoint-item";
    item.innerHTML = `
      <div class="waypoint-copy">
        <strong>WP ${index + 1}</strong>
        <span>${formatGpsPoint(waypoint.lat, waypoint.lon)} · ${formatNumber(waypoint.alt, 1)} m · yaw ${formatNumber(waypoint.yaw, 0)}°</span>
      </div>
      <div class="waypoint-actions">
        <button type="button" class="small-ghost" data-fly-waypoint="${waypoint.id}">Fly</button>
        <button type="button" class="small-ghost" data-remove-waypoint="${waypoint.id}">Remove</button>
      </div>
    `;
    dom.waypointList.appendChild(item);
  });

  dom.waypointList.querySelectorAll("[data-remove-waypoint]").forEach((button) => {
    button.addEventListener("click", () => removeWaypoint(button.getAttribute("data-remove-waypoint")));
  });

  dom.waypointList.querySelectorAll("[data-fly-waypoint]").forEach((button) => {
    button.addEventListener("click", async () => {
      const waypoint = state.waypoints.find((wp) => wp.id === button.getAttribute("data-fly-waypoint"));
      if (!waypoint) return;
      await executeWaypoint(waypoint);
    });
  });
}

function renderRecordings() {
  if (!dom.recordingList) return;
  if (!state.recordings.length) {
    dom.recordingList.innerHTML = `<div class="meta-box">No saved recordings yet.</div>`;
    return;
  }

  dom.recordingList.innerHTML = "";
  state.recordings
    .slice()
    .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
    .forEach((recording) => {
      const item = document.createElement("div");
      item.className = "recording-item";
      item.innerHTML = `
        <div class="recording-copy">
          <strong>${recording.name || "Flight recording"}</strong>
          <span>${new Date(recording.createdAt || Date.now()).toLocaleString()} · ${recording.points?.length || 0} points</span>
        </div>
        <div class="recording-actions">
          <button type="button" class="small-ghost" data-view-recording="${recording.id}">View</button>
        </div>
      `;
      dom.recordingList.appendChild(item);
    });

  dom.recordingList.querySelectorAll("[data-view-recording]").forEach((button) => {
    button.addEventListener("click", () => {
      const recording = state.recordings.find((entry) => entry.id === button.getAttribute("data-view-recording"));
      if (recording) {
        state.selectedRecordingId = recording.id;
        renderRecordingTrack(recording);
        renderRecordingSummary(recording);
      }
    });
  });
}

function renderRecordingSummary(recording = null) {
  if (!dom.recordingSummary) return;
  if (state.activeRecording) {
    dom.recordingSummary.textContent = `Recording live: ${state.activeRecording.points.length} samples captured.`;
    return;
  }
  if (!recording) {
    dom.recordingSummary.textContent = "No active recording.";
    return;
  }
  dom.recordingSummary.textContent =
    `${recording.name || "Recording"} · ${recording.points?.length || 0} samples · ` +
    `${new Date(recording.createdAt || Date.now()).toLocaleString()}`;
}

function renderRecordingTrack(recording) {
  if (!state.mapReady || !state.map || !recording?.points?.length) return;
  state.recordingLayer?.clearLayers();
  const points = recording.points
    .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
    .map((point) => [point.lat, point.lon]);
  if (points.length < 2) return;
  window.L.polyline(points, {
    color: "#ffbe55",
    weight: 3,
    opacity: 0.9,
    dashArray: "5 8",
  }).addTo(state.recordingLayer);
}

function pushFlightTrackPoint(telemetry) {
  if (!telemetry || !Number.isFinite(telemetry.lat) || !Number.isFinite(telemetry.lon)) return;
  const nextPoint = [telemetry.lat, telemetry.lon];
  const previous = state.currentTrack[state.currentTrack.length - 1];
  if (previous) {
    const separation = haversineMeters(
      { lat: previous[0], lon: previous[1] },
      { lat: nextPoint[0], lon: nextPoint[1] },
    );
    if (separation < 0.8) return;
  }
  state.currentTrack.push(nextPoint);
  if (state.currentTrack.length > 500) {
    state.currentTrack = state.currentTrack.slice(-500);
  }
}

function renderMapState() {
  if (!state.mapReady || !state.map) return;

  state.waypointLayer?.clearLayers();
  state.missionLayer?.clearLayers();

  const center = getMapCenter();
  if (!state.homePosition) {
    state.homePosition = { lat: center[0], lon: center[1] };
  }

  if (state.homePosition) {
    window.L.marker([state.homePosition.lat, state.homePosition.lon], {
      icon: waypointIcon("H", "rgba(255, 190, 85, 1)"),
    }).addTo(state.missionLayer);

    window.L.circle([state.homePosition.lat, state.homePosition.lon], {
      radius: Number(state.geofence.maxDistanceM || DEFAULT_GEOFENCE.maxDistanceM),
      color: "rgba(255, 190, 85, 0.9)",
      fillColor: "rgba(255, 190, 85, 0.15)",
      fillOpacity: 0.16,
      weight: 2,
    }).addTo(state.missionLayer);
  }

  state.waypoints.forEach((waypoint, index) => {
    window.L.marker([waypoint.lat, waypoint.lon], {
      icon: waypointIcon(String(index + 1), "rgba(93, 211, 255, 1)"),
    }).addTo(state.waypointLayer);
  });

  if (state.waypoints.length > 1) {
    window.L.polyline(
      state.waypoints.map((waypoint) => [waypoint.lat, waypoint.lon]),
      { color: "#5dd3ff", weight: 3, opacity: 0.8 },
    ).addTo(state.waypointLayer);
  }

  if (state.telemetry && Number.isFinite(state.telemetry.lat) && Number.isFinite(state.telemetry.lon)) {
    window.L.marker([state.telemetry.lat, state.telemetry.lon], {
      icon: droneIcon("rgba(60, 211, 140, 1)"),
    }).addTo(state.missionLayer);

    if (state.currentTrack.length > 1) {
      window.L.polyline(state.currentTrack, {
        color: "#3cd38c",
        weight: 3,
        opacity: 0.7,
      }).addTo(state.missionLayer);
    }
  }

  if (state.selectedRecordingId) {
    const recording = state.recordings.find((entry) => entry.id === state.selectedRecordingId);
    if (recording) renderRecordingTrack(recording);
  }
}

function captureRecordingSample(telemetry) {
  if (!state.activeRecording || !telemetry) return;
  state.activeRecording.points.push({
    lat: telemetry.lat,
    lon: telemetry.lon,
    alt: telemetry.relAlt ?? telemetry.absAlt,
    battery: telemetry.battery,
    mode: telemetry.flightMode,
    timestamp: Date.now(),
  });
  renderRecordingSummary();
}

function finalizeRecording(save = true) {
  if (!state.activeRecording) return null;
  const active = state.activeRecording;
  active.finishedAt = Date.now();
  active.durationMs = active.finishedAt - active.createdAt;
  if (save) {
    state.recordings = [active, ...state.recordings.filter((entry) => entry.id !== active.id)].slice(0, 20);
    saveRecordings();
  }
  state.activeRecording = null;
  renderRecordingSummary();
  renderRecordings();
  return active;
}

function hydrateRecordingTelemetry(telemetry) {
  if (!telemetry) return;
  state.telemetry = telemetry;
  state.lastTelemetry = telemetry;
  state.lastTelemetryAt = Date.now();
  if (Number.isFinite(telemetry.lat) && Number.isFinite(telemetry.lon)) {
    setHomePosition(telemetry.lat, telemetry.lon);
    pushFlightTrackPoint(telemetry);
    if (Number.isFinite(telemetry.relAlt) && dom.wpAlt) {
      dom.wpAlt.value = String(Math.max(1, Math.round(telemetry.relAlt)));
    }
  }
  captureRecordingSample(telemetry);
  updateHud(telemetry);
  state.telemetryText = formatTelemetryText(telemetry);
  dom.statusBox.textContent = [state.runtimeText, state.telemetryText].filter(Boolean).join("\n\n");
  renderMapState();
}

function ingestTelemetry(payload, source = "poll") {
  let telemetry = null;
  let rawText = null;
  if (typeof payload === "string") {
    rawText = payload;
    telemetry = telemetryFromText(payload);
  } else if (payload && typeof payload === "object") {
    if (payload.text && typeof payload.text === "string" && Object.keys(payload).length <= 2) {
      rawText = payload.text;
      telemetry = telemetryFromText(payload.text);
    } else {
      telemetry = telemetryFromObject(payload);
      if (typeof payload.text === "string") rawText = payload.text;
    }
  }

  if (!telemetry) return null;
  telemetry = synthesizeTelemetry(telemetry, state.lastTelemetry);
  telemetry.source = source;
  state.telemetry = telemetry;
  state.lastTelemetry = telemetry;
  state.lastTelemetryAt = Date.now();
  if (Number.isFinite(telemetry.lat) && Number.isFinite(telemetry.lon)) {
    setHomePosition(telemetry.lat, telemetry.lon);
    pushFlightTrackPoint(telemetry);
  }
  if (Number.isFinite(telemetry.relAlt) && dom.wpAlt) {
    dom.wpAlt.value = String(Math.max(1, Math.round(telemetry.relAlt)));
  }
  captureRecordingSample(telemetry);
  updateHud(telemetry);
  state.telemetryText = rawText || formatTelemetryText(telemetry);
  dom.statusBox.textContent = [state.runtimeText, state.telemetryText].filter(Boolean).join("\n\n");
  renderMapState();
  return telemetry;
}

function normalizeRuntimePayload(payload) {
  if (typeof payload === "string") return payload;
  if (payload && typeof payload.text === "string") return payload.text;
  if (payload && typeof payload.status_text === "string") return payload.status_text;
  if (payload && typeof payload.status === "string") return payload.status;
  return payload ? JSON.stringify(payload, null, 2) : "";
}

function applyRuntimeText(text) {
  state.runtimeText = text;
  updateBadgeFromText(text);
  if (text.includes("GUI Ready: yes") || text.includes("Ready: yes")) {
    hideLoadingOverlay();
  } else if (text.includes("Running: yes")) {
    setLoadingState("Simulation is starting on the server…");
  } else {
    setLoadingState("Simulation not started. Click Start or ask the chat.");
  }
  dom.statusBox.textContent = [state.runtimeText, state.telemetryText].filter(Boolean).join("\n\n");
}

function renderConnectionState(connection, source = state.statusMode) {
  const mode = source === "websocket" ? "websocket" : "polling";
  const latency = Number(connection?.latency_ms);
  const quality = String(connection?.quality || "");
  if (quality === "offline") {
    updateConnectionQuality(mode, "Offline", "quality-bad");
    return;
  }
  if (quality === "poor" || quality === "fair" || quality === "unknown") {
    const label = Number.isFinite(latency)
      ? `${mode === "websocket" ? "Live" : "Poll"} ${Math.round(latency)}ms`
      : (mode === "websocket" ? "Live" : "Polling");
    updateConnectionQuality(mode, label, "quality-warn");
    return;
  }
  const label = Number.isFinite(latency)
    ? `${mode === "websocket" ? "Live" : "Poll"} ${Math.round(latency)}ms`
    : (mode === "websocket" ? "WS live" : "Polling");
  updateConnectionQuality(mode, label, mode === "websocket" ? "quality-live" : "quality-polling");
}

function renderTrackingStatus(tracking = state.tracking) {
  state.tracking = tracking && typeof tracking === "object" ? tracking : null;
  if (!dom.trackingStatus) return;
  if (!state.tracking) {
    dom.trackingStatus.textContent = "Tracking is idle.";
    return;
  }
  const observation = state.tracking.last_observation || {};
  const command = state.tracking.last_command || {};
  const observationText = observation.detected
    ? `${safeText(observation.target_class, "target")} @ ${formatNumber(observation.confidence, 2)}`
    : "not detected";
  dom.trackingStatus.textContent = `Tracking ${state.tracking.active ? "active" : "idle"} · ${
    state.tracking.authorized ? "authorized" : "paused"
  }
Target: ${safeText(state.tracking.target_class, "person")} · Backend: ${safeText(state.tracking.detector_backend, "n/a")}
Steps: ${Number(state.tracking.step_count || 0)} · Observation: ${observationText}
Last command: ${safeText(command.mode, "idle")} · fwd ${formatNumber(command.forward_m_s, 1)} · yaw ${formatNumber(command.yaw_rate_deg_s, 0)}
${state.tracking.last_error ? `Note: ${state.tracking.last_error}` : "Server-side tracker is ready for follow-loop work."}`;
}

function applyStatusSnapshot(snapshot, source = "poll") {
  if (!snapshot || typeof snapshot !== "object") return null;
  state.statusSnapshot = snapshot;
  const droneId = String(
    snapshot.drone_id
      ?? snapshot.selected_drone_id
      ?? snapshot.drone?.drone_id
      ?? snapshot.active_drone?.drone_id
      ?? state.selectedDroneId
      ?? "",
  ).trim();
  if (droneId) {
    state.selectedDroneId = droneId;
    if (dom.droneSelector) {
      dom.droneSelector.innerHTML = `<option value="${escapeHtml(droneId)}">${escapeHtml(droneId)}</option>`;
      dom.droneSelector.value = droneId;
    }
  }
  if (snapshot.runtime || snapshot.runtime_text) {
    applyRuntimeText(snapshot.runtime_text || normalizeRuntimePayload(snapshot.runtime));
  }
  if (snapshot.runtime_profile && !state.launchProfile) {
    syncLaunchProfile(normalizeLaunchProfile(snapshot.runtime_profile), true);
  }
  if (snapshot.geofence) {
    syncGeofenceState(snapshot.geofence, true);
  }
  if (Array.isArray(snapshot.recordings)) {
    syncRecordingsState(snapshot.recordings, true);
  }
  if (snapshot.tracking || snapshot.autonomy) {
    renderTrackingStatus(snapshot.tracking || snapshot.autonomy);
  }
  renderSessionSummary();
  if (snapshot.connection) {
    renderConnectionState(snapshot.connection, source);
  }
  const telemetryPayload = snapshot.telemetry || snapshot.drone || snapshot.status || snapshot.selected_status;
  if (telemetryPayload) {
    return ingestTelemetry(telemetryPayload, source);
  }
  dom.statusBox.textContent = [state.runtimeText, state.telemetryText].filter(Boolean).join("\n\n");
  return null;
}

async function refreshStatusSnapshot(source = "poll") {
  const startedAt = performance.now();
  const query = state.selectedDroneId ? `?drone_id=${encodeURIComponent(state.selectedDroneId)}` : "";
  const attempts = [
    async () => fetchJson(`/api/status${query}`, {}, 12000),
    async () => {
      const [runtime, telemetry] = await Promise.all([
        fetchJson("/api/runtime-health", {}, 12000),
        fetchJson(`/api/drone/status${query}`, {}, 10000),
      ]);
      return {
        runtime_text: normalizeRuntimePayload(runtime),
        telemetry,
      };
    },
    async () => callTool("get_drone_status", activeDronePayload(), false),
  ];

  for (const attempt of attempts) {
    try {
      const result = await attempt();
      if (result && typeof result === "object" && "ok" in result) {
        const latency = Math.round(performance.now() - startedAt);
        const telemetry = ingestTelemetry(result.text, source);
        renderConnectionState({ latency_ms: latency, quality: telemetry?.connected ? "good" : "offline" }, source);
        return telemetry;
      }
      const telemetry = applyStatusSnapshot(result, source) || ingestTelemetry(result, source);
      if (telemetry || result?.runtime || result?.runtime_text) {
        if (!(result && typeof result === "object" && result.connection)) {
          const latency = Math.round(performance.now() - startedAt);
          renderConnectionState({ latency_ms: latency, quality: telemetry?.connected ? "good" : "unknown" }, source);
        }
        return telemetry;
      }
    } catch {
      // Try the next endpoint.
    }
  }

  state.runtimeText = "Connection error: unable to reach the operator server.";
  dom.statusBox.textContent = [state.runtimeText, state.telemetryText].filter(Boolean).join("\n\n");
  updateBadgeFromText("");
  updateConnectionQuality("polling", "Offline", "quality-bad");
  return null;
}

async function refreshRuntimeHealth() {
  return refreshStatusSnapshot("poll");
}

async function refreshDroneTelemetry(source = "poll") {
  return refreshStatusSnapshot(source);
}

function stopPolling() {
  if (state.statusPollTimer) window.clearInterval(state.statusPollTimer);
  if (state.telemetryPollTimer) window.clearInterval(state.telemetryPollTimer);
  if (state.healthPollTimer) window.clearInterval(state.healthPollTimer);
  state.statusPollTimer = null;
  state.telemetryPollTimer = null;
  state.healthPollTimer = null;
}

function startPollingFallback() {
  stopPolling();
  state.statusMode = "polling";
  updateConnectionQuality("polling", "Polling", "quality-polling");
  state.statusPollTimer = window.setInterval(() => {
    void refreshStatusSnapshot("poll");
  }, 2500);
  state.healthPollTimer = window.setInterval(() => {
    void refreshStatusSnapshot("poll");
  }, 12000);
  void refreshStatusSnapshot("poll");
}

function wsCandidates() {
  const candidates = [];
  const base = window.location.origin.replace(/^http/i, window.location.protocol === "https:" ? "wss" : "ws");
  [
    state.config.ws_url,
    state.config.websocket_url,
    state.config.status_ws_url,
    state.config.live_status_ws_url,
  ].forEach((value) => {
    if (typeof value !== "string" || !value.trim()) return;
    const trimmed = value.trim();
    candidates.push(trimmed.startsWith("/") ? `${base}${trimmed}` : trimmed);
  });
  candidates.push(`${base}/ws/status`, `${base}/ws`, `${base}/api/ws/status`);
  return [...new Set(candidates)];
}

function openStatusSocket() {
  if (!window.WebSocket) return false;
  if (state.statusSocket) {
    try {
      state.statusSocket.close();
    } catch {
      // ignore
    }
  }

  const candidates = wsCandidates();
  let index = 0;

  const tryNext = () => {
    if (index >= candidates.length) {
      startPollingFallback();
      return;
    }
    const url = candidates[index++];
    try {
      const socket = new WebSocket(url);
      let opened = false;
      socket.onopen = () => {
        opened = true;
        state.statusSocket = socket;
        state.statusMode = "websocket";
        updateConnectionQuality("websocket", "WS live", "quality-live");
        if (state.selectedDroneId) {
          socket.send(JSON.stringify({ drone_id: state.selectedDroneId }));
        }
      };
      socket.onmessage = (event) => {
        const payload = parseMaybeJson(event.data);
        applyStatusSnapshot(payload, "websocket");
        dom.statusBox.textContent = [state.runtimeText, state.telemetryText].filter(Boolean).join("\n\n");
      };
      socket.onerror = () => {
        if (!opened) socket.close();
      };
      socket.onclose = () => {
        if (state.statusSocket === socket) state.statusSocket = null;
        if (index < candidates.length) {
          tryNext();
          return;
        }
        startPollingFallback();
      };
      state.statusSocket = socket;
    } catch {
      tryNext();
    }
  };

  tryNext();
  return true;
}

async function callTool(name, argumentsPayload = {}, refreshAfter = true) {
  if (!name) return { ok: false, text: "Missing tool name." };
  let effectiveArguments = { ...argumentsPayload };
  if (name === "start_simulation" || name === "reset_simulation") {
    effectiveArguments = { ...runtimeTemplateArguments(), ...argumentsPayload };
  }
  if (name === "start_simulation") showLoadingOverlay("Starting simulation…");
  if (name === "reset_simulation") showLoadingOverlay("Resetting simulation…");
  if (dom.statusBox) dom.statusBox.textContent = `Running ${name}…`;
  const startedAt = performance.now();
  try {
    const data = await fetchJson(
      "/api/tool",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, arguments: effectiveArguments }),
      },
      20000,
    );
    const text = parseToolResponse(data);
    dom.statusBox.textContent = text;
    const latency = Math.round(performance.now() - startedAt);
    updateConnectionQuality(
      state.statusMode === "websocket" ? "websocket" : "polling",
      state.statusMode === "websocket" ? `WS ${latency}ms` : `Poll ${latency}ms`,
      state.statusMode === "websocket" ? "quality-live" : "quality-polling",
    );
    if (refreshAfter) {
      await refreshStatusSnapshot("poll");
    }
    return { ok: true, data, text };
  } catch (error) {
    const text = `Error: ${error.message}`;
    dom.statusBox.textContent = text;
    if (refreshAfter) {
      await refreshStatusSnapshot("poll");
    }
    return { ok: false, text };
  }
}

async function sendToolQuietly(name, argumentsPayload = {}) {
  if (!name) return { ok: false, text: "Missing tool name." };
  try {
    const data = await fetchJson(
      "/api/tool",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, arguments: argumentsPayload }),
      },
      12000,
    );
    return { ok: true, data, text: parseToolResponse(data) };
  } catch (error) {
    return { ok: false, text: `Error: ${error.message}` };
  }
}

async function executeWaypoint(waypoint) {
  const payload = activeDronePayload({
    latitude: waypoint.lat,
    longitude: waypoint.lon,
    altitude: waypoint.alt,
    yaw: waypoint.yaw,
  });
  return callTool("go_to_location", payload, true);
}

function hasReachedWaypoint(waypoint, telemetry = state.telemetry) {
  if (!telemetry || !Number.isFinite(telemetry.lat) || !Number.isFinite(telemetry.lon)) return false;
  const distance = haversineMeters(
    { lat: telemetry.lat, lon: telemetry.lon },
    { lat: waypoint.lat, lon: waypoint.lon },
  );
  const altitude = telemetry.relAlt ?? telemetry.absAlt;
  const altitudeError = Number.isFinite(altitude) ? Math.abs(altitude - waypoint.alt) : Infinity;
  return distance <= 8 && altitudeError <= 4;
}

async function waitForWaypoint(waypoint, timeoutMs = 180000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    await refreshDroneTelemetry("poll");
    if (hasReachedWaypoint(waypoint)) {
      return true;
    }
    if (state.missionAbort) {
      return false;
    }
    await sleep(2000);
  }
  return false;
}

async function executeMission() {
  if (state.missionRunning) {
    state.missionAbort = true;
    dom.btnExecuteMission.textContent = "Cancel mission";
    dom.statusBox.textContent = "Mission cancel requested.";
    return;
  }
  if (!state.waypoints.length) {
    dom.statusBox.textContent = "No waypoints to execute.";
    return;
  }

  await stopManualControl(false);
  await sendToolQuietly("stop_visual_tracking", activeDronePayload());
  state.missionRunning = true;
  state.missionAbort = false;
  dom.btnExecuteMission.textContent = "Cancel mission";
  dom.statusBox.textContent = `Executing ${state.waypoints.length} waypoints…`;

  for (let index = 0; index < state.waypoints.length; index += 1) {
    if (state.missionAbort) break;
    const waypoint = state.waypoints[index];
    dom.statusBox.textContent = `Waypoint ${index + 1}/${state.waypoints.length}: ${formatGpsPoint(waypoint.lat, waypoint.lon)}`;
    const result = await executeWaypoint(waypoint);
    if (!result.ok) {
      dom.statusBox.textContent = result.text;
      break;
    }
    const reached = await waitForWaypoint(waypoint);
    if (!reached && !state.missionAbort) {
      dom.statusBox.textContent = `Timed out before reaching waypoint ${index + 1}.`;
      break;
    }
  }

  state.missionRunning = false;
  state.missionAbort = false;
  dom.btnExecuteMission.textContent = "Execute mission";
  await refreshDroneTelemetry("poll");
}

function applyGeofence() {
  const geofence = {
    maxAltitudeM: clamp(Number(dom.geoAlt.value || DEFAULT_GEOFENCE.maxAltitudeM), 1, 10000),
    maxDistanceM: clamp(Number(dom.geoDistance.value || DEFAULT_GEOFENCE.maxDistanceM), 1, 100000),
    minBatteryPercent: clamp(Number(dom.geoBattery.value || DEFAULT_GEOFENCE.minBatteryPercent), 1, 100),
  };
  state.geofence = geofence;
  saveGeofence();
  renderMapState();
  dom.statusBox.textContent = `Geofence set locally:
Max altitude: ${geofence.maxAltitudeM} m
Max distance: ${geofence.maxDistanceM} m
RTL battery: ${geofence.minBatteryPercent}%`;
  void callTool("set_geofence", activeDronePayload({ ...geofence }), false);
}

async function refreshCameraFrame() {
  if (!dom.cameraFrame) return false;
  const profile = getActiveLaunchProfile();
  const cameraQuery = profile.cameraTopic ? `?topic=${encodeURIComponent(profile.cameraTopic)}` : "";
  const attempts = [
    async () => fetchJson(`/api/camera-frame${cameraQuery}`, {}, 12000),
    async () => fetchJson("/api/camera/frame", {}, 12000),
    async () => callTool("get_camera_frame", activeDronePayload({
      format: "base64",
      topic: profile.cameraTopic || "",
    }), false),
  ];

  for (const attempt of attempts) {
    try {
      const result = await attempt();
      const payload = parseMaybeJson(result?.data ?? result);
      let image = null;
      let mime = "image/jpeg";
      if (typeof payload === "string" && /^data:image\//.test(payload)) {
        image = payload;
      } else if (typeof payload === "string") {
        image = payload.startsWith("http") ? payload : `data:image/jpeg;base64,${payload}`;
      } else if (payload && typeof payload === "object") {
        image = payload.data_url || payload.image_url || payload.imageData || payload.image_base64 || payload.frame || payload.base64 || null;
        mime = payload.mime_type || payload.mime || mime;
        if (image && !/^data:image\//.test(image)) {
          image = `data:${mime};base64,${image}`;
        }
      }

      if (image) {
        dom.cameraFrame.src = image;
        dom.cameraFrame.style.display = "block";
        dom.cameraPlaceholder.classList.add("is-hidden");
        dom.cameraMeta.textContent = `Camera frame refreshed at ${new Date().toLocaleTimeString()}.`;
        return true;
      }
    } catch {
      // Try the next endpoint.
    }
  }

  dom.cameraFrame.removeAttribute("src");
  dom.cameraFrame.style.display = "none";
  dom.cameraPlaceholder.classList.remove("is-hidden");
  dom.cameraMeta.textContent = "Camera feed unavailable. The UI will recover automatically if the backend exposes a frame endpoint.";
  return false;
}

function setCameraFitMode() {
  if (!dom.cameraFrame) return;
  const current = dom.cameraFrame.style.objectFit || "contain";
  dom.cameraFrame.style.objectFit = current === "contain" ? "cover" : "contain";
  dom.cameraMeta.textContent = `Camera fit mode: ${dom.cameraFrame.style.objectFit}.`;
}

function startRecording() {
  if (state.activeRecording) return;
  const name = `Flight ${new Date().toLocaleString()}`;
  state.activeRecording = {
    id: `rec-${Date.now()}`,
    name,
    createdAt: Date.now(),
    points: [],
  };
  renderRecordingSummary();
  void callTool("start_recording", activeDronePayload({ name }), false);
}

function finalizeRecording(save = true) {
  if (!state.activeRecording) return null;
  const active = state.activeRecording;
  active.finishedAt = Date.now();
  active.durationMs = active.finishedAt - active.createdAt;
  if (save) {
    state.recordings = [active, ...state.recordings.filter((entry) => entry.id !== active.id)].slice(0, 20);
    saveRecordings();
  }
  state.activeRecording = null;
  renderRecordingSummary();
  renderRecordings();
  return active;
}

function stopRecording() {
  const saved = finalizeRecording(true);
  if (saved) {
    void callTool("stop_recording", activeDronePayload({ recording_id: saved.id }), false);
  } else {
    void callTool("stop_recording", activeDronePayload(), false);
  }
}

function manualCommandPayload(commandName) {
  const speed = clamp(Number(dom.manualSpeed?.value || 0.8), 0.1, 5);
  const yawRate = clamp(Number(dom.manualYawRate?.value || 25), 1, 120);
  switch (commandName) {
    case "forward":
      return { forward_m_s: speed, right_m_s: 0, down_m_s: 0, yaw_rate_deg_s: 0 };
    case "back":
      return { forward_m_s: -speed, right_m_s: 0, down_m_s: 0, yaw_rate_deg_s: 0 };
    case "left":
      return { forward_m_s: 0, right_m_s: -speed, down_m_s: 0, yaw_rate_deg_s: 0 };
    case "right":
      return { forward_m_s: 0, right_m_s: speed, down_m_s: 0, yaw_rate_deg_s: 0 };
    case "up":
      return { forward_m_s: 0, right_m_s: 0, down_m_s: -speed, yaw_rate_deg_s: 0 };
    case "down":
      return { forward_m_s: 0, right_m_s: 0, down_m_s: speed, yaw_rate_deg_s: 0 };
    case "yaw-left":
      return { forward_m_s: 0, right_m_s: 0, down_m_s: 0, yaw_rate_deg_s: -yawRate };
    case "yaw-right":
      return { forward_m_s: 0, right_m_s: 0, down_m_s: 0, yaw_rate_deg_s: yawRate };
    default:
      return { forward_m_s: 0, right_m_s: 0, down_m_s: 0, yaw_rate_deg_s: 0 };
  }
}

function setManualButtonState(activeCommand = "") {
  document.querySelectorAll("[data-manual-command]").forEach((button) => {
    button.classList.toggle("is-active", button.getAttribute("data-manual-command") === activeCommand);
  });
}

async function stopManualControl(updateStatus = true) {
  if (state.manualControlTimer) {
    window.clearInterval(state.manualControlTimer);
    state.manualControlTimer = null;
  }
  state.manualControlCommand = null;
  state.pressedManualKeys.clear();
  setManualButtonState("");
  const result = await sendToolQuietly("stop_body_velocity_control", activeDronePayload());
  if (updateStatus && dom.manualControlStatus) {
    dom.manualControlStatus.textContent = result.ok
      ? "Manual body control stopped."
      : result.text;
  }
}

async function startManualControl(commandName) {
  if (!commandName || commandName === "stop") {
    await stopManualControl(true);
    return;
  }
  await sendToolQuietly("stop_visual_tracking", activeDronePayload());
  if (state.manualControlTimer) {
    window.clearInterval(state.manualControlTimer);
  }
  state.manualControlCommand = commandName;
  setManualButtonState(commandName);

  const tick = async () => {
    const payload = activeDronePayload(manualCommandPayload(commandName));
    const result = await sendToolQuietly("send_body_velocity", payload);
    if (!result.ok) {
      if (dom.manualControlStatus) dom.manualControlStatus.textContent = result.text;
      await stopManualControl(false);
      return;
    }
    if (dom.manualControlStatus) {
      dom.manualControlStatus.textContent = `Manual control active: ${commandName}. Release to stop.`;
    }
  };

  await tick();
  state.manualControlTimer = window.setInterval(() => {
    void tick();
  }, 250);
}

function trackingArgumentsFromUi() {
  const profile = getActiveLaunchProfile();
  return activeDronePayload({
    target_class: dom.trackTargetClass?.value?.trim() || "person",
    confidence_threshold: String(Number(dom.trackConfidence?.value || 0.4)),
    loop_interval_s: String(Number(dom.trackLoop?.value || 0.35)),
    max_forward_speed_m_s: String(Number(dom.trackMaxForward?.value || 1.2)),
    camera_topic: profile.cameraTopic || "",
  });
}

async function runTrackingAction(name) {
  await stopManualControl(false);
  const result = await callTool(name, trackingArgumentsFromUi(), true);
  if (dom.trackingStatus) {
    dom.trackingStatus.textContent = result.text;
  }
}

function commitLaunchProfileFromForm(announce = false) {
  const envText = dom.launchEnvJson?.value?.trim() || "";
  if (envText) {
    try {
      JSON.parse(envText);
    } catch (error) {
      if (announce && dom.statusBox) {
        dom.statusBox.textContent = `Launch profile env JSON is invalid: ${error.message}`;
      }
      return false;
    }
  }
  syncLaunchProfile(readLaunchProfileFromForm(), true);
  renderTemplateSummary();
  renderSessionSummary();
  if (announce && dom.statusBox) {
    dom.statusBox.textContent = "Launch profile updated. Start or Reset will use the new server profile.";
  }
  return true;
}

function shouldIgnoreKeyboardShortcut(event) {
  const target = event.target;
  if (!target || !(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || tag === "button";
}

function manualCommandForKey(key) {
  switch (key.toLowerCase()) {
    case "w":
    case "arrowup":
      return "forward";
    case "s":
    case "arrowdown":
      return "back";
    case "a":
      return "left";
    case "d":
      return "right";
    case "q":
      return "yaw-left";
    case "e":
      return "yaw-right";
    case "r":
      return "up";
    case "f":
      return "down";
    default:
      return "";
  }
}

async function refreshRecordings() {
  const attempts = [
    async () => fetchJson("/api/recordings", {}, 10000),
    async () => callTool("list_recordings", activeDronePayload(), false),
  ];

  for (const attempt of attempts) {
    try {
      const result = await attempt();
      const payload = parseMaybeJson(result?.data ?? result);
      if (Array.isArray(payload)) {
        syncRecordingsState(payload, true);
      } else if (payload && typeof payload === "object" && Array.isArray(payload.recordings)) {
        syncRecordingsState(payload.recordings, true);
      } else {
        break;
      }
      if (state.selectedRecordingId) {
        const selected = state.recordings.find((entry) => entry.id === state.selectedRecordingId);
        if (selected) renderRecordingTrack(selected);
      }
      return true;
    } catch {
      // Try the next option or fall back to local recordings.
    }
  }

  renderRecordings();
  return false;
}

function showTab(tabName) {
  document.querySelectorAll(".panel-tab").forEach((button) => {
    const active = button.getAttribute("data-tab") === tabName;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });

  document.querySelectorAll(".panel-tab-content").forEach((panel) => {
    panel.classList.toggle("active", panel.getAttribute("data-panel") === tabName);
  });

  if (tabName === "camera") {
    void refreshCameraFrame();
  } else if (tabName === "recordings") {
    void refreshRecordings();
  }
}

function bindTabEvents() {
  document.querySelectorAll(".panel-tab").forEach((button) => {
    button.addEventListener("click", () => showTab(button.getAttribute("data-tab")));
  });
}

function bindQuickActions() {
  document.querySelectorAll("[data-tool]").forEach((button) => {
    button.addEventListener("click", async () => {
      const name = button.getAttribute("data-tool");
      const args = {};
      if (name === "get_simulation_logs") args.lines = "60";
      if (name === "connect_drone") args.address = state.config.mavsdk_address || "";
      if (name === "takeoff") args.altitude = String(Number(dom.wpAlt?.value || 5));
      await callTool(name, activeDronePayload(args), true);
    });
  });
}

function bindUiEvents() {
  dom.droneSelector?.addEventListener("change", () => {
    state.selectedDroneId = dom.droneSelector.value || "";
    storageSet(STORAGE_KEYS.selectedDrone, state.selectedDroneId);
    if (state.statusSocket && state.statusSocket.readyState === WebSocket.OPEN) {
      state.statusSocket.send(JSON.stringify({ drone_id: state.selectedDroneId }));
    }
    renderSessionSummary();
    void refreshStatusSnapshot("poll");
  });

  dom.statusToggle?.addEventListener("click", () => {
    setStatusCollapsed(!state.statusCollapsed);
  });

  dom.togglePanel?.addEventListener("click", () => {
    setPanelCollapsed(!state.panelCollapsed);
  });

  dom.themeBtn?.addEventListener("click", () => {
    setTheme(state.theme === "light" ? "dark" : "light");
  });

  dom.fullscreenBtn?.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      dom.viewport.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  });

  dom.btnCenterMap?.addEventListener("click", centerMap);
  dom.btnAddCurrent?.addEventListener("click", addCurrentPositionAsWaypoint);
  dom.btnClearWaypoints?.addEventListener("click", clearWaypoints);
  dom.btnExecuteMission?.addEventListener("click", () => {
    void executeMission();
  });
  dom.btnApplyGeofence?.addEventListener("click", applyGeofence);
  [
    dom.launchModel,
    dom.launchCameraTopic,
    dom.launchPorts,
    dom.launchEnvJson,
    dom.launchHeadless,
    dom.launchRequireGui,
    dom.launchRequireCamera,
    dom.launchNetworkHost,
  ].forEach((element) => {
    element?.addEventListener("change", () => {
      commitLaunchProfileFromForm(false);
    });
  });
  dom.btnUseTemplateProfile?.addEventListener("click", () => {
    const template = getSelectedTemplate();
    if (!template) return;
    syncLaunchProfile(launchProfileFromTemplate(template), true);
    renderTemplateSummary();
    renderSessionSummary();
    if (dom.statusBox) {
      dom.statusBox.textContent = `Launch profile reset to preset defaults for ${template.name}.`;
    }
  });
  dom.btnClearLaunchOverrides?.addEventListener("click", () => {
    if (dom.launchEnvJson) dom.launchEnvJson.value = "";
    commitLaunchProfileFromForm(true);
  });
  document.querySelectorAll("[data-manual-command]").forEach((button) => {
    const commandName = button.getAttribute("data-manual-command") || "";
    if (commandName === "stop") {
      button.addEventListener("click", () => {
        void stopManualControl(true);
      });
      return;
    }
    button.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      void startManualControl(commandName);
    });
    button.addEventListener("pointerup", () => {
      void stopManualControl(true);
    });
    button.addEventListener("pointerleave", () => {
      if (state.manualControlCommand === commandName) {
        void stopManualControl(true);
      }
    });
    button.addEventListener("pointercancel", () => {
      if (state.manualControlCommand === commandName) {
        void stopManualControl(true);
      }
    });
  });
  dom.btnRefreshCamera?.addEventListener("click", () => {
    void refreshCameraFrame();
  });
  dom.btnFitCamera?.addEventListener("click", setCameraFitMode);
  dom.btnTrackStart?.addEventListener("click", () => {
    void runTrackingAction("start_visual_tracking");
  });
  dom.btnTrackStep?.addEventListener("click", () => {
    void runTrackingAction("run_visual_tracking_step");
  });
  dom.btnTrackStop?.addEventListener("click", () => {
    void runTrackingAction("stop_visual_tracking");
  });
  dom.btnStartRecording?.addEventListener("click", startRecording);
  dom.btnStopRecording?.addEventListener("click", stopRecording);
  dom.btnRefreshRecordings?.addEventListener("click", () => {
    void refreshRecordings();
  });

  dom.waypointForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    addWaypoint({
      lat: Number(dom.wpLat.value),
      lon: Number(dom.wpLon.value),
      alt: Number(dom.wpAlt.value || 10),
      yaw: Number(dom.wpYaw.value || 0),
    });
    dom.waypointForm.reset();
    dom.wpAlt.value = "10";
    dom.wpYaw.value = "0";
  });

  dom.chatForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = dom.chatInput.value.trim();
    if (!message) return;
    appendMessage("user", message);
    dom.chatInput.value = "";

    try {
      const data = await fetchJson("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: chatHistory }),
      });
      if (!data || typeof data !== "object") {
        appendMessage("assistant", "Unexpected chat response.");
        return;
      }
      if (data.error) {
        appendMessage("assistant", `Error: ${data.error}`);
        return;
      }
      chatHistory = data.history || chatHistory;
      appendMessage("assistant", data.reply || "No reply received.");
    } catch (error) {
      appendMessage("assistant", `Connection error: ${error.message}`);
    }
    await refreshStatusSnapshot("poll");
  });

  dom.chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      dom.chatForm.dispatchEvent(new Event("submit"));
    }
  });

  document.addEventListener("keydown", (event) => {
    if (shouldIgnoreKeyboardShortcut(event)) return;
    const commandName = manualCommandForKey(event.key);
    if (!commandName || state.pressedManualKeys.has(commandName)) return;
    state.pressedManualKeys.add(commandName);
    event.preventDefault();
    void startManualControl(commandName);
  });

  document.addEventListener("keyup", (event) => {
    const commandName = manualCommandForKey(event.key);
    if (!commandName) return;
    state.pressedManualKeys.delete(commandName);
    if (state.manualControlCommand === commandName) {
      void stopManualControl(true);
    }
  });

  let swipeStart = null;
  dom.mainLayout?.addEventListener(
    "pointerdown",
    (event) => {
      if (event.pointerType !== "touch") return;
      swipeStart = { x: event.clientX, y: event.clientY, time: Date.now() };
    },
    { passive: true },
  );

  dom.mainLayout?.addEventListener(
    "pointerup",
    (event) => {
      if (!swipeStart || event.pointerType !== "touch") return;
      const dx = event.clientX - swipeStart.x;
      const dy = event.clientY - swipeStart.y;
      const elapsed = Date.now() - swipeStart.time;
      swipeStart = null;
      if (elapsed > 1000) return;
      if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy)) {
        setPanelCollapsed(!state.panelCollapsed);
      }
    },
    { passive: true },
  );
}

function initThemeFromStorage() {
  setTheme(storageGet(STORAGE_KEYS.theme, "dark"));
}

function initMobileDefaults() {
  const collapsed = window.matchMedia("(max-width: 768px)").matches
    ? Boolean(storageGet(STORAGE_KEYS.statusCollapsed, true))
    : Boolean(storageGet(STORAGE_KEYS.statusCollapsed, false));
  setStatusCollapsed(collapsed);
}

function scheduleCameraRefresh() {
  if (state.cameraTimer) window.clearInterval(state.cameraTimer);
  state.cameraTimer = window.setInterval(() => {
    if (document.querySelector('.panel-tab[data-tab="camera"]')?.classList.contains("active")) {
      void refreshCameraFrame();
    }
  }, 8000);
}

async function loadConfig() {
  try {
    const data = await fetchJson("/api/config", {}, 10000);
    state.config = data || {};
    state.configLoaded = true;
    if (dom.simFrame) dom.simFrame.src = state.config.vnc_url || "";
    if (dom.openVnc) dom.openVnc.href = state.config.vnc_url || "#";
    if (dom.chatState) {
      dom.chatState.textContent = state.config.chat_ready ? `via ${state.config.model || "model"}` : "key not set";
    }
    syncGeofenceState(state.config.geofence, false);
    if (!storageGet(STORAGE_KEYS.launchProfile, null) && state.config.runtime_profile) {
      syncLaunchProfile(normalizeLaunchProfile(state.config.runtime_profile), false);
    }
    if (state.config.tracking) {
      renderTrackingStatus(state.config.tracking);
    }
  } catch (error) {
    dom.statusBox.textContent = `Failed to load UI config: ${error.message}`;
    setLoadingState("Could not reach the operator server.");
  }

  const preferredDrone =
    String(
      state.config?.drone_id
      ?? state.config?.active_drone?.drone_id
      ?? state.config?.drone?.drone_id
      ?? storageGet(STORAGE_KEYS.selectedDrone, "")
      ?? "",
    ).trim() || "";
  state.selectedDroneId = preferredDrone;
  storageSet(STORAGE_KEYS.selectedDrone, state.selectedDroneId);
  if (dom.droneSelector) {
    dom.droneSelector.innerHTML = preferredDrone
      ? `<option value="${escapeHtml(preferredDrone)}">${escapeHtml(preferredDrone)}</option>`
      : `<option value="">Default drone</option>`;
    dom.droneSelector.value = preferredDrone;
  }

  let templates = Array.isArray(state.config?.simulation_templates) ? state.config.simulation_templates : [];
  if (!templates.length && typeof state.config?.template_catalog_url === "string" && state.config.template_catalog_url) {
    try {
      const payload = await fetchJson(state.config.template_catalog_url, {}, 10000);
      templates = Array.isArray(payload?.template_catalog)
        ? payload.template_catalog
        : (Array.isArray(payload?.simulation_templates) ? payload.simulation_templates : []);
    } catch {
      // Fall back to built-in templates below.
    }
  }
  loadSimulationTemplates(templates);
  renderSessionSummary();
}

function initMapFallbackState() {
  if (!window.L) {
    dom.waypointMap.classList.add("is-fallback");
    dom.mapFallback.classList.remove("is-hidden");
  }
}

function startTelemetryTransport() {
  if (!openStatusSocket()) {
    startPollingFallback();
  }
}

/* ── Init ─────────────────────────────────────────────────────── */
initThemeFromStorage();
loadWaypoints();
loadGeofence();
loadLaunchProfile();
loadRecordings();
ensureDefaultInputs();
bindTabEvents();
bindQuickActions();
bindUiEvents();
setPanelCollapsed(false);
initMobileDefaults();
setStatusCollapsed(state.statusCollapsed);

loadConfig()
  .then(() => {
    renderWaypoints();
    renderRecordings();
    renderRecordingSummary();
    initMap();
    initMapFallbackState();
    scheduleCameraRefresh();
    showTab("mission");
    startTelemetryTransport();
  })
  .catch((error) => {
    dom.statusBox.textContent = `Failed to initialize UI: ${error.message}`;
    setLoadingState("Could not reach the operator server.");
    startPollingFallback();
  });

window.addEventListener("resize", () => {
  initMobileDefaults();
  if (state.mapReady && state.map) {
    window.setTimeout(() => state.map?.invalidateSize(), 120);
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" && state.manualControlCommand) {
    state.pressedManualKeys.clear();
    void stopManualControl(false);
  }
  if (document.visibilityState === "visible") {
    void refreshStatusSnapshot("poll");
  }
});
