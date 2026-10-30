# AI assistants (MCP)

Glad serves an [MCP](https://modelcontextprotocol.io) server at `<APP_URL>/mcp`, so that an AI assistant (Claude Code, Claude Desktop, Cursor…) can analyse the data, check it and enter new values. Each adult of the household creates their keys in **Settings › MCP access**.

## Keys

- A key is shown once, at its creation; only its SHA-256 hash is stored. It reads `glad_<prefix>_<secret>`, and the prefix listed in the settings identifies it.
- A key is **read-only** by default. With **Allow writing**, the client also sees the write tools; a read-only key neither lists nor calls them.
- A key sees the data of the whole household, as its owner does in the application. It stops working when it is disabled or deleted, when its owner is deactivated, or when its owner becomes a child of the household.
- Every tool call is logged with its arguments and result; the settings show the 50 latest calls of the user.

The client sends the key in the `Authorization: Bearer` header, for example with Claude Code:

```sh
claude mcp add --transport http glad https://glad.example.com/mcp --header "Authorization: Bearer glad_…"
```

Claude Desktop and Cursor take the same URL and header in their MCP configuration. The connectors of claude.ai and of the mobile application require OAuth, which Glad does not offer.

Serve the application over HTTPS: the reverse proxy must also protect `/mcp`, which the Django HTTPS redirect does not cover.

## Tools

| Tool | Access | What it returns or does |
| --- | --- | --- |
| `get_net_worth` | read | Net worth, its changes, every asset by class with the total and share of each class, the loans, the share of each member, and the assets in another currency (not converted) |
| `get_net_worth_history` | read | Monthly net worth by asset class |
| `get_allocation` | read | Assets by class and by liquidity; the assets worth less than nothing are summed apart |
| `get_upcoming_deadlines` | read | Loan ends, rent revisions, lease ends, notices, DPE, account milestones… |
| `get_pending_checks` | read | Recurring ledger entries not checked yet, rent arrears, lease checklist issues |
| `list_accounts`, `get_account` | read | Savings, investment accounts and other assets: holder, values, deposits, holdings, XIRR (or why it is missing), deposit ceiling |
| `get_data_quality_issues` | read | Holdings without asset class, ISIN or purchase value, accounts without deposit, savings without rate, ceilings exceeded |
| `list_properties`, `get_property` | read | Values, loans, median monthly flows, leases, ledger totals of the year |
| `get_property_ledger` | read | Income and expenses of a property between two dates, by category and by occurrence |
| `get_lmnp_summary` | read | LMNP figures, cerfa boxes and checklist of a property for a year |
| `list_leases`, `get_lease` | read | Rent periods, payments, arrears and checklist |
| `get_budget`, `list_budget_categories` | read | Budget of a year with the previous year, budget categories |
| `add_account_value` | write | Balance of a savings account, cash of an investment account, value of an other asset |
| `add_account_deposit` | write | Deposit or withdrawal on a savings or investment account; a second deposit of the same amount on the same day is refused |
| `update_deposit` | write | Corrected amount, date, origin or source of a deposit |
| `delete_deposit` | write, destructive | A deposit deleted, only when called again with `confirm=true` |
| `update_account` | write | Name, institution, notes or interest rate of an account |
| `update_holding` | write | Name, ISIN, asset class, initial value and quantity of a holding |
| `record_trade` | write | A purchase or sale of an existing holding (quantity, unit price, fees): a history entry with the new quantity, and the cash debited or credited; the purchase price is left unchanged |
| `add_property_value` | write | Market value estimate of a property |
| `add_ledger_entry` | write | Income or expense of a property, recurring or not |
| `check_ledger_occurrence` | write | An occurrence checked: rent received, charge paid |
| `save_budget_line` | write | New or changed budget line |

The write tools fill the same forms as the pages of the application (restricted to the changed fields for the updates), so the data goes through the same validation, and the errors go back to the assistant. The only deletion is `delete_deposit`: it first describes the deposit, deletes it only when called again with `confirm=true`, and is flagged as destructive so that the client asks you first. Changing or deleting a deposit keeps the balance value it created when it was entered.

Amounts are rounded to the cent and percentages to 2 decimals, both as strings; dates are plain ISO dates.

Names, notes and descriptions entered in the application reach the assistant as they are: an assistant allowed to write may act on text planted in them, so give write access only to the assistants you watch.
