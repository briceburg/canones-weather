import assert from "node:assert/strict";
import test from "node:test";
import { DAY, HOUR, shiftWindow, timeDomain, timelineRange, visibleWindow } from "../site/shared/assets/timeline.js";

test("a live 24h preset ends at now with stale or newly started history", () => {
  const now = Date.UTC(2026, 10, 24, 19, 35);
  for (const first of [now - 4 * DAY, now - HOUR]) {
    const domain = timeDomain(first, now, 1);
    assert.deepEqual(visibleWindow(domain, timelineRange(domain, 1, null)), {from: now - DAY, to: now});
    assert.equal(domain.start, Math.min(first, now - DAY));
  }
  assert.deepEqual(timeDomain(now - 4 * DAY, now, Infinity), {start: now - 4 * DAY, end: now});
});

test("hourly and daily moves preserve the window width at both edges", () => {
  const domain = {start: 0, end: 31 * DAY};
  const dayView = {from: 30 * DAY, to: 31 * DAY};
  assert.deepEqual(shiftWindow(domain, dayView, -2 * HOUR), {from: dayView.from - 2 * HOUR, to: dayView.to - 2 * HOUR});
  const monthView = {from: DAY, to: 31 * DAY};
  const earliest = shiftWindow(domain, monthView, -2 * DAY);
  assert.deepEqual(earliest, {from: 0, to: 30 * DAY});
  assert.deepEqual(shiftWindow(domain, earliest, 2 * DAY), monthView);
});

test("3y presets the latest 1095 days while retaining earlier history for panning", () => {
  const domain = {start: Date.UTC(2016, 0, 1), end: Date.UTC(2026, 7, 15)};
  const zoom = timelineRange(domain, 1095, null);
  const first = domain.start + (domain.end - domain.start) * zoom.start / 100;
  assert(Math.abs(first - (domain.end - 1095 * DAY)) < 1);
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
  assert.deepEqual(timelineRange({start: view.to, end: view.to + DAY}, 365, view), {start: 0, end: 100});
});
