module "weather_hosting" {
  source = "../../modules/weather-hosting"

  cloudflare_account_id = "0053a5ff40688ef8b8b7f71c3ed46cbe"
  zone_name             = "iceburg.net"
  github_repository = {
    production_branch = "notprod"
    owner             = "briceburg"
    owner_id          = "490144"
    name              = "canones-weather"
    id                = "1456122766"
  }
  sites = {
    hub = {
      project_name = "iceburg-weather-notprod"
      hostname     = "weather-notprod.iceburg.net"
      output_dir   = "dist/hub"
    }
    canones = {
      project_name = "canones-weather-notprod"
      hostname     = "canones.weather-notprod.iceburg.net"
      output_dir   = "dist/canones"
    }
  }
  observations = {
    bucket_name = "canones-weather-notprod"
    hostname    = "data.weather-notprod.iceburg.net"
    key_prefix  = "canones/"
  }
}
