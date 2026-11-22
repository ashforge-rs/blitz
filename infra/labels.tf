# Labels used by dependabot, pr-title workflow, and release-please.
# Managed here to ensure they exist before any automation runs.

locals {
  labels = {
    "dependencies" = {
      color       = "0075ca"
      description = "Dependency update"
    }
    "github-actions" = {
      color       = "e4e669"
      description = "GitHub Actions workflow change"
    }
    "conventional commit" = {
      color       = "0e8a16"
      description = "PR title follows Conventional Commits"
    }
    "invalid title" = {
      color       = "e11d48"
      description = "PR title does not follow Conventional Commits"
    }
    "bug" = {
      color       = "d73a4a"
      description = "Something is not working"
    }
    "enhancement" = {
      color       = "a2eeef"
      description = "New feature or improvement"
    }
    "documentation" = {
      color       = "0075ca"
      description = "Documentation change"
    }
  }
}

resource "github_issue_label" "labels" {
  for_each = local.labels

  repository  = github_repository.blitz.name
  name        = each.key
  color       = each.value.color
  description = each.value.description
}
