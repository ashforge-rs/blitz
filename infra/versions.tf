# This configuration targets OpenTofu exclusively.
# Use `tofu init`, `tofu plan`, and `tofu apply` — not the Terraform CLI.
terraform {
  required_version = ">= 1.8, < 2.0"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}
