output "publisher" {
  description = "Public endpoints and bucket settings; contains no write credentials."
  value       = module.weather_hosting.publisher
}

output "site_urls" {
  description = "Public website URLs by role."
  value       = module.weather_hosting.site_urls
}
