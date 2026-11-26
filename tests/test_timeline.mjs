import assert from "node:assert/strict";
import test from "node:test";
import { DAY, HOUR, calendarDayOffset, calendarDayStart, shiftWindow, timeDomain, timelineWindow, usesDailyHistory, windowFromPercent } from "../site/shared/assets/timeline.js";

test("a live 24h preset ends at now with stale or newly started history", () => {
  const now = Date.UTC(2026, 10, 24, 19, 35);
  for (const first of [now - 4 * DAY, now - HOUR]) {
    const domain = timeDomain(first, now, 1);
    assert.deepEqual(timelineWindow(domain, 1), {from: now - DAY, to: now});
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

test("daily movement keeps the station wall-clock start across daylight saving", () => {
  for (const [start, nextDay] of [
    ["2026-03-08T00:00:00.125-07:00", "2026-03-09T00:00:00.125-06:00"],
    ["2026-11-01T00:00:00.125-06:00", "2026-11-02T00:00:00.125-07:00"],
  ]) {
    const from = Date.parse(start);
    const next = Date.parse(nextDay);
    const width = 30 * DAY;
    const view = {from, to: from + width};
    const domain = {start: from - DAY, end: view.to + 2 * DAY};
    const move = (window, direction) => shiftWindow(
      domain, window, calendarDayOffset(window.from, direction, "America/Denver"),
    );
    const later = move(view, 1);
    assert.deepEqual(later, {from: next, to: next + width});
    assert.deepEqual(move(later, -1), view);
  }
});

test("daily movement advances through a skipped hour and selects the first repeated hour", () => {
  for (const [start, nextDay] of [
    ["2026-03-07T02:30:00-07:00", "2026-03-08T03:30:00-06:00"],
    ["2026-10-31T01:30:00-06:00", "2026-11-01T01:30:00-06:00"],
  ]) {
    const from = Date.parse(start);
    assert.equal(from + calendarDayOffset(from, 1, "America/Denver"), Date.parse(nextDay));
  }
});

test("the pending day starts at station midnight on both daylight saving transitions", () => {
  for (const [now, midnight] of [
    ["2026-03-08T18:00:00Z", "2026-03-08T07:00:00Z"],
    ["2026-11-01T18:00:00Z", "2026-11-01T06:00:00Z"],
  ]) {
    assert.equal(calendarDayStart(Date.parse(now), "America/Denver"), Date.parse(midnight));
  }
});

test("panning a 24h view stays hourly and widening it enables daily comparisons", () => {
  const domain = {start: 0, end: 31 * DAY};
  const initial = timelineWindow(domain, 1);
  const earlier = shiftWindow(domain, initial, -2 * HOUR);
  assert.equal(usesDailyHistory(1, earlier), false);
  assert.equal(usesDailyHistory(1, {from: earlier.from - 2 * HOUR, to: earlier.to}), true);
  assert.equal(usesDailyHistory(30, earlier), true);
});

test("7d shows the latest week while retaining earlier history for panning", () => {
  const domain = {start: Date.UTC(2016, 0, 1), end: Date.UTC(2026, 7, 15)};
  assert.deepEqual(timelineWindow(domain, 7), {from: domain.end - 7 * DAY, to: domain.end});
  assert.deepEqual(timelineWindow(domain, Infinity), {from: domain.start, to: domain.end});
});

test("a dragged date range survives new observations and safely clamps missing history", () => {
  const view = {from: Date.UTC(2024, 0, 1), to: Date.UTC(2025, 0, 1)};
  for (const end of [Date.UTC(2026, 0, 1), Date.UTC(2026, 0, 2)]) {
    const domain = {start: Date.UTC(2016, 0, 1), end};
    assert.deepEqual(timelineWindow(domain, 365, view), view);
  }
  const domain = {start: view.to, end: view.to + DAY};
  assert.deepEqual(timelineWindow(domain, 365, view), {from: domain.start, to: domain.end});
  assert.deepEqual(windowFromPercent(domain, {start: 25, end: 75}), {
    from: domain.start + DAY / 4,
    to: domain.end - DAY / 4,
  });
});
