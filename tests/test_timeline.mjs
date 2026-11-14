import assert from "node:assert/strict";
import test from "node:test";
import { timelineRange } from "../site/shared/assets/timeline.js";

const day = 86400000;

test("3y presets the latest 1095 days while retaining earlier history for panning", () => {
  const domain = {start: Date.UTC(2016, 0, 1), end: Date.UTC(2026, 7, 15)};
  const zoom = timelineRange(domain, 1095, null);
  const first = domain.start + (domain.end - domain.start) * zoom.start / 100;
  assert(Math.abs(first - (domain.end - 1095 * day)) < 1);
  assert.equal(zoom.end, 100);
  assert.deepEqual(timelineRange(domain, Infinity, null), {start: 0, end: 100});
});

test("a dragged date range survives new observations and safely clamps missing history", () => {
  const view = {from: Date.UTC(2024, 0, 1), to: Date.UTC(2025, 0, 1)};
  for (const end of [Date.UTC(2026, 0, 1), Date.UTC(2026, 0, 2)]) {
    const domain = {start: Date.UTC(2016, 0, 1), end};
    const zoom = timelineRange(domain, 365, view);
    assert(Math.abs(domain.start + (end - domain.start) * zoom.start / 100 - view.from) < 1);
    assert(Math.abs(domain.start + (end - domain.start) * zoom.end / 100 - view.to) < 1);
  }
  assert.deepEqual(timelineRange({start: view.to, end: view.to}, 365, view), {start: 0, end: 100});
  assert.deepEqual(timelineRange({start: view.to, end: view.to + day}, 365, view), {start: 0, end: 100});
});
