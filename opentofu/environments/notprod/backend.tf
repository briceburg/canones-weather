terraform {
  backend "s3" {
    encrypt      = true
    use_lockfile = true
    lock_tags    = { ObjectType = "Lock" }
    state_tags   = { ObjectType = "State" }
  }
}
