import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {once} from "node:events";
import {mkdtemp, readFile, rm} from "node:fs/promises";
import {createServer} from "node:http";
import {tmpdir} from "node:os";
import {extname, join} from "node:path";
import test from "node:test";
import {setTimeout as delay} from "node:timers/promises";
import { DAY, HOUR } from "../site/shared/assets/timeline.js";

const browser = ["chromium", "chromium-browser", "google-chrome"]
  .find((command) => spawnSync(command, ["--version"], {stdio: "ignore"}).status === 0);

async function waitFor(read, ready) {
  for (let attempt = 0; attempt < 100; attempt++) {
    const value = await read();
    if (ready(value)) return value;
    await delay(50);
  }
  assert.fail("Timed out waiting for the chart or browser");
}

function devtools(socket) {
  const pending = new Map();
  let id = 0;
  socket.addEventListener("message", ({data}) => {
    const {id, result, error} = JSON.parse(data);
    const request = pending.get(id);
    if (!request) return;
    pending.delete(id);
    if (error) request.reject(new Error(error.message));
    else request.resolve(result);
  });
  return (method, params) => new Promise((resolve, reject) => {
    pending.set(++id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
}

test("repeated preset, slider pan, and plot drag select the dates under the pointer", {
  skip: browser ? false : "Chromium or Chrome is required for the pointer regression",
  timeout: 25000,
}, async () => {
  const root = new URL("../dist/canones/", import.meta.url);
  const read = (name) => readFile(new URL(name, root));
  const sample = JSON.parse(await read("data/sample/history.json"));
  const anchor = Date.parse(sample.through);
  const current = JSON.parse(await read("data/sample/current.json"));
  const config = JSON.parse(await read("assets/site-config.json"));
  const reference = {
    schema_version: 1, kind: "reference",
    source: {id: "bodega", name: "Bodega Marine test data", type: "observed", elevation_m: 19.2},
    start_date: "2020-01-01", end_date: sample.through,
    daily: [sample.daily.length, 0].flatMap((days) => sample.daily.map((row) => ({
      ...row, at: new Date(Date.parse(row.at) - days * DAY).toISOString(),
    }))),
  };
  const fixture = {
    "/assets/site-config.json": config,
    "/feed/current.json": {...current, kind: "live"},
    "/feed/history.json": {...sample, kind: "live"},
    "/references/bodega.json": reference,
    "/references/valles-caldera.json": {
      ...reference, source: {...reference.source, id: "valles-caldera"},
    },
  };
  for (const [key, offset] of [["bodega", -DAY], ["valles-caldera", 0]]) {
    const through = new Date(anchor + offset).toISOString();
    fixture[`/references/hourly/${key}.json`] = {
      schema_version: 1, kind: "reference", through,
      source: {...reference.source, id: key},
      hourly: sample.hourly.filter(({at}) => Date.parse(at) + HOUR <= anchor).map((row) => ({
        ...row, at: new Date(Date.parse(row.at) + offset).toISOString(),
      })),
    };
  }
  const mime = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json"};
  const server = createServer(async (req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    const file = path === "/" ? "/index.html" : path;
    res.setHeader("Content-Type", mime[extname(file)] ?? "application/octet-stream");
    try {
      res.end(fixture[file] ? JSON.stringify(fixture[file]) : await read(file.slice(1)));
    } catch {
      res.writeHead(404).end();
    }
  });
  const profile = await mkdtemp(join(tmpdir(), "canones-timeline-"));
  let chrome;
  let socket;
  try {
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    const origin = `http://127.0.0.1:${server.address().port}`;
    config.environments.prod = {
      ...config.environments.prod, station: origin, data: origin + "/feed/", reference_feed: origin + "/references/",
    };
    chrome = spawn(browser, [
      "--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-first-run",
      "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1280,1000", "about:blank",
    ], {stdio: "ignore"});
    const port = await waitFor(
      () => readFile(join(profile, "DevToolsActivePort"), "utf8").then((data) => data.split("\n")[0], () => null),
      Boolean,
    );
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = targets.find(({type}) => type === "page");
    socket = new WebSocket(page.webSocketDebuggerUrl);
    await Promise.race([
      once(socket, "open"),
      once(socket, "error").then(() => assert.fail("Could not connect to Chromium")),
    ]);
    const call = devtools(socket);
    async function evaluate(expression) {
      const {result, exceptionDetails} = await call("Runtime.evaluate", {expression, returnByValue: true});
      assert(!exceptionDetails, exceptionDetails?.exception?.description);
      return result.value;
    }
    await call("Page.enable");
    await call("Emulation.setEmulatedMedia", {features: [{name: "prefers-reduced-motion", value: "reduce"}]});
    const now = anchor + HOUR;
    await call("Page.addScriptToEvaluateOnNewDocument", {source: `
      window.previewNow = ${now};
      Date.now = () => window.previewNow;
      const schedule = window.setInterval;
      window.setInterval = (callback, period) => period === 300000
        ? (window.refreshFeed = callback) : schedule(callback, period);
      window.chartInstance = () => window.echarts?.getInstanceByDom(document.getElementById("chart"));
    `});
    await call("Page.navigate", {url: origin});
    const view = () => evaluate(`(() => {
      const chart = window.chartInstance?.();
      const grid = chart?.getModel()?.getComponent("grid", 0)?.coordinateSystem?.getRect();
      if (!grid) return null;
      const box = chart.getDom().getBoundingClientRect();
      const at = (x) => Math.round(chart.convertFromPixel({xAxisIndex: 0}, x));
      const left = Math.round(box.x + grid.x + .24 * grid.width);
      const right = Math.round(box.x + grid.x + .69 * grid.width);
      return {
        bounds: [at(grid.x), at(grid.x + grid.width)],
        domainEnd: chart.getOption().xAxis[0].max,
        resolution: document.getElementById("history-resolution").textContent,
        target: [at(left - box.x), at(right - box.x)],
        x: [left, right],
        y: Math.round(box.y + grid.y + grid.height / 2),
        msPerPixel: (at(grid.x + grid.width) - at(grid.x)) / grid.width,
        handles: [...document.querySelectorAll('#chart svg path[fill="#759b85"]')]
          .map((element) => element.getBoundingClientRect().toJSON()).sort((a,b) => a.x - b.x),
        series: chart.getOption().series.map(({name}) => name),
      };
    })()`);
    const click = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
    async function setDates([from, to]) {
      await click("#timeline-dates summary");
      await waitFor(() => evaluate('document.getElementById("timeline-from").value'), Boolean);
      await evaluate(`
        document.getElementById("timeline-from").valueAsNumber = ${from};
        document.getElementById("timeline-to").valueAsNumber = ${to};
        document.getElementById("timeline-dates-form").requestSubmit();
      `);
    }
    const drag = async (start, end, y) => {
      await call("Input.dispatchMouseEvent", {type: "mouseMoved", x: start, y});
      await call("Input.dispatchMouseEvent", {type: "mousePressed", x: start, y, button: "left", buttons: 1, clickCount: 1});
      for (const fraction of [.25, .5, .75, 1]) {
        await call("Input.dispatchMouseEvent", {type: "mouseMoved", x: start + fraction * (end - start), y, buttons: 1});
      }
      await call("Input.dispatchMouseEvent", {type: "mouseReleased", x: end, y, button: "left", clickCount: 1});
    };
    const initial = await waitFor(view, (v) => v?.series.length);
    assert.deepEqual(initial.bounds, [now - DAY, now]);
    assert.equal(initial.resolution, "Five-minute observations");
    assert.deepEqual(initial.series, ["Secco Spring · temperature"]);
    const labels = await evaluate(`(() => {
      const option = window.chartInstance().getOption();
      const series = option.series[0];
      const dataIndex = series.data.length - 1;
      const value = series.data[dataIndex];
      return [
        option.xAxis[0].axisLabel.formatter(value[0]),
        option.tooltip[0].formatter([{value, dataIndex, seriesName: series.name, marker: ""}]),
      ];
    })()`);
    assert.match(labels[0], /Sat/);
    assert.match(labels[1], /Five minutes ending Sat, Aug 15/);
    const olderDay = [anchor - 2 * DAY, anchor - DAY];
    await setDates(olderDay);
    const widened = await view();
    assert.deepEqual(widened.bounds, olderDay);
    assert.equal(widened.resolution, "Hourly summaries");
    await click('[data-period="week"]');
    const week = await view();
    assert.deepEqual(week.bounds, [now - 7 * DAY, now]);
    assert.equal(week.resolution, "Hourly summaries");
    await click('[data-period="month"]');
    const daily = await view();
    assert.deepEqual(daily.bounds, [now - 30 * DAY, now]);
    assert.equal(daily.resolution, "Daily summaries");
    await click('[data-control="bodega"]');
    await waitFor(view, (v) => v?.series.some((name) => name.startsWith("Bodega")));
    await evaluate('document.getElementById("chart").scrollIntoView({block: "center", behavior: "instant"})');

    for (let cycle = 0; cycle < 3; cycle++) {
      await click('[data-period="year"]');
      const preset = await view();
      const [left, right] = preset.handles;
      const midpoint = Math.round((left.x + right.x + right.width) / 2);
      await drag(midpoint, midpoint - 180 - 50 * cycle, Math.round(left.y + left.height / 2));
      const panned = await waitFor(view, (v) => v?.bounds[1] < now - DAY);
      assert(Math.abs(panned.bounds[1] - panned.bounds[0] - 365 * DAY) <= 1);
      await drag(...(cycle % 2 ? panned.x.toReversed() : panned.x), panned.y);
      const selected = await view();
      for (let i = 0; i < 2; i++) {
        assert(Math.abs(selected.bounds[i] - panned.target[i]) <= panned.msPerPixel,
          `Cycle ${cycle + 1}, expected ${panned.target}, got ${selected.bounds}`);
      }
      await click('[data-metric="rain"]');
      assert.deepEqual((await view()).bounds, selected.bounds);
      await click('[data-metric="temperature"]');
    }

    await click('[data-period="year"]');
    for (const [index, offset] of [[0, 32], [1, -32]]) {
      const before = await view();
      const handle = before.handles[index];
      const x = Math.round(handle.x + handle.width / 2);
      await drag(x, x + offset, Math.round(handle.y + handle.height / 2));
      const after = await view();
      assert(Math.abs(after.bounds[1 - index] - before.bounds[1 - index]) <= 1);
      assert(Math.sign(after.bounds[index] - before.bounds[index]) === Math.sign(offset));
    }

    const dates = [Date.UTC(2025, 10, 10, 7), Date.UTC(2025, 10, 15, 7)];
    await setDates(dates);
    assert.deepEqual((await view()).bounds, dates);
    await evaluate('window.previewNow += 3600000; window.refreshFeed();');
    const refreshed = await waitFor(view, (v) => v?.domainEnd === now + 3600000);
    assert.deepEqual(refreshed.bounds, dates);

    await click("#show-station-history");
    await click('[data-metric="solar"]');
    assert.equal(await view(), null);
    await click('[data-metric="temperature"]');
    assert.deepEqual((await view()).bounds, dates);
    await click("#show-station-history");

    await click('[data-period="week"]');
    assert.deepEqual((await view()).bounds, [now + HOUR - 7 * DAY, now + HOUR]);
    await click('[data-control="valles-caldera"]');
    const hourly = await waitFor(view, (v) =>
      v?.series.some((name) => name.startsWith("Bodega")) && v.series.some((name) => name.startsWith("Valles Caldera")));
    assert.deepEqual(hourly.bounds, [now + HOUR - 7 * DAY, now + HOUR]);
    assert(await evaluate('document.querySelector("[data-control=santa-fe]").matches(":disabled")'));
    assert.match(await evaluate('document.getElementById("control-note").textContent'), /Bodega Marine .*delayed/);
    fixture["/references/hourly/valles-caldera.json"] = {};
    await evaluate('window.previewNow += 900000; window.refreshFeed();');
    await waitFor(() => evaluate('document.getElementById("control-note").textContent'),
      (text) => /Valles Caldera .*refresh failed/.test(text));
    assert((await view()).series.some((name) => name.startsWith("Valles Caldera")));
    await click('[data-period="month"]');
    await waitFor(view, (v) => v?.series.some((name) => name.startsWith("Valles Caldera")));
    await click('[data-period="day"]');
    await click('[data-mode="sample"]');
    const sampleView = await waitFor(view, (v) => v?.domainEnd === anchor);
    assert.deepEqual(sampleView.bounds, [anchor - DAY, anchor]);
    assert.equal(sampleView.resolution, "Five-minute observations");
  } finally {
    socket?.close();
    if (chrome && chrome.exitCode === null && chrome.signalCode === null) {
      const exited = once(chrome, "exit");
      chrome.kill();
      await exited;
    }
    server.close();
    await rm(profile, {recursive: true, force: true, maxRetries: 3});
  }
});
