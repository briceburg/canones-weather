data "cloudflare_zones" "selected" {
  name = var.zone_name
  account = {
    id = var.cloudflare_account_id
  }
  status = "active"

  lifecycle {
    postcondition {
      condition     = length(self.result) == 1
      error_message = "Expected exactly one active ${var.zone_name} zone in the configured Cloudflare account."
    }
  }
}

locals {
  zone_id = one(data.cloudflare_zones.selected.result).id
}
