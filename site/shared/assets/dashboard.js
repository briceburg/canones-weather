import { settings } from "./common.js";

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
};
const colors = {
  temperature: "#e4b17b",
  humidity: "#9fbfd1",
  wind: "#a1c6ac",
  rain: "#9fbfd1",
};
let requestId = 0;

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
});

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
    !Array.isArray(data.daily)
  )
    throw new Error("The history feed is incomplete.");
  for (const series of [data.hourly, data.daily]) {
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
      for (const field of ["temperature_min_c", "temperature_max_c"]) {
        if (
          row[field] !== undefined &&
          row[field] !== null &&
          !numeric(row[field])
        )
          throw new Error("History contains an invalid temperature range.");
      }
    }
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
  const daily = ["year", "all"].includes(state.period);
  const history = state.history;
  const end = Date.parse(history?.through);
  const days = { day: 1, week: 7, month: 30, year: 365, all: Infinity }[
    state.period
  ];
  const rows = history
    ? history[daily ? "daily" : "hourly"].filter(
        (row) => Date.parse(row.at) > end - days * 86400000,
      )
    : [];
  const label = {
    temperature: "Temperature",
    humidity: "Relative humidity",
    wind: "Wind speed",
    rain: "Rainfall",
  }[state.metric];
  $("history-subtitle").textContent =
    `${state.mode === "sample" ? "Illustrative sample history" : "Station history"} · Mountain Time`;
  $("history-resolution").textContent = daily
    ? "Daily summaries · archive retained separately"
    : "Hourly summaries · archive retained separately";
  $("history-range").textContent = rows.length
    ? `${dateFormat.format(new Date(rows[0].at))} – ${dateFormat.format(new Date(rows.at(-1).at))}`
    : "No history available";
  const field = {
    temperature: "temperature_c",
    humidity: "humidity_pct",
    wind: "wind_speed_m_s",
    rain: "rain_mm",
  }[state.metric];
  if (!rows.some((row) => numeric(row[field]))) {
    chart.clear();
    chart.setOption({
      title: {
        text: state.loading
          ? "Loading history…"
          : "No observations in this period.",
        left: "center",
        top: "center",
        textStyle: { color: "#a1b0ab", fontSize: 14, fontWeight: "normal" },
      },
    });
    $("chart").setAttribute("aria-label", "No history data available.");
    $("chart-description").textContent = "";
    return;
  }
  const unit = units()[state.metric];
  const convert = {
    temperature: temp,
    humidity: (value) => (numeric(value) ? value : null),
    wind: speed,
    rain,
  }[state.metric];
  const makeSeries = (name, key, color, extra = {}) => ({
    name,
    type: state.metric === "rain" ? "bar" : "line",
    showSymbol: rows.length === 1,
    connectNulls: false,
    data: rows.map((row) => [Date.parse(row.at), convert(row[key])]),
    itemStyle: { color },
    lineStyle: { color, width: 2 },
    emphasis: { focus: "series" },
    ...extra,
  });
  const series = [makeSeries(label, field, colors[state.metric])];
  if (state.metric === "temperature" && daily) {
    series.push(
      makeSeries("Daily low", "temperature_min_c", "#9fbfd1", {
        lineStyle: { width: 1, type: "dashed", color: "#9fbfd1" },
      }),
    );
    series.push(
      makeSeries("Daily high", "temperature_max_c", "#bc8e84", {
        lineStyle: { width: 1, type: "dashed", color: "#bc8e84" },
      }),
    );
  }
  if (state.metric === "wind")
    series.push(
      makeSeries("Peak gust", "wind_gust_m_s", "#d7c7a4", {
        lineStyle: { width: 1, type: "dashed", color: "#d7c7a4" },
      }),
    );
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
      grid: { left: 10, right: 16, top: 34, bottom: 52, containLabel: true },
      legend: {
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
        formatter: (entries) =>
          `${timeFormat.format(new Date(entries[0].value[0]))}<br>${entries.map((entry) => `${entry.marker}${entry.seriesName}: ${numeric(entry.value[1]) ? entry.value[1].toFixed(state.metric === "rain" && state.units === "us" ? 2 : 1) + " " + unit : "Missing"}`).join("<br>")}`,
        axisPointer: { type: state.metric === "rain" ? "shadow" : "line" },
      },
      xAxis: {
        type: "time",
        boundaryGap: state.metric === "rain",
        axisLine: { lineStyle: { color: "#35433e" } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          hideOverlap: true,
          color: "#a1b0ab",
          formatter: (value) =>
            new Intl.DateTimeFormat("en-US", {
              timeZone: "America/Denver",
              ...(state.period === "day"
                ? { hour: "numeric" }
                : { month: "short", day: "numeric" }),
            }).format(new Date(value)),
        },
      },
      yAxis: {
        type: "value",
        scale: state.metric === "temperature",
        min: ["rain", "wind", "humidity"].includes(state.metric)
          ? 0
          : undefined,
        max: state.metric === "humidity" ? 100 : undefined,
        name: unit,
        nameTextStyle: { color: "#a1b0ab" },
        splitLine: { lineStyle: { color: "#283632", type: "dashed" } },
        axisLabel: { color: "#a1b0ab" },
      },
      dataZoom: [
        { type: "inside", zoomOnMouseWheel: "ctrl" },
        {
          type: "slider",
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
  const values = rows.map((row) => convert(row[field])).filter(numeric);
  const range = values.length
    ? `Values from ${Math.min(...values).toFixed(1)} to ${Math.max(...values).toFixed(1)} ${unit}.`
    : "No recorded values in this period.";
  $("chart-description").textContent =
    `${daily ? "Daily" : "Hourly"} ${state.metric === "rain" ? "rainfall totals" : state.metric === "wind" ? "average wind and maximum gusts" : state.metric === "temperature" && daily ? "mean temperature, with minimum and maximum" : `average ${label.toLowerCase()}`}. ${range} Gaps represent missing readings.`;
  $("chart").setAttribute(
    "aria-label",
    `${state.mode === "sample" ? "Sample" : "Station"} ${label.toLowerCase()} chart. ${range}`,
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
      ? "Design preview. All readings and history shown here are illustrative sample data, not station observations."
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
    else if (!state.history)
      notice(
        "Current observations are available; the history feed is unavailable.",
      );
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
      selected(group, state[group]);
      if (group === "mode") load();
      else {
        renderCurrent();
        renderChart();
      }
    });
}
new ResizeObserver(() => chart.resize()).observe($("chart"));
setInterval(renderStatus, 60000);
setInterval(() => {
  if (state.mode === "live" && !state.loading) load({ refresh: true });
}, 300000);
await load();
