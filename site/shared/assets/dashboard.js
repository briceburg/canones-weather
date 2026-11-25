import { settings } from "./common.js";
import { seasonalRows } from "./seasons.js";
import { DAY, HOUR, shiftWindow, timeDomain, timelineRange, usesDailyHistory, visibleWindow } from "./timeline.js";

const $ = (id) => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: settings.station.timezone,
  month: "short",
  day: "numeric",
  year: "numeric",
});
const timeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: settings.station.timezone,
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const hourFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: settings.station.timezone, hour: "numeric",
});
const clockFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: settings.station.timezone,
  hour: "numeric", hour12: true, minute: "2-digit", second: "2-digit", timeZoneName: "short",
});
function renderClock() {
  const now = new Date();
  $("station-clock").dateTime = now.toISOString();
  $("station-clock").textContent = clockFormat.formatToParts(now)
    .map(({type, value}) => type === "dayPeriod" ? value.toLowerCase() : value)
    .join("");
}
renderClock();
setInterval(renderClock, 1000);
const chart = window.echarts.init($("chart"), null, { renderer: "svg" });
function sourceStyle(input) {
  const {color, pattern} = input.closest(".reference-option").dataset;
  return {color, pattern: pattern ? pattern.split(" ").map(Number) : "solid"};
}
const stationInput = $("show-station-history");
const stationStyle = sourceStyle(stationInput);
const referenceInputs = [...document.querySelectorAll("[data-control]")];
const referenceSources = Object.fromEntries(referenceInputs.map((input) =>
  [input.dataset.control, {name: input.dataset.name, ...sourceStyle(input)}]));
const periodDays = { day: 1, month: 30, year: 365, "three-years": 1095, all: Infinity };
const minute = HOUR / 60;
const state = {
  mode: settings.default_mode,
  metric: "temperature",
  period: "day",
  units: "us",
  current: null,
  history: null,
  loading: false,
  viewport: null,
  controls: new Set(),
  showStation: true,
  references: {},
  referenceCheckedAt: {},
  controlErrors: new Set(),
};
let requestId = 0;
let timelineDomain = null;
let renderWindow;
function rememberViewport(event) {
  let zoom = event.batch?.[0] ?? event;
  if (!numeric(zoom.start) || !numeric(zoom.end)) zoom = chart.getOption().dataZoom?.[0];
  if (!timelineDomain || !numeric(zoom?.start) || !numeric(zoom?.end)) return;
  state.viewport = timelineDomain.seasonal ? {start: zoom.start, end: zoom.end} : visibleWindow(timelineDomain, zoom);
  renderPeriodSelection();
  if (timelineDomain.seasonal) return;
  if (usesDailyHistory(periodDays[state.period], state.viewport) !== timelineDomain.daily) renderChart();
  else renderWindow(state.viewport);
}
chart.on("datazoom", rememberViewport);

function currentWindow() {
  const days = periodDays[state.period];
  return visibleWindow(timelineDomain, timelineRange(timelineDomain, days, state.viewport));
}
function zoomTo(view) {
  chart.dispatchAction({type: "dataZoom", ...timelineRange(timelineDomain, periodDays[state.period], view)});
}
function moveWindow(direction) {
  const view = currentWindow();
  const offset = direction * (timelineDomain.daily ? DAY : HOUR);
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
const timestamp = (value) =>
  typeof value === "string" &&
  /(?:Z|[+-]\d\d:\d\d)$/.test(value) &&
  Number.isFinite(Date.parse(value));
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
  rain: {label: "Rainfall", field: "rain_mm", convert: rain},
  solar: {label: "Solar irradiance", field: "solar_w_m2"},
};

function validEnvelope(data) {
  if (data.schema_version !== 1 || data.kind !== state.mode)
    throw new Error("The feed does not match the selected data source.");
}
function validCurrent(data) {
  validEnvelope(data);
  if (
    data.station?.id !== settings.station.id ||
    !timestamp(data.observed_at) ||
    !data.outdoor ||
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
  return data;
}
function validHistory(data) {
  validEnvelope(data);
  if (
    data.station_id !== settings.station.id ||
    !timestamp(data.through) ||
    !Array.isArray(data.hourly) ||
    !Array.isArray(data.daily) ||
    (data.recent !== undefined && !Array.isArray(data.recent))
  )
    throw new Error("The history feed is incomplete.");
  for (const series of [data.recent ?? [], data.hourly, data.daily]) {
    let previous = -Infinity;
    for (const row of series) {
      if (
        !timestamp(row.at) ||
        Date.parse(row.at) <= previous ||
        Date.parse(row.at) > Date.parse(data.through)
      )
        throw new Error("History timestamps are invalid.");
      previous = Date.parse(row.at);
      for (const field of [
        "temperature_c",
        "humidity_pct",
        "wind_speed_m_s",
        "wind_gust_m_s",
        "rain_mm",
      ]) {
        if (row[field] !== null && !numeric(row[field]))
          throw new Error("History contains an invalid value.");
      }
      for (const field of ["temperature_min_c", "temperature_max_c", "solar_w_m2"]) {
        if (
          row[field] !== undefined &&
          row[field] !== null &&
          !numeric(row[field])
        )
          throw new Error("History contains an invalid optional value.");
      }
    }
  }
  return data;
}
function validReference(data, key) {
  if (data.schema_version !== 1 || data.kind !== "reference" || data.source?.id !== key ||
      !["modeled", "observed"].includes(data.source.type) || typeof data.source.name !== "string" ||
      !numeric(data.source.elevation_m) || !Array.isArray(data.daily) ||
      !Number.isFinite(Date.parse(data.start_date)) || !Number.isFinite(Date.parse(data.end_date)))
    throw new Error("Invalid reference metadata");
  let previous = -Infinity;
  for (const row of data.daily) {
    if (!timestamp(row.at) || Date.parse(row.at) <= previous) throw new Error("Invalid reference dates");
    previous = Date.parse(row.at);
    for (const field of ["temperature_min_c", "temperature_max_c", "rain_mm"])
      if (row[field] !== null && !numeric(row[field])) throw new Error("Invalid reference value");
    for (const field of ["humidity_pct", "wind_speed_m_s"])
      if (row[field] != null && (!numeric(row[field]) || row[field] < 0))
        throw new Error("Invalid reference value");
    if (numeric(row.rain_mm) && row.rain_mm < 0 || numeric(row.temperature_min_c) &&
        numeric(row.temperature_max_c) && row.temperature_min_c > row.temperature_max_c || row.humidity_pct > 100)
      throw new Error("Invalid reference range");
  }
  return data;
}
async function readJSON(url, signal) {
  const response = await fetch(url, { signal, cache: "no-cache" });
  if (!response.ok) throw new Error(`Feed returned HTTP ${response.status}.`);
  return response.json();
}
function notice(text, error = false) {
  $("notice-text").textContent = text;
  $("notice").classList.toggle("error", error);
}
function selected(group, value) {
  document
    .querySelectorAll(`[data-${group}]`)
    .forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset[group] === value),
      ),
    );
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
    ? `${data.kind === "sample" ? "Sample observation" : "Observed"} · ${timeFormat.format(new Date(data.observed_at))}`
    : state.loading
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
    status.textContent = state.loading ? "Connecting" : "Unavailable";
    return;
  }
  const age = (Date.now() - Date.parse(state.current.observed_at)) / 60000;
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
function renderChart() {
  renderPeriodSelection();
  const seasonal = ["seasons", "monsoon"].includes(state.period);
  $("monsoon-source").hidden = state.period !== "monsoon";
  const days = periodDays[state.period];
  const daily = !seasonal && usesDailyHistory(days, state.viewport);
  const history = state.history;
  const resolution = seasonal ? "Seasonal" : daily ? "Daily" : "Hourly";
  const sampleEnd = history?.through ?? state.current?.observed_at;
  const end = state.mode === "sample" && sampleEnd ? Date.parse(sampleEnd) : Date.now();
  const selectRows = (data) => {
    const selectedRows = (data?.[daily || seasonal ? "daily" : "hourly"] ?? []).filter(
      (row) => Date.parse(row.at) <= end,
    );
    return seasonal ? seasonalRows(selectedRows, state.period === "monsoon", settings.station.timezone) : selectedRows;
  };
  let rows = state.showStation ? selectRows(history) : [];
  const {label, field, convert = (value) => numeric(value) ? value : null} = metrics[state.metric];
  const stationName = state.mode === "sample" ? "Sample station" : settings.station.name;
  const stationSubtitle = state.showStation
    ? `${stationName} history · Mountain Time`
    : `${stationName} hidden · Mountain Time`;
  $("history-resolution").textContent = `${resolution} summaries`;
  const canCompare = daily || seasonal;
  $("reference-sources").disabled = !canCompare;
  const activeControls = [];
  let hasEligibleSource = false;
  for (const input of referenceInputs) {
    const key = input.dataset.control;
    const supportsMetric = input.dataset.metrics.split(" ").includes(state.metric);
    hasEligibleSource ||= supportsMetric;
    input.disabled = !supportsMetric;
    input.checked = supportsMetric && state.controls.has(key);
    if (canCompare && input.checked) activeControls.push(key);
  }
  const showReferences = activeControls.length > 0;
  if (showReferences)
    for (const key of activeControls)
      if (!state.referenceCheckedAt[key]) loadReference(key);
  $("reference-summary").textContent = canCompare
    ? "Chart source settings ↓" : "Daily references · expand beyond 24h ↓";
  const selectedReferences = showReferences
    ? activeControls.map((key) => state.references[key]).filter(Boolean) : [];
  const temperatureFields = [["temperature_max_c", "high"], ["temperature_min_c", "low"]];
  const referenceFields = state.metric === "temperature" ? temperatureFields : [[field, state.metric === "rain" ? "precipitation" : label.toLowerCase()]];
  const hasReferenceValue = (row) => referenceFields.some(([key]) => numeric(row[key]));
  const comparisons = selectedReferences.filter((data) => data.daily.some(hasReferenceValue)).map((data) => ({
    source: data.source,
    rows: selectRows(data),
  }));
  const controlNote = !canCompare ? "Widen past 24h or choose 30d to compare daily references."
    : !hasEligibleSource ? "No references report the selected metric."
    : !showReferences ? "Select sources to compare regional weather."
    : activeControls.map((key) => {
      const {name} = referenceSources[key];
      const data = state.references[key];
      const failed = state.controlErrors.has(key);
      if (!data) return failed ? `${name} could not be loaded. Reselect to retry.` : `Loading ${name}…`;
      const last = data.daily.findLast(hasReferenceValue);
      const coverage = last ? `through ${dateFormat.format(new Date(last.at))}` : "no values for this measurement";
      return `${name} · ${coverage}${failed ? " (refresh failed)" : ""}`;
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
    .sort((a, b) => seasonal ? a.start - b.start : Date.parse(a.at) - Date.parse(b.at));
  $("history-range").textContent = !endpoints.length ? "No history available" : seasonal
    ? `${endpoints[0].label} – ${endpoints.at(-1).label}`
    : `Available ${dateFormat.format(new Date(endpoints[0].at))} – ${dateFormat.format(new Date(endpoints.at(-1).at))}`;
  const referenceHasData = comparisons.some((item) => item.rows.some(hasReferenceValue));
  const stationFields = state.metric === "temperature" ? temperatureFields : [[field, label.toLowerCase()]];
  if (state.metric === "wind") stationFields.push(["wind_gust_m_s", "peak gust"]);
  const plottedFields = stationFields.filter(([key]) => rows.some((row) => numeric(row[key])));
  const stationHasData = plottedFields.length > 0;
  function describeCoverage(view) {
    const inWindow = (row) => !view || (Date.parse(row.at) >= view.from && Date.parse(row.at) <= view.to);
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
    const selectionPrompt = canCompare && hasEligibleSource
      ? "Choose observations or\nreference history to display." : `Show ${stationName} to display history.`;
    const emptyMessage = !state.showStation && !showReferences ? selectionPrompt
      : state.loading ? "Loading history…"
      : state.metric === "solar" ? "No solar observations in this period." : seasonal ? "Seasonal comparisons need daily history." : "No observations in this period.";
    timelineDomain = null;
    chart.clear();
    chart.setOption({
      title: {
        text: emptyMessage,
        left: "center",
        top: "center",
        textStyle: { color: "#a1b0ab", fontSize: 14, fontWeight: "normal" },
      },
    });
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
    const allSymbols = seasonal || state.period === "day";
    let hasIsolatedPoints = false;
    const data = dataRows.map((row, index) => {
      const value = [seasonal ? index : Date.parse(row.at), convert(row[key])];
      if (line && !allSymbols && numeric(value[1]) &&
          !numeric(dataRows[index - 1]?.[key]) && !numeric(dataRows[index + 1]?.[key])) {
        hasIsolatedPoints = true;
        return {value, symbol: marker};
      }
      return value;
    });
    return {
      name,
      type: line ? "line" : "bar",
      showSymbol: allSymbols || hasIsolatedPoints,
      symbol: allSymbols ? marker : "none",
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
  for (const item of comparisons) {
    const source = referenceSources[item.source.id];
    for (const [key, suffix] of referenceFields) {
      if (!item.rows.some((row) => numeric(row[key]))) continue;
      series.push(makeSeries(`${source.name} · ${suffix}`, key, source, item.rows));
    }
  }
  if (comparisons.length && stationHasData && !seasonal && timestamp(history?.record_started_at)) {
    series[0].markLine = {
      symbol: "none", lineStyle: {color: stationStyle.color, type: "dashed"},
      data: [{xAxis: Date.parse(history.record_started_at), name: state.mode === "sample" ? "Sample station begins" : history.deployment?.phase === "production" && state.current?.outdoor?.verified ? "Verified WS90 begins" : "Local pilot begins"}],
      label: {formatter: "{b}", color: stationStyle.color, position: "insideEndTop"},
    };
  }
  // Keep the selected dates when switching between hourly and daily records.
  const first = Math.min(Date.parse(endpoints[0].at), state.viewport?.from ?? Infinity);
  timelineDomain = seasonal ? {seasonal: true} : {...timeDomain(first, end, days), daily};
  const zoom = seasonal ? state.viewport ?? {start: 0, end: 100} : timelineRange(timelineDomain, days, state.viewport);
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
    const step = daily ? "one day" : "one hour";
    $("timeline-earlier").setAttribute("aria-label", `Move window ${step} earlier`);
    $("timeline-later").setAttribute("aria-label", `Move window ${step} later`);
    renderWindow(visibleWindow(timelineDomain, zoom));
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
      // ECharts needs the toolbox mounted for native drag selection.
      toolbox: {
        itemSize: 0, itemGap: 0, showTitle: false,
        feature: {dataZoom: {yAxisIndex: "none"}},
      },
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
        backgroundColor: "#22302e",
        borderColor: "#43534a",
        textStyle: { color: "#e8ebe4" },
        formatter: (entries) => {
          const date = new Date(entries[0].value[0]);
          const title = seasonal ? rows[entries[0].value[0]].label
            : daily ? dateFormat.format(date) : `Hour starting ${timeFormat.format(date)}`;
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
            return `${entry.marker}${entry.seriesName}: ${value}${seasonal ? ` · ${row?.coverage?.[meta.key] ?? 0}/${row?.expectedDays} days` : row?.field_sources?.[meta.key] === "rcc-acis" ? " · RCC-ACIS supplemental report" : ""}`;
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
          formatter: (value) => seasonal ? value.replace(" ", "\n") : daily ?
            dateFormat.format(new Date(value)).replace(", ", "\n") : hourFormat.format(new Date(value)),
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
          // Apply a resized 24h window when the handle is released so it can change resolution.
          realtime: state.period !== "day",
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
    true,
  );
  chart.dispatchAction({type: "takeGlobalCursor", key: "dataZoomSelect", dataZoomSelectActive: true});
  const notes = [];
  if (seasonal) notes.push("Summaries use reported days. Hover or tap to see coverage.");
  if (state.metric === "rain" && referenceHasData)
    notes.push("Reference precipitation can include melted snow.");
  if (state.metric === "solar") notes.push("Solar averages include nighttime readings.");
  description.textContent = notes.join(" ");
  description.hidden = !notes.length;
  const sources = stationHasData
    ? stationName + (referenceHasData ? " and selected references" : "")
    : "selected references";
  const measurement = state.metric === "temperature" ? "temperature lows and highs" : label.toLowerCase();
  $("chart").setAttribute("aria-label", `${resolution} ${measurement} chart for ${sources}`);
}
async function load({ refresh = false } = {}) {
  const id = ++requestId;
  const source =
    state.mode === "sample"
      ? new URL("./data/sample/", location.href).href
      : settings.feed;
  state.loading = true;
  if (!refresh) {
    state.current = null;
    state.history = null;
    renderCurrent();
    renderChart();
    selected("mode", state.mode);
    notice(
      state.mode === "sample"
        ? "Station readings and history are illustrative samples. Selected controls use real, attributed reference data."
        : "Connecting to the station feed…",
    );
  }
  if (!source) {
    state.loading = false;
    notice(
      "The live feed is not configured for this preview address. Sample mode is available; no live readings are shown.",
      true,
    );
    $("json-link").hidden = true;
    renderCurrent();
    renderChart();
    return;
  }
  $("json-link").href = `${source}current.json`;
  $("json-link").hidden = false;
  const signal = AbortSignal.timeout(15000);
  const [current, history] = await Promise.allSettled([
    readJSON(`${source}current.json`, signal).then(validCurrent),
    readJSON(`${source}history.json`, signal).then(validHistory),
  ]);
  if (id !== requestId) return;
  state.loading = false;
  if (current.status === "fulfilled") state.current = current.value;
  if (history.status === "fulfilled") state.history = history.value;
  if (
    state.current?.deployment?.dataset_id &&
    state.history?.deployment?.dataset_id !==
      state.current.deployment.dataset_id
  ) {
    state.history = null;
  }

  if (state.mode === "live") {
    if (current.status !== "fulfilled")
      notice(
        state.current
          ? "The latest refresh failed. Showing the last successfully received observation and its original timestamp."
          : "The live observation feed is unavailable. No sample readings are substituted. Please try again later.",
        true,
      );
    else if (history.status !== "fulfilled" && state.history)
      notice("History refresh failed. Showing the previously received history and its original dates.", true);
    else if (!state.history)
      notice(
        "Current observations are available; the history feed is unavailable.",
      );
    else if (state.history.through !== state.current.observed_at)
      notice("Current observations and history have different update times. Each retains its original timestamp; the next refresh will check again.");
    else
      notice(
        state.current.outdoor.verified
          ? "Station observations · timestamps and sensor provenance are included in the public JSON feed."
          : "Sensor mapping is unverified. Primary temperature and humidity may come from an auxiliary sensor.",
      );
  } else if (!state.current || !state.history)
    notice(
      "Sample data could not be loaded. Serve the built site over HTTP and try again.",
      true,
    );
  renderCurrent();
  renderChart();
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
      if (group === "mode") load();
      else {
        renderCurrent();
        renderChart();
      }
    });
}
async function loadReference(key) {
  state.referenceCheckedAt[key] = Date.now();
  try {
    state.references[key] = validReference(await readJSON(new URL(`${key}.json`, settings.reference_feed), AbortSignal.timeout(15000)), key);
    state.controlErrors.delete(key);
  } catch {
    state.controlErrors.add(key);
  }
  renderChart();
}
stationInput.addEventListener("change", (event) => {
  state.showStation = event.target.checked;
  if (["seasons", "monsoon"].includes(state.period)) state.viewport = null;
  renderChart();
});
for (const input of referenceInputs) {
  const key = input.dataset.control;
  input.addEventListener("change", () => {
    if (["seasons", "monsoon"].includes(state.period)) state.viewport = null;
    if (state.controlErrors.has(key) || Date.now() - state.referenceCheckedAt[key] >= 3600000)
      delete state.referenceCheckedAt[key];
    if (input.checked) state.controls.add(key);
    else state.controls.delete(key);
    state.controlErrors.delete(key);
    renderChart();
  });
}
new ResizeObserver(() => chart.resize()).observe($("chart"));
setInterval(renderStatus, 60000);
setInterval(() => {
  if (state.mode === "live" && !state.loading) load({ refresh: true });
  for (const input of referenceInputs) {
    const key = input.dataset.control;
    if (input.checked && !input.matches(":disabled") && Date.now() - state.referenceCheckedAt[key] >= 3600000)
      loadReference(key);
  }
}, 300000);
await load();
