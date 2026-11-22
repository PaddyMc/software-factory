# Web UI mockups

Static mockups of the pages `factory web` serves, planned in [docs/plans/webui.md](../../plans/webui.md). They are the reference every web task matches.

Open them straight from a checkout: each one links the real stylesheet, `factory/web/static/app.css`, so what you see is what the server will serve.

| Page | Shows |
|---|---|
| [board.html](board.html) | The board: what needs you, what's running, every plan |
| [task.html](task.html) | One failed task: its next step, contract, runs and log |
| [transcript.html](transcript.html) | One agent run, step by step, with what the model thought before each step ([thoughts](../../plans/thoughts.md)) |
| [run.html](run.html) | The form that starts a plan run |
| [activity.html](activity.html) | Commands the page ran, and the latest log lines of every task |
| [plans.html](plans.html) | Every plan doc, with its tasks' statuses ([plan-pages](../../plans/plan-pages.md)) |
| [plan.html](plan.html) | One plan, rendered: its contents, its contracts as task rows with their statuses, and its task ids linked |

The data is made up. Links between the pages work, and the forms and buttons do nothing.

Change a page's look by changing these mockups and `app.css` together. The pages `factory web` renders use the same classes and structure.
