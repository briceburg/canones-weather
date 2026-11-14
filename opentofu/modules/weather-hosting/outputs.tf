output "publisher" {
  description = "Public endpoints and bucket settings; contains no write credentials."
  value = {
    bucket          = cloudflare_r2_bucket.observations.name
    endpoint_url    = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
    region          = "auto"
    key_prefix      = var.observations.key_prefix
    public_base_url = "https://${cloudflare_r2_custom_domain.observations.domain}/${trimsuffix(var.observations.key_prefix, "/")}"
  }
}

output "site_urls" {
  description = "Public website URLs by role."
  value       = { for role, domain in cloudflare_pages_domain.weather : role => "https://${domain.name}" }
}
