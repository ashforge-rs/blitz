resource "github_branch_protection" "master" {
  repository_id = github_repository.blitz.node_id
  pattern       = "master"

  # At least one approval required before merge.
  required_pull_request_reviews {
    required_approving_review_count = 1
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = true
  }

  # CI must pass before merge.
  # Context strings must match the exact job name shown on GitHub Actions.
  required_status_checks {
    strict   = true
    contexts = [
      "Test (Python 3.12)",
      "Test (Python 3.13)",
      "Lint & Type-check",
    ]
  }

  # All review threads must be resolved.
  require_conversation_resolution = true

  # Enforce protections for admins too — prevents accidental direct pushes.
  enforce_admins = true

  lifecycle {
    prevent_destroy = true
  }
}
