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
  required_status_checks {
    strict   = true
    contexts = [
      "test (3.12)",
      "test (3.13)",
      "lint-and-typecheck",
    ]
  }

  # All review threads must be resolved.
  require_conversation_resolution = true

  # No direct pushes to master — PRs only.
  enforce_admins = false
}
