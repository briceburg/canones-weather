import { settings } from "./common.js";
import { seasonalRows } from "./seasons.js";
import { timelineRange } from "./timeline.js";

const $ = (id) => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  month: "short",
  day: "numeric",
  year: "numeric",
});
const timeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const chart = window.echarts.init($("chart"), null, { renderer: "svg" });
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
  references: {},
  referenceCheckedAt: {},
  controlErrors: new Set(),
};
let requestId = 0;
let timelineDomain = null;
function rememberViewport() {
  const zoom = chart.getOption().dataZoom?.[0];
  if (!timelineDomain || !numeric(zoom?.start) || !numeric(zoom?.end)) return;
  const {start, end} = timelineDomain;
  state.viewport = timelineDomain.seasonal ? {start: zoom.start, end: zoom.end} : {
    from: start + (end - start) * zoom.start / 100,
    to: start + (end - start) * zoom.end / 100,
  };
}
chart.on("datazoom", rememberViewport);

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
  temperature: {label: "Temperature", field: "temperature_c", color: "#e4b17b", convert: temp},
  humidity: {label: "Relative humidity", field: "humidity_pct", color: "#9fbfd1"},
  wind: {label: "Wind speed", field: "wind_speed_m_s", color: "#a1c6ac", convert: speed},
  rain: {label: "Rainfall", field: "rain_mm", color: "#9fbfd1", convert: rain},
  solar: {label: "Solar irradiance", field: "solar_w_m2", color: "#d7c7a4"},
};

function validEnvelope(data) {
  if (data.schema_version !== 1 || data.kind !== state.mode)
    throw new Error("The feed does not match the selected data source.");
}
function validCurrent(data) {
  validEnvelope(data);
  if (
    data.station?.id !== "canones" ||
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
    data.station_id !== "canones" ||
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
    if (numeric(row.rain_mm) && row.rain_mm < 0 || numeric(row.temperature_min_c) &&
        numeric(row.temperature_max_c) && row.temperature_min_c > row.temperature_max_c)
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
  if (state.viewport) rememberViewport();
  const seasonal = ["seasons", "monsoon"].includes(state.period);
  $("monsoon-source").hidden = state.period !== "monsoon";
  const daily = ["year", "three-years", "all"].includes(state.period);
  const history = state.history;
  const recent = state.period === "day" && Array.isArray(history?.recent);
  const resolution = seasonal ? "Seasonal" : daily ? "Daily" : recent ? "Five-minute" : "Hourly";
  const end = Date.parse(history?.through ?? state.current?.observed_at ?? new Date().toISOString());
  const days = { day: 1, month: 30, year: 365, "three-years": 1095, all: Infinity }[
    state.period
  ];
  const selectRows = (data) => {
    const selectedRows = (data?.[daily || seasonal ? "daily" : recent ? "recent" : "hourly"] ?? []).filter(
      (row) => Date.parse(row.at) <= end && (daily || seasonal || Date.parse(row.at) > end - days * 86400000),
    );
    return seasonal ? seasonalRows(selectedRows, state.period === "monsoon") : selectedRows;
  };
  let rows = selectRows(history);
  const {label, field, color, convert = (value) => numeric(value) ? value : null} = metrics[state.metric];
  const stationName = state.mode === "sample" ? "Sample station" : "Secco Creek";
  $("history-subtitle").textContent =
    `${state.mode === "sample" ? "Sample station history" : "Station history"} · Mountain Time`;
  $("history-resolution").textContent =
    seasonal ? "Days with data · partial seasons included" : `${resolution} summaries · archive retained separately`;
  const eligible = (daily || seasonal) && ["temperature", "rain"].includes(state.metric);
  const selectedReferences = [...state.controls].map((key) => state.references[key]).filter(Boolean);
  const comparisons = eligible ? selectedReferences.map((data) => ({
    source: data.source,
    rows: selectRows(data),
  })) : [];
  $("control-note").textContent = [...state.controls].some((key) => state.controlErrors.has(key)) ? "A control could not be loaded. Station data remains independent; uncheck and retry."
    : !eligible ? "Controls compare daily temperature ranges and precipitation in 1y, 3y, All, Seasons, or Monsoon."
    : state.controls.size > selectedReferences.length ? "Loading historical controls…"
    : selectedReferences.length ? selectedReferences.map((data) => `${data.source.name}: ${data.start_date}–${data.available_through ?? data.end_date}, ${Math.round(data.source.elevation_m)} m elevation.`).join(" ") +
      " Separate reference records; neither establishes past conditions at Secco Creek."
    : "Choose a control to overlay daily temperature ranges or precipitation; station observations remain separate.";
  if (seasonal && comparisons.length) {
    const periods = new Map([...rows, ...comparisons.flatMap((item) => item.rows)].map((row) => [row.start, row]));
    const templates = [...periods.values()].sort((a, b) => a.start - b.start);
    const align = (data) => templates.map((row) => data.find((item) => item.start === row.start) ??
      {label: row.label, start: row.start, expectedDays: row.expectedDays, coverage: {}});
    rows = align(rows);
    for (const item of comparisons) item.rows = align(item.rows);
  }
  const rangeRows = [...rows, ...comparisons.flatMap((item) => item.rows)].sort((a, b) => seasonal ? a.start - b.start : Date.parse(a.at) - Date.parse(b.at));
  $("history-range").textContent = !rangeRows.length ? "No history available" : seasonal
    ? `${rangeRows[0].label} – ${rangeRows.at(-1).label}`
    : `Available ${dateFormat.format(new Date(rangeRows[0].at))} – ${dateFormat.format(new Date(rangeRows.at(-1).at))}`;
  if (comparisons.length && timestamp(history?.record_started_at))
    $("control-note").textContent += ` ${state.mode === "sample" ? "Sample station" : "Local archive"} begins ${dateFormat.format(new Date(history.record_started_at))}.`;
  const referenceFields = state.metric === "temperature" ? ["temperature_min_c", "temperature_max_c"] : [field];
  const stationHasData = rows.some((row) => numeric(row[field]));
  const referenceHasData = comparisons.some((item) => item.rows.some((row) => referenceFields.some((key) => numeric(row[key]))));
  if (comparisons.length && !referenceHasData)
    $("control-note").textContent += " No selected control values overlap this window.";
  if (!stationHasData && !referenceHasData) {
    timelineDomain = null;
    chart.clear();
    chart.setOption({
      title: {
        text: state.loading
          ? "Loading history…"
          : state.metric === "solar" ? "No solar observations in this period." : seasonal ? "Seasonal comparisons need daily history." : "No observations in this period.",
        left: "center",
        top: "center",
        textStyle: { color: "#a1b0ab", fontSize: 14, fontWeight: "normal" },
      },
    });
    $("chart").setAttribute("aria-label", "No history data available.");
    $("chart-description").textContent = seasonal
      ? "Completed daily intervals build this view. Partial seasons and missing days are not extrapolated."
      : "";
    return;
  }
  const unit = units()[state.metric];
  const seriesMeta = new Map();
  const makeSeries = (name, key, color, extra = {}, dataRows = rows) => {
    seriesMeta.set(name, {rows: dataRows, key});
    return {
      name,
      type: state.metric === "rain" ? "bar" : "line",
      showSymbol: seasonal || dataRows.filter((row) => numeric(row[key])).length === 1,
      connectNulls: false,
      data: dataRows.map((row, index) => [seasonal ? index : Date.parse(row.at), convert(row[key])]),
      itemStyle: { color },
      lineStyle: { color, width: 2 },
      emphasis: { focus: "series" },
      ...extra,
    };
  };
  const series = stationHasData ? [
    makeSeries(comparisons.length ? `${stationName} · ${state.metric === "temperature" ? "mean" : label.toLowerCase()}` : state.metric === "temperature" ? "Mean temperature" : label, field, comparisons.length ? "#e4b17b" : color),
  ] : [];
  if (state.metric === "temperature" && !recent &&
      rows.some((row) => numeric(row.temperature_min_c) || numeric(row.temperature_max_c))) {
    for (const [suffix, key, rangeColor, style] of [
      ["low", "temperature_min_c", "#9fbfd1", "dotted"],
      ["high", "temperature_max_c", "#bc8e84", "dashed"],
    ]) {
      const seriesColor = comparisons.length ? "#e4b17b" : rangeColor;
      const prefix = comparisons.length ? `${stationName} · ` : "";
      series.push(makeSeries(`${prefix}${resolution} ${suffix}`, key, seriesColor, {
        lineStyle: {width: 1, type: style, color: seriesColor},
      }));
    }
  }
  if (state.metric === "wind" && stationHasData)
    series.push(
      makeSeries("Peak gust", "wind_gust_m_s", "#d7c7a4", {
        lineStyle: { width: 1, type: "dashed", color: "#d7c7a4" },
      }),
    );
  for (const item of comparisons) {
    const name = item.source.id === "daymet" ? "Daymet estimate" : "Abiquiu NOAA";
    const color = item.source.id === "daymet" ? "#b8a3cf" : "#86b4cb";
    for (const key of referenceFields) {
      if (!item.rows.some((row) => numeric(row[key]))) continue;
      const suffix = key === "temperature_min_c" ? "low" : key === "temperature_max_c" ? "high" : "precipitation";
      series.push(makeSeries(`${name} · ${suffix}`, key, color, {
        lineStyle: {color, width: 1.5, type: key === "temperature_min_c" ? "dashed" : "solid"},
      }, item.rows));
    }
  }
  if (comparisons.length && series.length && !seasonal && timestamp(history?.record_started_at)) {
    series[0].markLine = {
      symbol: "none", lineStyle: {color: "#e4b17b", type: "dashed"},
      data: [{xAxis: Date.parse(history.record_started_at), name: state.mode === "sample" ? "Sample station begins" : history.deployment?.phase === "production" && state.current?.outdoor?.verified ? "Verified WS90 begins" : "Local pilot begins"}],
      label: {formatter: "{b}", color: "#e4b17b", position: "insideEndTop"},
    };
  }
  timelineDomain = seasonal ? {start: 0, end: rows.length - 1, seasonal: true} :
    {start: Date.parse(rangeRows[0].at), end, seasonal: false};
  const zoom = seasonal ? state.viewport ?? {start: 0, end: 100} : timelineRange(timelineDomain, days, state.viewport);
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
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
        type: "scroll",
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
          const title = seasonal ? rows[entries[0].value[0]].label : (daily ? dateFormat : timeFormat).format(new Date(entries[0].value[0]));
          return `${title}<br>` + entries.map((entry) => {
            const meta = seriesMeta.get(entry.seriesName);
            const row = meta.rows[entry.dataIndex];
            const value = state.metric === "rain" && row?.precipitation_trace ? "Trace" : numeric(entry.value[1])
              ? entry.value[1].toFixed(state.metric === "rain" && state.units === "us" ? 2 : 1) + " " + unit : "Missing";
            return `${entry.marker}${entry.seriesName}: ${value}${seasonal ? ` · ${row?.coverage?.[meta.key] ?? 0}/${row?.expectedDays} days` : ""}`;
          }).join("<br>");
        },
        axisPointer: { type: state.metric === "rain" ? "shadow" : "line" },
      },
      xAxis: {
        type: seasonal ? "category" : "time",
        min: seasonal ? undefined : timelineDomain.start,
        max: seasonal ? undefined : end,
        ...(seasonal ? { data: rows.map((row) => row.label +
          (comparisons.length ? "" : !row.coverage[field] ? "\n(no data)" : row.coverage[field] < row.expectedDays ? "\n(partial)" : "")) } : {}),
        boundaryGap: state.metric === "rain",
        axisLine: { lineStyle: { color: "#35433e" } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          hideOverlap: true,
          color: "#a1b0ab",
          formatter: (value) => seasonal ? value.replace(" ", "\n") :
            new Intl.DateTimeFormat("en-US", {
              timeZone: "America/Denver",
              ...(state.period === "day"
                ? { hour: "numeric" }
                : { month: "short", ...(daily ? { year: "numeric" } : { day: "numeric" }) }),
            }).format(new Date(value)),
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
        { type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseMove: true, moveOnMouseWheel: false, ...zoom },
        {
          type: "slider",
          ...zoom,
          bottom: 4,
          height: 18,
          borderColor: "#35433e",
          backgroundColor: "#172422",
          fillerColor: "#a1c6ac18",
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
  const values = [...rows.map((row) => convert(row[field])), ...comparisons.flatMap((item) => item.rows.flatMap((row) => referenceFields.map((key) => convert(row[key]))))].filter(numeric);
  const range = values.length
    ? `Available values span ${Math.min(...values).toFixed(1)} to ${Math.max(...values).toFixed(1)} ${unit}.`
    : "No recorded values in this period.";
  $("chart-description").textContent = seasonal
    ? `${state.period === "monsoon" ? "Monsoon: June 15–September 30." : "Spring: March–May; summer: June–August; autumn: September–November; winter: December–February."} Means average recorded daily means; lows/highs and gusts are recorded extremes. Rain totals exclude missing days. Hover or tap for day counts; individual days may also be incomplete. No extrapolation or climate normals.`
    : `${resolution} ${state.metric === "rain" ? "rainfall totals" : state.metric === "wind" ? "average wind and maximum gusts" : state.metric === "temperature" && !recent ? "mean temperature, with minimum and maximum" : `average ${label.toLowerCase()}`}. ${range} Gaps represent missing readings.`;
  if (comparisons.length)
    $("chart-description").textContent += ` Controls retain their own daily reporting periods.${state.metric === "rain" ? " Reference precipitation includes snow water equivalent; the station series represents rainfall." : ""}${stationHasData ? "" : " No local daily values are available in this view yet; only the selected controls are shown."}`;
  if (state.metric === "solar")
    $("chart-description").textContent += " Solar means include nighttime readings. Sun angle, day length, shading, smoke, and clouds affect this light-derived estimate; it is not cloud-cover percentage.";
  $("chart").setAttribute(
    "aria-label",
    `${stationName}${comparisons.length ? " and reference" : ""} ${label.toLowerCase()} chart. ${range}`,
  );
}
async function load({ refresh = false } = {}) {
  const id = ++requestId;
  const source =
    state.mode === "sample"
      ? new URL("./data/sample/", location.href).href
      : settings.feed;
  if (!refresh) {
    state.current = null;
    state.history = null;
  }
  state.loading = true;
  renderCurrent();
  renderChart();
  selected("mode", state.mode);
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
  notice(
    state.mode === "sample"
      ? "Station readings and history are illustrative samples. Selected controls use real, attributed reference data."
      : "Connecting to the station feed…",
  );
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
      if (group === "period" || group === "mode") state.viewport = null;
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
for (const input of document.querySelectorAll("[data-control]")) {
  input.addEventListener("change", async () => {
    const key = input.dataset.control;
    if (["seasons", "monsoon"].includes(state.period)) state.viewport = null;
    state.controlErrors.delete(key);
    if (!input.checked) {
      state.controls.delete(key);
      renderChart();
      return;
    }
    state.controls.add(key);
    if (!["year", "three-years", "all", "seasons", "monsoon"].includes(state.period)) {
      state.period = "all";
      state.viewport = null;
      selected("period", state.period);
    }
    if (!["temperature", "rain"].includes(state.metric)) {
      state.metric = "temperature";
      selected("metric", state.metric);
    }
    renderChart();
    if (!state.references[key] || Date.now() - state.referenceCheckedAt[key] >= 3600000)
      await loadReference(key);
    renderChart();
  });
}
new ResizeObserver(() => chart.resize()).observe($("chart"));
setInterval(renderStatus, 60000);
setInterval(() => {
  if (state.mode === "live" && !state.loading) load({ refresh: true });
  for (const key of state.controls)
    if (Date.now() - state.referenceCheckedAt[key] >= 3600000) loadReference(key);
}, 300000);
await load();
