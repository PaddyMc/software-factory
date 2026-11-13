# Reporttool

Reporttool renders key-value reports on the command line.

## Usage

```console
python3 -m reporttool TITLE [KEY=VALUE ...]
```

For example, `python3 -m reporttool "Q3 Expenses" rent=1200 food=340.50` prints:

```text
Q3 Expenses
-----------
rent 1200
food 340.50
```
