resource "cloudflare_r2_bucket" "observations" {
  account_id    = var.cloudflare_account_id
  name          = var.observations.bucket_name
  location      = "wnam"
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_managed_domain" "development" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.observations.name
  enabled     = false
}

resource "cloudflare_r2_custom_domain" "observations" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.observations.name
  domain      = var.observations.hostname
  enabled     = true
  zone_id     = local.zone_id
  min_tls     = "1.2"
}

resource "cloudflare_r2_bucket_cors" "public_read" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.observations.name
  rules = [{
    id = "public-read"
    allowed = {
      methods = ["GET", "HEAD"]
      origins = ["*"]
    }
    expose_headers  = ["ETag", "Last-Modified"]
    max_age_seconds = 3600
  }]
}
