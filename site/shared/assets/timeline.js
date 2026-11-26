export const HOUR = 3600000;
export const DAY = 24 * HOUR;

export function usesDailyHistory(presetDays, view) {
  // Allow one millisecond of rounding at the two slider endpoints.
  return presetDays > 1 || (view != null && view.to - view.from > DAY + 1);
}

export function timeDomain(first, now, days) {
  const start = Number.isFinite(days) ? Math.min(first, now - days * DAY) : first;
  return {start, end: now};
}

export function windowFromPercent(domain, zoom) {
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

function changeWallTime(from, timeZone, change) {
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
  const wallStart = wallTime(from);
  const wallTarget = change(wallStart);
  const approximate = from + wallTarget - wallStart;
  // Check both offsets around a transition. Use the earlier repeated time or advance through a gap.
  const candidates = [approximate - DAY, approximate + DAY]
    .map((probe) => wallTarget + probe - wallTime(probe))
    .sort((a, b) => a - b);
  return candidates.find((instant) => wallTime(instant) === wallTarget) ?? candidates.at(-1);
}

export function calendarDayOffset(from, direction, timeZone) {
  return changeWallTime(from, timeZone, (wall) => wall + direction * DAY) - from;
}

export function calendarDayStart(from, timeZone) {
  return changeWallTime(from, timeZone, (wall) => Math.floor(wall / DAY) * DAY);
}

export function timelineWindow({start, end}, days, view) {
  if (view) {
    const from = Math.max(start, view.from);
    const to = Math.min(end, view.to);
    return from < to ? {from, to} : {from: start, to: end};
  }
  return {from: Math.max(start, end - days * DAY), to: end};
}
