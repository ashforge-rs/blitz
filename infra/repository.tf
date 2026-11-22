resource "github_repository" "blitz" {
  name        = var.repository_name
  description = "FastAPI boilerplate"
  visibility  = "public"

  # Allow only squash merges to keep history clean.
  allow_squash_merge = true
  allow_merge_commit = false
  allow_rebase_merge = false

  # Auto-delete head branches after merge.
  delete_branch_on_merge = true

  # Enable issues; disable unused features.
  has_issues   = true
  has_projects = false
  has_wiki     = false

  # Require up-to-date branches before merging.
  allow_update_branch = true

  vulnerability_alerts = true
}
