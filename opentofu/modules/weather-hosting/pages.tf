resource "cloudflare_pages_project" "weather" {
  for_each          = var.sites
  account_id        = var.cloudflare_account_id
  name              = each.value.project_name
  production_branch = var.github_repository.production_branch
  build_config = {
    build_command   = "bin/build-site"
    destination_dir = each.value.output_dir
  }
  source = {
    type = "github"
    config = {
      owner                          = var.github_repository.owner
      owner_id                       = var.github_repository.owner_id
      repo_name                      = var.github_repository.name
      repo_id                        = var.github_repository.id
      production_branch              = var.github_repository.production_branch
      production_deployments_enabled = true
      preview_deployment_setting     = "none"
      pr_comments_enabled            = false
    }
  }
}

resource "cloudflare_pages_domain" "weather" {
  for_each     = var.sites
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.weather[each.key].name
  name         = each.value.hostname
}

resource "cloudflare_dns_record" "pages" {
  for_each = var.sites
  # Associate custom domains before publishing their CNAMEs.
  depends_on = [cloudflare_pages_domain.weather]
  zone_id    = local.zone_id
  name       = each.value.hostname
  type       = "CNAME"
  content    = cloudflare_pages_project.weather[each.key].subdomain
  proxied    = true
  ttl        = 1
  comment    = "Managed by opentofu:canones-weather"
}
