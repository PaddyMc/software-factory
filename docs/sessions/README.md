# Session logs

One file per piece of work, `YYYY-MM-DD-<task id or topic>.md`, so tasks running in parallel never
edit the same file (older logs are one file per day, `YYYY-MM-DD.md`):

```markdown
## [HH:MM] <task id or topic>: <title>

- What changed and why, the files touched, and the commands run (with results).
```

Every factory task adds its own file here; the factory's `session_log` gate fails without one.
