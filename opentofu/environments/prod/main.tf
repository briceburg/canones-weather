module "weather_hosting" {
  source = "../../modules/weather-hosting"

  cloudflare_account_id = "0053a5ff40688ef8b8b7f71c3ed46cbe"
  zone_name             = "iceburg.net"
  github_repository = {
    production_branch = "main"
    owner             = "briceburg"
    owner_id          = "490144"
    name              = "canones-weather"
    id                = "1456122766"
  }
  sites = {
    hub = {
      project_name = "iceburg-weather"
      hostname     = "weather.iceburg.net"
      output_dir   = "dist/hub"
    }
    canones = {
      project_name = "canones-weather"
      hostname     = "canones.weather.iceburg.net"
      output_dir   = "dist/canones"
    }
  }
  observations = {
    bucket_name = "canones-weather"
    hostname    = "data.weather.iceburg.net"
    key_prefix  = "canones/"
  }
}
