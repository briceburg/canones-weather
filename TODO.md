# Follow-ups

## Experimental sunlight relative to clear sky

- After permanent WS90 mounting, pilot a pvlib clear-sky model using the station's
  location, elevation, and observation intervals. Compare several confirmed clear
  days before interpreting the light-derived irradiance.
- Exclude nighttime, low sun, known shading, and missing observations. Account for
  the sensor's light-meter uncertainty and document model/calibration assumptions.
- Compare observed and modeled solar energy over identical valid intervals for
  daily, seasonal, and monsoon summaries; report coverage.
- Label the result “Sunlight relative to clear sky — experimental.” A clear-sky
  index is not cloud-cover percentage. Keep derived estimates separate from
  measured observations and weather-network submissions.

References: [pvlib clear-sky models](https://pvlib-python.readthedocs.io/en/stable/user_guide/modeling_topics/clearsky.html),
[Ecowitt sensor specifications](https://shop.ecowitt.com/collections/wifi-sensor/products/ws90).

## Public API clients

Investigate Cloudflare error 1010 for Python urllib's default user agent on the
data hostname. Browser requests and identified clients work. Inspect the
host-specific security configuration before changing shared zone settings; avoid
broad account permissions merely to address this exception.

## Reference refresh operations

Watch scheduled reference-workflow results and the providers' actual coverage
dates. GitHub disables public-repository schedules after 60 days of inactivity;
re-enable them if needed. Evaluate an external scheduler if that operational
constraint becomes unsuitable; do not couple reference fetches to local collection.
