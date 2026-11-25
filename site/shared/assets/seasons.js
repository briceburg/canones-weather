// Summaries of observed days, not estimates for missing days or climate normals.
const numeric = (value) => typeof value === "number" && Number.isFinite(value);
const fields = {
  temperature_c: "mean", temperature_min_c: "min", temperature_max_c: "max",
  solar_w_m2: "mean", humidity_pct: "mean", wind_speed_m_s: "mean", wind_gust_m_s: "max", rain_mm: "sum",
};

export function seasonalRows(daily, monsoon, timeZone) {
  if (!daily.length) return [];
  const localDate = new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  });
  const dates = daily.map((row) => {
    const parts = Object.fromEntries(localDate.formatToParts(new Date(row.at)).map(({type, value}) => [type, value]));
    return { row, year: +parts.year, month: +parts.month, day: +parts.day };
  });
  const key = ({year, month}) => monsoon ? year :
    (month < 3 ? year - 1 : year) * 4 + (month < 3 || month === 12 ? 3 : Math.floor((month - 3) / 3));
  const groups = new Map();
  for (let k = key(dates[0]); k <= key(dates.at(-1)); k++) {
    const year = monsoon ? k : Math.floor(k / 4);
    const season = k % 4;
    const start = monsoon ? Date.UTC(year, 5, 15) : Date.UTC(year, season * 3 + 2, 1);
    const stop = monsoon ? Date.UTC(year, 9, 1) : Date.UTC(year, season * 3 + 5, 1);
    groups.set(k, {
      label: monsoon ? `Monsoon ${year}` : `${["Spring", "Summer", "Autumn", "Winter"][season]} ${year}${season === 3 ? `–${String(year + 1).slice(-2)}` : ""}`,
      start,
      expectedDays: (stop - start) / 86400000,
      values: Object.fromEntries(Object.keys(fields).map((field) => [field, []])),
    });
  }
  for (const date of dates) {
    if (monsoon && (date.month < 6 || date.month > 9 || (date.month === 6 && date.day < 15))) continue;
    const group = groups.get(key(date));
    for (const field of Object.keys(fields)) {
      if (numeric(date.row[field])) group.values[field].push(date.row[field]);
    }
  }
  return [...groups.values()].map(({label, start, expectedDays, values}) => {
    const result = {label, start, expectedDays, coverage: {}};
    for (const [field, operation] of Object.entries(fields)) {
      const data = values[field];
      result.coverage[field] = data.length;
      const total = data.reduce((a, b) => a + b, 0);
      result[field] = !data.length ? null : operation === "min" ? Math.min(...data) :
        operation === "max" ? Math.max(...data) : operation === "sum" ? total : total / data.length;
    }
    return result;
  });
}
