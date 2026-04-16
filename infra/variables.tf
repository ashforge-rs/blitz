variable "github_token" {
  description = "GitHub Personal Access Token with repo and admin:org scopes."
  type        = string
  sensitive   = true
}

variable "github_owner" {
  description = "GitHub organisation or user that owns the repository."
  type        = string
  default     = "ashforge-rs"
}

variable "repository_name" {
  description = "Name of the repository to manage."
  type        = string
  default     = "blitz"
}
