# Weather hosting module

Creates Git-backed Pages sites and their custom domains/CNAMEs, an R2 observation
bucket, a public data domain, public-read CORS, and disabled r2.dev access.
`data.tf` requires exactly one active DNS zone in the supplied account.

Call from an environment root with an inherited Cloudflare provider. Inputs are
specified in `variables.tf`: account ID, zone name, GitHub repository identity,
site map (including each build output directory), and observation storage
settings. They contain no credentials.
Outputs `site_urls` and `publisher` describe public endpoints and publisher
settings. The root owns provider versions, authentication, and state.

The bucket has `prevent_destroy` in all environments. Production and test callers
must supply distinct project names, hostnames, buckets, state keys, and publisher
credentials. This module provisions hosting; it does not enable collector uploads
or populate the bucket. Pages needs authorized repository access and committed
site assets before deployment.
