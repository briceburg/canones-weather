import assert from "node:assert/strict";
import test from "node:test";
import { seasonalRows as summarize } from "../site/canones/assets/seasons.js";

const seasonalRows = (daily, monsoon = false) => summarize(daily, monsoon, "America/Denver");

const day = (at, temperature_c, rain_mm) => ({ at, temperature_c, rain_mm });

test("winter crosses years, includes leap day, and preserves missing seasons", () => {
  const winter = seasonalRows([
    {...day("2023-12-31T07:00:00Z", 10, 0), temperature_min_c: 5, temperature_max_c: 14, wind_gust_m_s: 10},
    {...day("2024-01-01T07:00:00Z", 20, null), temperature_min_c: 15, temperature_max_c: null, wind_gust_m_s: 5},
    {...day("2024-02-29T07:00:00Z", null, 2), temperature_max_c: 18},
  ])[0];
  assert.equal(winter.label, "Winter 2023–24");
  assert.equal(winter.expectedDays, 91);
  assert.equal(winter.temperature_c, 15);
  assert.equal(winter.temperature_max_c, 16);
  assert.equal(winter.temperature_min_c, 10);
  assert.equal(winter.coverage.temperature_max_c, 2);
  assert.equal(winter.wind_gust_m_s, 10);
  assert.equal(winter.rain_mm, 2);
  assert.equal(winter.coverage.rain_mm, 2);
  const gaps = seasonalRows([
    day("2024-03-01T07:00:00Z", 0, null),
    day("2024-09-01T06:00:00Z", 0, null),
  ]);
  assert.equal(gaps.length, 3);
  assert.equal(gaps[1].temperature_c, null);
  assert.equal(gaps[1].rain_mm, null);
});

test("monsoon includes June 15 and September 30 in station time only", () => {
  const monsoon = seasonalRows([
    day("2025-06-15T05:00:00Z", 1, 100), // June 14 in Denver.
    day("2025-06-15T06:00:00Z", 1, 2),
    day("2025-09-30T06:00:00Z", 1, 3),
    day("2025-10-01T06:00:00Z", 1, 100),
  ], true)[0];
  assert.equal(monsoon.rain_mm, 5);
  assert.equal(monsoon.expectedDays, 108);
  assert.equal(monsoon.coverage.rain_mm, 2);
});
