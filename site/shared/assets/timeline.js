// Keep a dragged time window stable as fresh observations extend the domain.
export function timelineRange(domain, days, view) {
  const span = domain.end - domain.start;
  if (!(span > 0)) return { start: 0, end: 100 };
  const from = view?.from ?? (Number.isFinite(days) ? domain.end - days * 86400000 : domain.start);
  const to = view?.to ?? domain.end;
  const start = Math.max(0, Math.min(100, (from - domain.start) / span * 100));
  const end = Math.max(0, Math.min(100, (to - domain.start) / span * 100));
  return start < end ? { start, end } : { start: 0, end: 100 };
}
