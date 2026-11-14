# Reporttool

Reporttool renders key-value reports on the command line.

## Usage

```console
python3 -m reporttool [--format {table,json}] TITLE [KEY=VALUE ...]
```

For example, `python3 -m reporttool "Q3 Expenses" rent=1200 food=340.50` prints:

```text
Q3 Expenses
-----------
rent 1200
food 340.50
```

Pass `--format json` for machine-readable output:

```console
$ python3 -m reporttool --format json "Q3 Expenses" rent=1200 food=340.50
{"title": "Q3 Expenses", "rows": [["rent", "1200"], ["food", "340.50"]]}
```
