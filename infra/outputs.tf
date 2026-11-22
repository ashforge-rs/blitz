output "repository_url" {
  description = "HTTPS clone URL of the managed repository."
  value       = github_repository.blitz.html_url
}

output "repository_node_id" {
  description = "GraphQL node ID — used internally by branch protection resources."
  value       = github_repository.blitz.node_id
  sensitive   = true
}
