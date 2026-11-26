export const HOUR = 3600000;
export const DAY = 24 * HOUR;

export function usesDailyHistory(presetDays, view) {
  // Allow one millisecond of rounding when converting slider percentages to dates.
  return presetDays > 1 || (view != null && view.to - view.from > DAY + 1);
}

export function timeDomain(first, now, days) {
  const start = Number.isFinite(days) ? Math.min(first, now - days * DAY) : first;
  return {start, end: now};
}

export function visibleWindow(domain, zoom) {
  const span = domain.end - domain.start;
  return {
    from: Math.round(domain.start + span * zoom.start / 100),
    to: Math.round(domain.start + span * zoom.end / 100),
  };
}

export function shiftWindow(domain, view, offset) {
  const width = view.to - view.from;
  const from = Math.max(domain.start, Math.min(domain.end - width, view.from + offset));
  return {from, to: from + width};
}

export function calendarDayOffset(from, direction, timeZone) {
  const format = new Intl.DateTimeFormat("en", {
    timeZone, year: "numeric", month: "numeric", day: "numeric", hourCycle: "h23",
    hour: "numeric", minute: "numeric", second: "numeric", fractionalSecondDigits: 3,
  });
  const wallTime = (instant) => {
    const {year, month, day, hour, minute, second, fractionalSecond} = Object.fromEntries(
      format.formatToParts(instant).map(({type, value}) => [type, Number(value)]),
    );
    const date = new Date(0);
    date.setUTCFullYear(year, month - 1, day);
    date.setUTCHours(hour, minute, second, fractionalSecond);
    return date.getTime();
  };
  const wallTarget = wallTime(from) + direction * DAY;
  const approximate = from + direction * DAY;
  // Check both offsets around a transition. Use the earlier repeated time or advance through a gap.
  const candidates = [approximate - DAY, approximate + DAY]
    .map((probe) => wallTarget + probe - wallTime(probe))
    .sort((a, b) => a - b);
  return (candidates.find((instant) => wallTime(instant) === wallTarget) ?? candidates.at(-1)) - from;
}

// Keep a dragged time window stable as fresh observations extend the domain.
export function timelineRange(domain, days, view) {
  const span = domain.end - domain.start;
  if (!(span > 0)) return { start: 0, end: 100 };
  const from = view?.from ?? (Number.isFinite(days) ? domain.end - days * DAY : domain.start);
  const to = view?.to ?? domain.end;
  const start = Math.max(0, Math.min(100, (from - domain.start) / span * 100));
  const end = Math.max(0, Math.min(100, (to - domain.start) / span * 100));
  return start < end ? { start, end } : { start: 0, end: 100 };
}
