# Fixture repositories contain test modules that only run inside a materialized case.
# Never collect those files as tests of the factory itself.
collect_ignore_glob = ["*"]
