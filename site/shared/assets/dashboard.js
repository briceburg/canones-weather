import { settings } from "./common.js";
import { seasonalRows } from "./seasons.js";
import { DAY, HOUR, HOURLY_PRESET_DAYS, calendarDayOffset, historyCadence, shiftWindow, timeDomain, timelineWindow, windowFromPercent } from "./timeline.js";

const $ = (id) => document.getElementById(id);
const stationFormat = (options) => new Intl.DateTimeFormat("en-US", {timeZone: settings.station.timezone, ...options});
const dateParts = {month: "short", day: "numeric", year: "numeric"};
const timeParts = {hour: "numeric", minute: "2-digit", timeZoneName: "short"};
const dateFormat = stationFormat(dateParts);
const timeFormat = stationFormat({...dateParts, ...timeParts});
const hourFormat = stationFormat({weekday: "short", hour: "numeric"});
const recentTickFormat = stationFormat({weekday: "short", hour: "numeric", minute: "2-digit"});
const weekdayFormat = stationFormat({weekday: "short"});
const clockFormat = stationFormat({...timeParts, hour12: true, second: "2-digit"});
function renderClock() {
  const now = new Date();
  $("station-clock").dateTime = now.toISOString();
  $("station-clock").textContent = clockFormat.formatToParts(now)
    .map(({type, value}) => type === "dayPeriod" ? value.toLowerCase() : value)
    .join("");
}
renderClock();
setInterval(renderClock, 1000);
let chart;
let chartRequested = false;
const chartUpdate = {replaceMerge: ["title", "grid", "legend", "tooltip", "xAxis", "yAxis", "dataZoom", "series"]};
function sourceStyle(input) {
  const {color, pattern} = input.closest(".reference-option").dataset;
  return {color, pattern: pattern ? pattern.split(" ").map(Number) : "solid"};
}
const stationInput = $("show-station-history");
const stationStyle = sourceStyle(stationInput);
const references = [...document.querySelectorAll("[data-control]")].map((input) => ({
  input,
  key: input.dataset.control,
  name: input.labels[0].textContent,
  daily: input.dataset.metrics.split(" "),
  hourly: input.dataset.hourlyMetrics?.split(" ") ?? [],
  status: $(`${input.id}-status`),
  selected: false,
  feeds: {},
  ...sourceStyle(input),
}));
const referenceRefresh = {daily: HOUR, hourly: HOUR / 4};
const hourlyDelay = 3 * HOUR;
const periodDays = { day: 1, week: HOURLY_PRESET_DAYS, month: 30, year: 365, all: Infinity };
const minute = HOUR / 60;
const archiveStep = 5 * minute;
const seasonCache = new WeakMap();
const clippedRows = new WeakMap();
const state = {
  mode: settings.default_mode,
  metric: "temperature",
  period: "day",
  units: "us",
  current: null,
  history: {},
  viewport: null,
  showStation: true,
};
let currentFeed = {};
function stationFeed() {
  const path = state.mode === "sample" ? "./data/sample/" : settings.feed;
  return path && new URL(path, location.href);
}
function historyEnd() {
  return state.mode === "sample" ? state.current?.observedAt ?? state.history.recent?.data?.throughTime ?? -Infinity : Date.now();
}
function chartCadence(end = historyEnd()) {
  const recentThrough = Math.max(state.current?.observedAt ?? -Infinity, state.history.recent?.data?.throughTime ?? -Infinity);
  if (state.period === "day" && !state.viewport && recentThrough === -Infinity) return "recent";
  return historyCadence(periodDays[state.period], state.viewport, end, recentThrough);
}
function supportsMetric(source, cadence) {
  return source[cadence]?.includes(state.metric) ?? false;
}
let timelineDomain = null;
let renderWindow;
function rememberViewport(event) {
  if (!timelineDomain) return;
  const zoom = event.batch?.[0] ?? event;
  if (timelineDomain.seasonal) {
    const {start, end} = numeric(zoom.start) ? zoom : chart.getOption().dataZoom[0];
    state.viewport = {start, end};
    renderPeriodSelection();
    return;
  }
  // Plot selection and date entry supply timestamps. The slider and wheel supply percentages.
  const view = numeric(zoom.startValue) && numeric(zoom.endValue)
    ? {from: zoom.startValue, to: zoom.endValue}
    : windowFromPercent(timelineDomain, zoom);
  if (!(view.from < view.to)) return;
  state.viewport = timelineWindow(timelineDomain, periodDays[state.period], view);
  if (chartCadence(timelineDomain.end) !== timelineDomain.cadence) {
    renderChart();
  } else {
    renderPeriodSelection();
    renderWindow(state.viewport);
  }
}
function currentWindow() {
  return timelineWindow(timelineDomain, periodDays[state.period], state.viewport);
}
function zoomValues({from, to}) {
  return {startValue: from, endValue: to};
}
function zoomTo(view) {
  chart.dispatchAction({type: "dataZoom", ...zoomValues(view)});
}
function moveWindow(direction) {
  const view = currentWindow();
  const offset = timelineDomain.cadence === "daily" ? calendarDayOffset(view.from, direction, settings.station.timezone)
    : direction * (timelineDomain.cadence === "recent" ? archiveStep : HOUR);
  const next = shiftWindow(timelineDomain, view, offset);
  if (next.from !== view.from) zoomTo(next);
}
$("timeline-earlier").addEventListener("click", () => moveWindow(-1));
$("timeline-later").addEventListener("click", () => moveWindow(1));
$("timeline-dates").addEventListener("toggle", (event) => {
  if (!event.target.open || !timelineDomain || timelineDomain.seasonal) return;
  const {from, to} = currentWindow();
  // A datetime-local field has no timezone. The labels define its values as UTC.
  $("timeline-from").valueAsNumber = Math.floor(from / minute) * minute;
  $("timeline-to").valueAsNumber = Math.ceil(to / minute) * minute;
  $("timeline-dates-error").textContent = "";
});
$("timeline-dates-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!timelineDomain || timelineDomain.seasonal) return;
  const from = $("timeline-from").valueAsNumber;
  const to = $("timeline-to").valueAsNumber;
  const error = $("timeline-dates-error");
  if (!(from < to)) {
    error.textContent = "Choose an end time after the start time.";
    return;
  }
  if (from >= timelineDomain.end || to <= timelineDomain.start) {
    error.textContent = "Choose dates that overlap the chart timeline.";
    return;
  }
  error.textContent = from <= timelineDomain.start - minute || to >= timelineDomain.end + minute
    ? "Range limited to the chart timeline." : "";
  zoomTo({from, to});
});

const numeric = (value) => typeof value === "number" && Number.isFinite(value);
const rounded = (value, decimals = 1) =>
  numeric(value) ? value.toFixed(decimals) : "—";
const parseTimestamp = (value) =>
  typeof value === "string" && /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? Date.parse(value) : NaN;
const temp = (value) =>
  numeric(value) ? (state.units === "us" ? (value * 9) / 5 + 32 : value) : null;
const speed = (value) =>
  numeric(value) ? value * (state.units === "us" ? 2.236936 : 1) : null;
const rain = (value) =>
  numeric(value) ? value / (state.units === "us" ? 25.4 : 1) : null;
const units = () => ({
  temperature: state.units === "us" ? "°F" : "°C",
  wind: state.units === "us" ? "mph" : "m/s",
  rain: state.units === "us" ? "in" : "mm",
  humidity: "%",
  solar: "W/m²",
});

const metrics = {
  temperature: {label: "Temperature", field: "temperature_c", convert: temp},
  humidity: {label: "Relative humidity", field: "humidity_pct"},
  wind: {label: "Average wind speed", field: "wind_speed_m_s", convert: speed},
  rain: {label: "Precipitation", field: "rain_mm", convert: rain},
  solar: {label: "Solar irradiance", field: "solar_w_m2"},
};
const partialBarStyle = {
  decal: {symbol: "rect", dashArrayX: [1, 0], dashArrayY: [2, 3], rotation: Math.PI / 4, color: "rgba(0, 0, 0, .55)"},
};

function validEnvelope(data) {
  if (data.schema_version !== 1 || data.kind !== state.mode)
    throw new Error("The feed does not match the selected data source.");
}
function parseRows(rows, through, validate) {
  let previous = -Infinity;
  return rows.map((row) => {
    const at = parseTimestamp(row.at);
    if (!numeric(at) || at <= previous || at > through) throw new Error("Invalid feed timestamps");
    previous = at;
    validate(row, at);
    return {...row, at};
  });
}
function validCurrent(data) {
  validEnvelope(data);
  const observedAt = parseTimestamp(data.observed_at);
  if (
    data.station?.id !== settings.station.id ||
    !numeric(observedAt) ||
    !data.outdoor ||
    (state.mode === "live" && !data.deployment?.dataset_id) ||
    typeof data.outdoor.verified !== "boolean" ||
    typeof data.outdoor.source !== "string"
  )
    throw new Error("The observation feed is incomplete.");
  for (const field of [
    "temperature_c",
    "humidity_pct",
    "wind_speed_m_s",
    "wind_gust_m_s",
    "wind_direction_deg",
    "rain_today_mm",
    "solar_w_m2",
    "uv_index",
  ]) {
    if (data.outdoor[field] !== null && !numeric(data.outdoor[field]))
      throw new Error("An observation contains an invalid value.");
  }
  return {...data, observedAt};
}
function validHistory(data, cadence) {
  validEnvelope(data);
  const throughTime = parseTimestamp(data.through);
  const recordStartedAt = parseTimestamp(data.record_started_at);
  if (
    data.station_id !== settings.station.id ||
    data.cadence !== cadence ||
    !numeric(throughTime) ||
    !numeric(recordStartedAt) ||
    !Array.isArray(data.rows) ||
    (state.mode === "live" && !data.deployment?.dataset_id)
  )
    throw new Error("The history feed is incomplete.");
  const rows = parseRows(data.rows, throughTime, (row, at) => {
    if (cadence !== "recent" && at >= throughTime) throw new Error("History includes an unfinished interval.");
    for (const field of ["temperature_c", "humidity_pct", "wind_speed_m_s", "wind_gust_m_s", "rain_mm"])
      if (row[field] !== null && !numeric(row[field])) throw new Error("History contains an invalid value.");
    for (const field of ["temperature_min_c", "temperature_max_c", "solar_w_m2"])
      if (row[field] != null && !numeric(row[field])) throw new Error("History contains an invalid optional value.");
  });
  const history = {...data, throughTime, recordStartedAt, rows};
  if (!matchesCurrentDataset(history)) throw new Error("Current observations use a different history dataset.");
  return history;
}
function validReference(data, key, cadence) {
  const hourly = cadence === "hourly";
  const through = hourly ? parseTimestamp(data.through) : Infinity;
  if (data.schema_version !== 1 || data.kind !== "reference" || data.source?.id !== key ||
      !["modeled", "observed"].includes(data.source.type) || typeof data.source.name !== "string" ||
      !numeric(data.source.elevation_m) || !Array.isArray(data[cadence]) || !data[cadence].length ||
      (hourly ? !numeric(through) || data.source.type !== "observed" :
        !Number.isFinite(Date.parse(data.start_date)) || !Number.isFinite(Date.parse(data.end_date))))
    throw new Error("Invalid reference metadata");
  const rows = parseRows(data[cadence], hourly ? through - HOUR : through, (row, at) => {
    if (hourly && at % HOUR !== 0) throw new Error("Invalid reference hour");
    for (const field of ["temperature_min_c", "temperature_max_c", "rain_mm"])
      if (row[field] !== null && !numeric(row[field])) throw new Error("Invalid reference value");
    for (const field of ["humidity_pct", "wind_speed_m_s", "solar_w_m2"])
      if (row[field] != null && (!numeric(row[field]) || row[field] < 0))
        throw new Error("Invalid reference value");
    if (numeric(row.rain_mm) && row.rain_mm < 0 || numeric(row.temperature_min_c) &&
        numeric(row.temperature_max_c) && row.temperature_min_c > row.temperature_max_c || row.humidity_pct > 100)
      throw new Error("Invalid reference range");
  });
  return {...data, [cadence]: rows};
}
function matchesCurrentDataset(history) {
  const currentDataset = state.current?.deployment?.dataset_id;
  return !currentDataset || history.deployment?.dataset_id === currentDataset;
}
async function refreshFeed(entry, url, validate) {
  const {data, failed} = entry;
  entry.loading = true;
  entry.checkedAt = Date.now();
  try {
    const response = await fetch(url, {signal: AbortSignal.timeout(15000), cache: "no-cache"});
    if (!response.ok) throw new Error(`Feed returned HTTP ${response.status}.`);
    const etag = response.headers.get("etag");
    if (!etag || etag !== entry.etag) {
      entry.data = validate(await response.json());
      entry.etag = etag;
    }
    entry.failed = false;
  } catch {
    entry.failed = true;
  } finally {
    entry.loading = false;
  }
  return !data || data !== entry.data || failed !== entry.failed;
}
function notice(text, error = false) {
  $("notice-text").textContent = text;
  $("notice").classList.toggle("error", error);
}
function selected(group, value) {
  for (const button of document.querySelectorAll(`[data-${group}]`))
    button.setAttribute("aria-pressed", String(button.dataset[group] === value));
}
function renderPeriodSelection() {
  const custom = state.viewport !== null;
  selected("period", custom ? null : state.period);
  $("custom-period").hidden = !custom;
  $("custom-period").title = custom && !timelineDomain?.seasonal
    ? `${timeFormat.format(new Date(state.viewport.from))} – ${timeFormat.format(new Date(state.viewport.to))}`
    : "Custom history window";
}
function renderCurrent() {
  const data = state.current;
  const observation = data?.outdoor ?? {};
  $("pilot-notice").hidden =
    state.mode === "sample" ||
    (data?.deployment?.phase === "production" && observation.verified);
  if (data?.deployment?.notice)
    $("pilot-notice-text").textContent = data.deployment.notice;

  const unverified = data?.kind === "live" && !observation.verified;
  $("temperature-label").textContent = unverified
    ? "Primary temperature · unverified"
    : "Outdoor temperature";
  $("humidity-label").textContent = unverified
    ? "Primary humidity · unverified"
    : "Outdoor relative humidity";
  const u = units();
  $("temperature").textContent = rounded(temp(observation.temperature_c));
  $("humidity").textContent = rounded(observation.humidity_pct, 0);
  $("wind").textContent = rounded(speed(observation.wind_speed_m_s));
  $("rain").textContent = rounded(
    rain(observation.rain_today_mm),
    state.units === "us" ? 2 : 1,
  );
  $("solar").textContent = rounded(observation.solar_w_m2, 0);
  const direction = numeric(observation.wind_direction_deg)
    ? ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][
        Math.round(observation.wind_direction_deg / 45) % 8
      ]
    : "—";
  $("gust").textContent =
    `Gust ${rounded(speed(observation.wind_gust_m_s))} ${u.wind} · ${direction}`;
  $("uv").textContent = `UV index ${rounded(observation.uv_index)}`;
  for (const label of document.querySelectorAll("[data-unit]"))
    label.textContent = ` ${u[label.dataset.unit]}`;
  $("observed-at").textContent = data
    ? `${data.kind === "sample" ? "Sample observation" : "Observed"} · ${timeFormat.format(data.observedAt)}`
    : currentFeed.loading
      ? "Connecting to the selected feed…"
      : "No observation available.";
  $("provenance").textContent =
    data?.kind === "sample"
      ? "Sample values only. Live sensor mapping is unverified."
      : data
        ? `${observation.source} · ${observation.verified ? "Sensor mapping verified." : "Sensor mapping unverified."}`
        : "Sensor provenance is unavailable.";
  renderStatus();
}
function renderStatus() {
  const status = $("status");
  status.className = "tag";
  if (state.mode === "sample") {
    status.classList.add("sample");
    status.textContent = "Sample data";
    return;
  }
  if (!state.current) {
    status.classList.add("error");
    status.textContent = currentFeed.loading ? "Connecting" : "Unavailable";
    return;
  }
  const age = (Date.now() - state.current.observedAt) / 60000;
  const stale = age > settings.stale_after_minutes;
  const clockError = age < -5;
  status.classList.add(stale || clockError ? "stale" : "fresh");
  status.textContent = clockError
    ? "Check timestamp"
    : stale
      ? "Last known data"
      : "Recent observation";
  if (clockError)
    notice(
      "The observation time is in the future. Check the station clock before using these readings.",
      true,
    );
  else if (stale)
    notice(
      "These are last-known readings. The station has not reported a recent observation.",
      true,
    );
}
function rowsThrough(rows, cutoff) {
  if (!rows?.length) return [];
  if (rows.at(-1).at <= cutoff) return rows;
  const previous = clippedRows.get(rows);
  // A moving cutoff reuses the same rows until it crosses a reading.
  if (previous && (previous.at(-1)?.at ?? -Infinity) <= cutoff && rows[previous.length].at > cutoff)
    return previous;
  const clipped = rows.filter((row) => row.at <= cutoff);
  clippedRows.set(rows, clipped);
  return clipped;
}
function groupedRows(rows, seasonal) {
  if (!seasonal || !rows.length) return rows;
  let summaries = seasonCache.get(rows);
  if (!summaries) {
    summaries = {};
    seasonCache.set(rows, summaries);
  }
  return summaries[state.period] ??= seasonalRows(rows, state.period === "monsoon", settings.station.timezone);
}
function renderChart() {
  if (!chartRequested) return;
  const end = historyEnd();
  const cadence = chartCadence(end);
  loadHistory(cadence);
  if (!chart) return;
  renderPeriodSelection();
  const seasonal = ["seasons", "monsoon"].includes(state.period);
  $("monsoon-source").hidden = state.period !== "monsoon";
  const days = periodDays[state.period];
  const daily = !seasonal && cadence === "daily";
  const recent = cadence === "recent";
  const historyFeed = state.showStation && state.history[cadence];
  const history = historyFeed?.data;
  const resolution = seasonal ? (state.period === "monsoon" ? "Monsoon" : "Seasonal")
    : daily ? "Daily" : recent ? "Five-minute" : "Hourly";
  let rows = groupedRows(rowsThrough(history?.rows, end), seasonal);
  const {label, field, convert = (value) => numeric(value) ? value : null} = metrics[state.metric];
  const stationName = state.mode === "sample" ? "Sample station" : settings.station.name;
  const stationSubtitle = state.showStation
    ? `${stationName} history · Mountain Time`
    : `${stationName} hidden · Mountain Time`;
  $("history-resolution").textContent = recent ? "Five-minute observations" : `${resolution} summaries`;
  const activeSources = [];
  const hasEligibleSource = references.some((source) => supportsMetric(source, cadence));
  $("reference-sources").disabled = !hasEligibleSource;
  for (const source of references) {
    const {input, status} = source;
    const eligible = supportsMetric(source, cadence);
    const active = eligible && source.selected;
    input.disabled = !eligible;
    input.checked = active;
    status.hidden = !hasEligibleSource || eligible;
    status.textContent = cadence === "hourly" && source.daily.includes(state.metric) ? "Daily only" : "No data";
    if (status.hidden) input.removeAttribute("aria-describedby");
    else input.setAttribute("aria-describedby", status.id);
    if (active) {
      activeSources.push(source);
      loadReference(source, cadence);
    }
  }
  const showReferences = activeSources.length > 0;
  const measurementFields = state.metric === "temperature" && !recent ? [
    ["temperature_max_c", seasonal ? "avg high" : "high"],
    ["temperature_min_c", seasonal ? "avg low" : "low"],
  ] : [[field, seasonal && state.metric === "rain" ? "total precipitation" : label.toLowerCase()]];
  const hasReferenceValue = (row) => measurementFields.some(([key]) => numeric(row[key]));
  // A reference hour must be complete at the live or sample cutoff.
  const hourly = cadence === "hourly";
  const referenceInterval = hourly ? HOUR : 0;
  const selectedReferences = activeSources.map((source) => {
    const {data, failed, loading} = source.feeds[cadence];
    const rows = rowsThrough(data?.[cadence], end - referenceInterval);
    return {source, rows, last: rows.findLast(hasReferenceValue), loaded: Boolean(data), failed, loading};
  });
  const comparisons = selectedReferences.flatMap(({source, rows, last}) =>
    last ? [{source, rows: groupedRows(rows, seasonal)}] : []);
  const dailyAvailable = references.some((source) => source.daily.includes(state.metric));
  const controlNote = recent ? "Choose 7d or 30d to compare references."
    : !hasEligibleSource
    ? cadence === "hourly" && dailyAvailable ? "Choose 30d to compare this measurement in daily summaries."
      : "No references report the selected metric."
    : !showReferences ? "Select sources to compare regional weather."
    : selectedReferences.map(({source: {name}, last, loaded, failed, loading}) => {
      if (!loaded) return loading ? `Loading ${name}…` : `${name} could not be loaded. Reselect to retry.`;
      const coverageEnd = last && last.at + referenceInterval;
      const lag = last && hourly && state.mode === "live" && end - coverageEnd > hourlyDelay;
      const coverage = last ? `through ${(hourly ? timeFormat : dateFormat).format(coverageEnd)}`
        : state.mode === "sample" ? "no values for this measurement before the sample ends"
        : "no values for this measurement";
      return [name, coverage, lag ? "delayed" : "", failed ? "refresh failed" : ""].filter(Boolean).join(" · ");
    }).join(" | ");
  if (seasonal && comparisons.length) {
    const periods = new Map([...rows, ...comparisons.flatMap((item) => item.rows)].map((row) => [row.start, row]));
    const templates = [...periods.values()].sort((a, b) => a.start - b.start);
    const align = (data) => {
      const byStart = new Map(data.map((row) => [row.start, row]));
      return templates.map((row) => byStart.get(row.start) ??
        {label: row.label, start: row.start, expectedDays: row.expectedDays, coverage: {}});
    };
    rows = align(rows);
    for (const item of comparisons) item.rows = align(item.rows);
  }
  // Each validated series is ordered; only its endpoints are needed for coverage.
  const endpoints = [rows, ...comparisons.map((item) => item.rows)]
    .flatMap((data) => data.length ? [data[0], data.at(-1)] : [])
    .sort((a, b) => seasonal ? a.start - b.start : a.at - b.at);
  const range = !endpoints.length ? "No history available" : seasonal
    ? `${endpoints[0].label} – ${endpoints.at(-1).label}`
    : `Available ${dateFormat.format(endpoints[0].at)} – ${dateFormat.format(endpoints.at(-1).at)}`;
  const stationStatus = historyFeed?.failed ? (history ? "Station refresh failed" : "Station history unavailable")
    : recent && history && state.current && history.throughTime !== state.current.observedAt
      ? "Station history and current observations updated at different times" : "";
  $("history-range").textContent = [range, stationStatus].filter(Boolean).join(" · ");
  const referenceHasData = comparisons.some((item) => item.rows.some(hasReferenceValue));
  const stationFields = state.metric === "wind" ? [...measurementFields, ["wind_gust_m_s", "peak gust"]] : measurementFields;
  const plottedFields = stationFields.filter(([key]) => rows.some((row) => numeric(row[key])));
  const stationHasData = plottedFields.length > 0;
  function describeCoverage(view) {
    const inWindow = (row) => !view || (row.at >= view.from && row.at <= view.to);
    const stationInWindow = rows.some((row) => inWindow(row) && plottedFields.some(([key]) => numeric(row[key])));
    const referenceInWindow = comparisons.some((item) => item.rows.some((row) =>
      inWindow(row) && hasReferenceValue(row)));
    const subtitle = !referenceInWindow ? stationSubtitle : stationInWindow
      ? `${stationName} + reference history · Mountain Time`
      : `Reference history only · ${state.showStation ? `${stationName} has no readings in this window` : `${stationName} hidden`} · Mountain Time`;
    if ($("history-subtitle").textContent !== subtitle) $("history-subtitle").textContent = subtitle;
    const status = controlNote + (comparisons.length && !referenceInWindow
      ? " · No reference observations in this window" : "");
    if ($("control-note").textContent !== status) $("control-note").textContent = status;
    return stationInWindow || referenceInWindow;
  }
  const description = $("chart-description");
  $("timeline-controls").hidden = seasonal || (!stationHasData && !referenceHasData);
  if (!stationHasData && !referenceHasData) {
    describeCoverage();
    const loading = historyFeed?.loading || selectedReferences.some((reference) => reference.loading);
    const selectionPrompt = hasEligibleSource
      ? "Choose observations or\nreference history to display." : `Show ${stationName} to display history.`;
    const emptyMessage = !state.showStation && !showReferences ? selectionPrompt
      : loading ? "Loading history…"
      : `No ${label.toLowerCase()} observations in this period.`;
    timelineDomain = null;
    chart.setOption({
      title: {
        text: emptyMessage,
        left: "center",
        top: "center",
        textStyle: { color: "#a1b0ab", fontSize: 14, fontWeight: "normal" },
      },
    }, chartUpdate);
    $("chart").setAttribute("aria-label", emptyMessage.replace("\n", " "));
    description.hidden = true;
    return;
  }
  const unit = units()[state.metric];
  const seriesMeta = new Map();
  const makeSeries = (name, key, {color, pattern}, dataRows = rows) => {
    seriesMeta.set(name, {rows: dataRows, key});
    const line = state.metric !== "rain";
    const low = key === "temperature_min_c";
    const gust = key === "wind_gust_m_s";
    const secondary = low || gust;
    const marker = low ? "emptyCircle" : "circle";
    const opacity = secondary ? .72 : 1;
    let hasIsolatedPoints = false;
    const data = dataRows.map((row, index) => {
      const value = [seasonal ? index : row.at, convert(row[key])];
      if (!line && seasonal && numeric(value[1]) && row.coverage[key] < row.expectedDays)
        return {value, itemStyle: partialBarStyle};
      if (line && !seasonal && numeric(value[1]) &&
          !numeric(dataRows[index - 1]?.[key]) && !numeric(dataRows[index + 1]?.[key])) {
        hasIsolatedPoints = true;
        return {value, symbol: marker};
      }
      return value;
    });
    return {
      name,
      type: line ? "line" : "bar",
      showSymbol: seasonal || hasIsolatedPoints,
      symbol: seasonal ? marker : "none",
      symbolSize: 4,
      connectNulls: false,
      data,
      itemStyle: {color, opacity},
      lineStyle: {color, opacity, width: secondary ? 1.5 : 2.25, type: gust ? [4, 3] : pattern},
      emphasis: { focus: "series" },
    };
  };
  // Color and dash pattern identify the source. Stroke weight and markers distinguish highs and lows.
  const series = plottedFields.map(([key, suffix]) => makeSeries(`${stationName} · ${suffix}`, key, stationStyle));
  for (const {source, rows} of comparisons) {
    for (const [key, suffix] of measurementFields) {
      if (!rows.some((row) => numeric(row[key]))) continue;
      series.push(makeSeries(`${source.name} · ${suffix}`, key, source, rows));
    }
  }
  if (comparisons.length && stationHasData && !seasonal && numeric(history?.recordStartedAt)) {
    series[0].markLine = {
      symbol: "none", lineStyle: {color: stationStyle.color, type: "dashed"},
      data: [{xAxis: history.recordStartedAt, name: state.mode === "sample" ? "Sample station begins" : history.deployment?.phase === "production" && state.current?.outdoor?.verified ? "Verified WS90 begins" : "Local pilot begins"}],
      label: {formatter: "{b}", color: stationStyle.color, position: "insideEndTop"},
    };
  }
  // Keep older hourly dates reachable from the rolling five-minute archive.
  const oldestHourly = recent && history ? Math.max(
    Math.floor((history.recordStartedAt - 1) / HOUR) * HOUR,
    Math.floor(history.throughTime / HOUR) * HOUR - 30 * DAY,
  ) : Infinity;
  const first = Math.min(endpoints[0].at, oldestHourly ?? Infinity, state.viewport?.from ?? Infinity);
  timelineDomain = seasonal ? {seasonal: true} : {...timeDomain(first, end, days), cadence};
  const view = seasonal ? null : currentWindow();
  const zoom = seasonal ? state.viewport ?? {start: 0, end: 100} : {...zoomValues(view), minValueSpan: 1};
  renderWindow = (view) => {
    const readings = describeCoverage(view);
    const format = daily ? dateFormat : timeFormat;
    const dates = format.formatRange(new Date(view.from), new Date(view.to));
    const summary = `Showing ${dates}${readings ? "" : " · No readings in this window"}`;
    if ($("timeline-window").textContent !== summary) $("timeline-window").textContent = summary;
    $("timeline-earlier").disabled = view.from <= timelineDomain.start;
    $("timeline-later").disabled = view.to >= timelineDomain.end;
  };
  if (seasonal) describeCoverage();
  else {
    const step = daily ? "one day" : recent ? "five minutes" : "one hour";
    $("timeline-earlier").setAttribute("aria-label", `Move window ${step} earlier`);
    $("timeline-later").setAttribute("aria-label", `Move window ${step} later`);
    renderWindow(view);
  }
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const seasonLabel = (row) => {
    if (comparisons.length) return row.label;
    const days = plottedFields.map(([key]) => row.coverage[key] ?? 0);
    const status = days.every((count) => count === 0) ? "\n(no data)"
      : days.some((count) => count < row.expectedDays) ? "\n(partial)" : "";
    return row.label + status;
  };
  chart.setOption(
    {
      backgroundColor: "transparent",
      animation: !reducedMotion,
      textStyle: {
        fontFamily: "system-ui, sans-serif",
        color: "#a1b0ab",
        fontSize: 11,
      },
      aria: { enabled: true },
      grid: { left: 10, right: 16, top: 34, bottom: seasonal ? 70 : 52, containLabel: true },
      legend: {
        left: 50, // Leave room for the y-axis unit.
        type: "scroll",
        itemWidth: 31,
        pageTextStyle: {color: "#a1b0ab"},
        show: series.length > 1,
        top: 0,
        right: 0,
        textStyle: { color: "#a1b0ab", fontSize: 10 },
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        extraCssText: "max-width:100%;white-space:normal",
        backgroundColor: "#22302e",
        borderColor: "#43534a",
        textStyle: { color: "#e8ebe4" },
        formatter: (entries) => {
          const date = new Date(entries[0].value[0]);
          const title = seasonal ? rows[entries[0].value[0]].label
            : daily ? `${weekdayFormat.format(date)}, ${dateFormat.format(date)}`
            : recent ? `Five minutes ending ${weekdayFormat.format(date)}, ${timeFormat.format(date)}`
            : `${weekdayFormat.format(date)}, ${timeFormat.formatRange(date, new Date(date.getTime() + HOUR))}`;
          const ordered = state.metric === "temperature" ? entries : [...entries].sort((a, b) => {
            const aValue = a.value[1], bValue = b.value[1];
            return numeric(aValue) && numeric(bValue) ? bValue - aValue
              : Number(numeric(bValue)) - Number(numeric(aValue));
          });
          return `${title}<br>` + ordered.map((entry) => {
            const meta = seriesMeta.get(entry.seriesName);
            const row = meta.rows[entry.dataIndex];
            const value = state.metric === "rain" && row?.precipitation_trace ? "Trace" : numeric(entry.value[1])
              ? entry.value[1].toFixed(state.metric === "rain" && state.units === "us" ? 2 : 1) + " " + unit : "Missing";
            const name = window.echarts.format.encodeHTML(entry.seriesName);
            const reading = `${entry.marker}${name}: ${value}`;
            if (seasonal) {
              const days = row.coverage[meta.key] ?? 0;
              const percent = Math.round(100 * days / row.expectedDays);
              const partial = days < row.expectedDays ? " is-partial" : "";
              return `${reading} <span class="tooltip-coverage${partial}">${percent}% data coverage</span>`;
            }
            return reading + (row?.field_sources?.[meta.key] === "rcc-acis" ? " · RCC-ACIS supplemental report" : "");
          }).join("<br>");
        },
        axisPointer: { type: state.metric === "rain" ? "shadow" : "line" },
      },
      xAxis: {
        type: seasonal ? "category" : "time",
        min: seasonal ? undefined : timelineDomain.start,
        max: seasonal ? undefined : end,
        ...(seasonal ? { data: rows.map(seasonLabel) } : {}),
        axisLine: { lineStyle: { color: "#35433e" } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          hideOverlap: true,
          color: "#a1b0ab",
          formatter: (value) => seasonal ? value.replace(" ", "\n") : daily
            ? dateFormat.format(value).replace(", ", "\n") : (recent ? recentTickFormat : hourFormat).format(value),
        },
      },
      yAxis: {
        type: "value",
        scale: state.metric === "temperature",
        min: ["rain", "wind", "humidity", "solar"].includes(state.metric)
          ? 0
          : undefined,
        max: state.metric === "humidity" ? 100 : undefined,
        name: unit,
        nameTextStyle: { color: "#a1b0ab" },
        splitLine: { lineStyle: { color: "#283632", type: "dashed" } },
        axisLabel: { color: "#a1b0ab" },
      },
      dataZoom: [
        { type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseMove: false, moveOnMouseWheel: false, ...zoom },
        {
          type: "slider",
          ...zoom,
          // Commit the slider range on release so a pan cannot keep changing
          // the plot while the next selection is in progress.
          realtime: false,
          throttle: 0,
          brushSelect: seasonal,
          showDetail: seasonal,
          // ECharts bases the preview on series extents, which can end before the live axis.
          showDataShadow: seasonal ? "auto" : false,
          bottom: 4,
          height: 24,
          borderColor: "#35433e",
          backgroundColor: "#172422",
          fillerColor: "#a1c6ac32",
          handleStyle: { color: "#759b85" },
          textStyle: { color: "#a1b0ab" },
          dataBackground: {
            lineStyle: { color: "#759b85" },
            areaStyle: { color: "#30463c" },
          },
        },
      ],
      series,
    },
    chartUpdate,
  );
  const notes = [];
  if (seasonal && state.metric === "temperature") notes.push("Highs and lows are averages of the reported daily highs and lows.");
  if (seasonal && state.metric === "rain") notes.push("Striped bars show precipitation totals for periods with incomplete data coverage.");
  if (seasonal) notes.push("Data coverage counts days with a reported value, including zero, out of the full period.");
  if (state.metric === "rain" && referenceHasData)
    notes.push("Reference precipitation can include melted snow.");
  if (state.metric === "solar") notes.push("Solar averages include nighttime readings.");
  description.textContent = notes.join(" ");
  description.hidden = !notes.length;
  const sources = stationHasData
    ? stationName + (referenceHasData ? " and selected references" : "")
    : "selected references";
  const measurement = state.metric === "temperature" && !recent
    ? seasonal ? "average daily temperature highs and lows" : "temperature highs and lows"
    : label.toLowerCase();
  $("chart").setAttribute("aria-label", `${resolution} ${measurement} chart for ${sources}`);
}
function loadMode() {
  const source = stationFeed();
  currentFeed = {};
  state.current = null;
  state.history = {};
  $("json-link").hidden = !source;
  selected("mode", state.mode);
  if (!source) {
    notice("Live observations are unavailable on this preview address. Sample mode is available.", true);
  } else {
    $("json-link").href = new URL("current.json", source);
    notice(state.mode === "sample"
      ? "Station readings and history are illustrative samples. Selected controls use real, attributed reference data."
      : "Connecting to the station feed…");
    loadCurrent();
  }
  renderCurrent();
  renderChart();
}
async function loadCurrent() {
  const entry = currentFeed;
  const source = stationFeed();
  if (!source || entry.loading) return;
  await refreshFeed(entry, new URL("current.json", source), validCurrent);
  if (entry !== currentFeed) return;
  const previous = state.current;
  state.current = entry.data ?? null;
  if (previous && !matchesCurrentDataset(previous)) state.history = {};
  for (const [cadence, cached] of Object.entries(state.history))
    if (cached.data && !matchesCurrentDataset(cached.data)) delete state.history[cadence];
  if (state.mode === "live") {
    if (entry.failed)
      notice(
        state.current
          ? "The latest refresh failed. Showing the last observation with its original timestamp."
          : "The live observation feed is unavailable. Please try again later.",
        true,
      );
    else
      notice(
        state.current.outdoor.verified
          ? "Station observations · timestamps and sensor provenance are included in the public JSON feed."
          : "Sensor mapping is unverified. Primary temperature and humidity may come from an auxiliary sensor.",
      );
  } else if (entry.failed)
    notice("Sample current observations could not be loaded.", true);
  renderCurrent();
  renderChart();
}
async function loadHistory(cadence) {
  const source = stationFeed();
  if (!source || !state.showStation) return;
  const entry = state.history[cadence] ??= {};
  const fresh = entry.checkedAt !== undefined && (state.mode === "sample" || Date.now() - entry.checkedAt < archiveStep);
  if (entry.loading || fresh) return;
  const changed = await refreshFeed(entry, new URL(`history/${cadence}.json`, source), (data) => validHistory(data, cadence));
  if (changed && entry === state.history[cadence] && cadence === chartCadence() && state.showStation) renderChart();
}
for (const group of ["metric", "period", "units", "mode"]) {
  for (const button of document.querySelectorAll(`[data-${group}]`))
    button.addEventListener("click", () => {
      state[group] = button.dataset[group];
      if (group === "period" || group === "mode") {
        state.viewport = null;
        $("timeline-dates").open = false;
      }
      if (group === "period" && state.period === "monsoon") {
        state.metric = "rain";
        selected("metric", state.metric);
      }
      selected(group, state[group]);
      if (group === "mode") loadMode();
      else {
        if (group === "units") renderCurrent();
        renderChart();
      }
    });
}
async function loadReference(source, cadence, {maxAge = Infinity, retryFailed = false} = {}) {
  const entry = source.feeds[cadence] ??= {};
  const now = Date.now();
  const fresh = now - entry.checkedAt < maxAge;
  if (entry.loading || (fresh && !(retryFailed && entry.failed))) return;
  const {key} = source;
  const path = cadence === "hourly" ? `hourly/${key}.json` : `${key}.json`;
  const changed = await refreshFeed(entry, new URL(path, settings.reference_feed), (data) => validReference(data, key, cadence));
  if (changed && source.selected && cadence === chartCadence() && supportsMetric(source, cadence)) renderChart();
}
stationInput.addEventListener("change", (event) => {
  state.showStation = event.target.checked;
  if (["seasons", "monsoon"].includes(state.period)) state.viewport = null;
  renderChart();
});
for (const source of references) {
  const {input} = source;
  input.addEventListener("change", () => {
    if (["seasons", "monsoon"].includes(state.period)) state.viewport = null;
    source.selected = input.checked;
    if (source.selected) {
      const cadence = chartCadence();
      if (referenceRefresh[cadence])
        loadReference(source, cadence, {maxAge: referenceRefresh[cadence], retryFailed: true});
    }
    renderChart();
  });
}
async function activateChart() {
  if (chartRequested) return;
  chartRequested = true;
  renderChart();
  try {
    if (!window.echarts) {
      await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = new URL("./vendor/echarts/echarts.common.min.js", import.meta.url);
        script.onload = resolve;
        script.onerror = () => {
          script.remove();
          reject(new Error("Could not load ECharts"));
        };
        document.head.append(script);
      });
    }
    chart = window.echarts.init($("chart"), null, {renderer: "svg"});
    // Replacing the toolbox leaves its brush listening, so one drag can zoom several times.
    chart.setOption({toolbox: {itemSize: 0, itemGap: 0, showTitle: false, feature: {dataZoom: {yAxisIndex: "none"}}}});
    chart.dispatchAction({type: "takeGlobalCursor", key: "dataZoomSelect", dataZoomSelectActive: true});
    chart.on("datazoom", rememberViewport);
    new ResizeObserver(() => chart.resize()).observe($("chart"));
    chartObserver.disconnect();
    renderChart();
  } catch {
    chartRequested = false;
    $("history-range").textContent = "Chart unavailable. Select History to retry.";
  }
}
const chartObserver = new IntersectionObserver(([entry]) => {
  if (entry.isIntersecting) activateChart();
}, {rootMargin: "160px"});
chartObserver.observe($("chart"));
$("history").addEventListener("focusin", activateChart);
document.querySelector('a[href="#history"]').addEventListener("click", activateChart);
setInterval(renderStatus, 60000);
setInterval(() => {
  if (state.mode === "live") loadCurrent();
  if (!chartRequested) return;
  const cadence = chartCadence();
  if (state.mode === "live") loadHistory(cadence);
  const maxAge = referenceRefresh[cadence];
  if (!maxAge) return;
  for (const source of references)
    if (source.selected && supportsMetric(source, cadence))
      loadReference(source, cadence, {maxAge});
}, 300000);
loadMode();
if (location.hash === "#history") activateChart();
