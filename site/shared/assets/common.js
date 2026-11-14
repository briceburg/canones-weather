const config = await fetch(new URL("./site-config.json", import.meta.url)).then(
  (response) => {
    if (!response.ok) throw new Error("Site configuration is unavailable.");
    return response.json();
  },
);
const environment = Object.values(config.environments).find((settings) =>
  [settings.hub, settings.station].some(
    (url) => new URL(url).hostname === location.hostname,
  ),
);
export const settings = {
  ...config,
  default_mode: environment?.default_mode ?? config.default_mode,
  feed: environment?.data ?? null,
};
for (const link of document.querySelectorAll("[data-route]")) {
  const route = link.dataset.route;
  link.href = environment
    ? environment[route]
    : `/${route === "station" ? "canones" : "hub"}/`;
}
