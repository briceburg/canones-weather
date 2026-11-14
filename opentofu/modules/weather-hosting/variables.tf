variable "cloudflare_account_id" {
  description = "Cloudflare account that owns the zone, Pages projects, and R2 bucket."
  type        = string
  validation {
    condition     = can(regex("^[a-f0-9]{32}$", var.cloudflare_account_id))
    error_message = "Provide a 32-character Cloudflare account ID."
  }
}

variable "github_repository" {
  description = "GitHub repository authorized through the Cloudflare GitHub app."
  type = object({
    production_branch = string
    owner             = string
    owner_id          = string
    name              = string
    id                = string
  })
}

variable "observations" {
  description = "Public observation storage and publisher path."
  type = object({
    bucket_name = string
    hostname    = string
    key_prefix  = string
  })
}

variable "sites" {
  description = "Pages sites keyed by role, with repository-relative output directories."
  type = map(object({
    project_name = string
    hostname     = string
    output_dir   = string
  }))
}

variable "zone_name" {
  description = "Existing active Cloudflare DNS zone containing all public hostnames."
  type        = string
}
