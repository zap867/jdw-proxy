# justdowork-proxy

Run **Claude Code** against a OpenAI/Anthropic-compatible relay that isn't a
faithful Anthropic endpoint.

The relay this was built for is `https://api.justwoker.icu`, but the messy parts
it fixes are generic: relays that drop tool calls, ignore the `tools` array, or
mangle streaming.

**You point Claude Code at this proxy on `http://127.0.0.1:8181` instead of at
the relay.** The proxy translates both ways, repairs the model's JSON, runs
web search itself, and hands Claude Code a clean, standards-shaped stream.

> **License:** free for personal, hobby, educational, research, non-profit and
> government use. **Commercial use — including reselling or hosting it as a
> paid service — requires a separate written license.** See [License](#license).

---

## What it fixes

| Problem at the relay | What the proxy does |
|---|---|
| Only honours tools literally named `read`/`write`/`edit`/`bash` | Sends those four natively with real schemas; every other tool goes through a `<tool_call>` text protocol |
| Model writes JSON with literal newlines and bad escapes, call is dropped | 4-step repair: strict parse → control chars → escape repair → bracket balancing |
| Streaming drops text and tool blocks (thinking deltas only) | Synthesises the SSE stream itself, with a ping every 3s so nothing times out |
| Cannot run `WebSearch` / `WebFetch` | The proxy runs DuckDuckGo / opens the page itself, and loops until the model answers |
| Huge histories cause 524 timeouts | Trims history to a char budget, truncates large tool output |
| Adds ~10.4k phantom input tokens to every request | `usage_baseline_tokens` corrects the reported number (the real cost stays — that's the relay's) |

---

## Requirements

* **Python 3.9+** or **[uv](https://docs.astral.sh/uv/) (Recommended)** — blazing fast environment & package runner.
* An API key for the relay you're pointing at (or 9Router configured with multiple keys).
* [Claude Code](https://claude.com/claude-code) (only if you want to run Claude Code through it).

---

## Quick start with `uv` (Recommended)

If you have `uv` installed:

```sh
# Start proxy directly (uv automatically resolves dependencies & venv in seconds)
uv run ccproxy.py

# Run offline tests
uv run test_offline.py
```

---

## Quick start — macOS / Linux

```sh
# 1. get the code
git clone https://github.com/zap867/jdw-proxy.git
cd jdw-proxy

# 2. (Optional if using 9Router) put your relay API key in
export UPSTREAM_API_KEY='sk-...'

# 3. start it (uses uv if available, or creates .venv automatically)
sh start.sh
```

You should see:

```
Starting ccproxy ... the exact URL is printed on the next line.
Press Ctrl+C to stop.

[20:18:39] ccproxy ready -> http://127.0.0.1:8181/v1   (upstream: https://api.justwoker.icu)
```

The `ccproxy ready ->` line is the authoritative one — it uses whatever
`listen_port` you set in `config.json`.

Leave that terminal running. Now open a **second** terminal:

```sh
cd justdowork-proxy
sh run-claude.sh
```

That starts Claude Code pointed at the proxy — **your global
`~/.claude/settings.json` is not modified**, so your other Claude Code setup
keeps working exactly as before.

> If `sh start.sh` says `python3: command not found`:
> macOS — `brew install python3`. Linux — `sudo apt install python3 python3-venv`.

---

## Quick start — Windows

**Before anything else:** install Python from
[python.org/downloads](https://www.python.org/downloads/) and, on the **first
screen of the installer**, tick:

```
[x] Add python.exe to PATH
```

If you miss that box, `start.bat` will tell you Python wasn't found — re-run the
installer, choose *Modify*, and add it.

Then, in **Command Prompt** or **PowerShell**:

```bat
:: 1. get the code
git clone https://github.com/abdurrehmandaudi/justdowork-proxy.git
cd justdowork-proxy

:: 2. put your relay API key in (this sets it permanently for your user)
setx UPSTREAM_API_KEY "sk-..."

::    IMPORTANT: setx only affects NEW windows. Close this one and open a new one.
```

Now start the proxy — you can just **double-click `start.bat`**, or run:

```bat
cd justdowork-proxy
start.bat
```

The first run creates `.venv` and installs the dependencies (about a minute).
When you see the "Starting ccproxy" banner, open a **second** window:

```bat
cd justdowork-proxy
run-claude.bat
```

`run-claude.bat` writes a temporary settings file (`%TEMP%\ccproxy-claude-settings.json`)
and passes it to Claude Code with `--settings`. Your global
`%USERPROFILE%\.claude\settings.json` is **not** modified.

> **Windows Firewall:** the proxy listens on `127.0.0.1` only, so Windows
> normally does not prompt. If you *do* get a firewall dialog, you can safely
> click Cancel — a loopback-only listener doesn't need an exception.

---

## Getting an API key

The key is the relay's key, not an Anthropic key. For the relay this was built
against, sign up at [api.justwoker.icu](https://api.justwoker.icu) and copy the
`sk-...` key from the dashboard.

You can give it to the proxy in **either** of two ways:

**Option A — environment variable** (recommended; keeps it out of the repo)

| | |
|---|---|
| macOS / Linux | `export UPSTREAM_API_KEY='sk-...'` (add to `~/.zshrc` to persist) |
| Windows | `setx UPSTREAM_API_KEY "sk-..."` then open a new terminal |

**Option B — `config.json`**

```jsonc
{
  "upstream_base_url": "https://api.justwoker.icu",
  "api_key": "sk-...",          // <-- here
  ...
}
```

`config.json` is git-ignored by default in spirit — **do not commit your key**.
The version in the repo ships with `"api_key": ""`.

---

## Check that it works

Open **<http://127.0.0.1:8181/>** in a browser. You get a live dashboard showing
where your tokens are going: requests, input/output tokens, the relay's phantom
tokens, tool calls, dropped calls, retries, and a bar per request. It refreshes
every 2 seconds.

Open **<http://127.0.0.1:8181/health>** for a machine-readable check:

```json
{"ok": true, "upstream": "https://api.justwoker.icu", "model": "claude-opus-4-8", "key_set": true}
```

`"key_set": true` means the proxy found your key. If it's `false`, see
[Getting an API key](#getting-an-api-key).

You can also run the offline test suite — it needs **no** API key, because it
starts its own mock upstream:

```sh
sh run_tests.sh          # macOS / Linux
```
```bat
run-tests.bat            :: Windows
```

Expected:

```
RESULT:  70 pass, 0 fail
```

---

## Running Claude Code through it

`run-claude.sh` (macOS/Linux) and `run-claude.bat` (Windows) do the same four
things:

1. check that the proxy is actually answering, and tell you clearly if it isn't
2. set `ANTHROPIC_BASE_URL` to the proxy
3. set `ANTHROPIC_API_KEY=dummy` — the *real* key lives inside the proxy, so
   Claude Code never needs to see it
4. set `ENABLE_TOOL_SEARCH=false` — the proxy relies on this being off

Any normal Claude Code flag passes straight through:

```sh
sh run-claude.sh --continue
sh run-claude.sh --model claude-opus-4-8
```

**Doing it by hand** (if you'd rather not use the scripts):

```sh
export ANTHROPIC_BASE_URL='http://127.0.0.1:8181'
export ANTHROPIC_API_KEY='dummy'
export ENABLE_TOOL_SEARCH='false'
claude
```
```bat
set ANTHROPIC_BASE_URL=http://127.0.0.1:8181
set ANTHROPIC_API_KEY=dummy
set ENABLE_TOOL_SEARCH=false
claude
```

---

## What works

| Feature | How it works |
|---|---|
| `Read` `Write` `Edit` `Bash` | the relay's **native** tools (`read`/`write`/`edit`/`bash`) |
| `Agent` (subagents, parallel), `Monitor`, `Task*`, `TodoWrite`, MCP tools | the `<tool_call>` text protocol |
| `WebSearch` | the **proxy itself** searches DuckDuckGo |
| `WebFetch` | the **proxy itself** opens the page |
| `fetch_image` | the **proxy itself** fetches the image |
| `/v1/messages/count_tokens` | local estimate (the relay returns 404) |
| `/v1/models` | available |
| Streaming | SSE + a **ping every 3 seconds** (no dead air, no timeout) |

Verified by running real Claude Code through the proxy: four `Agent` subagents
launched in parallel in one message, each ran its own live web search, each
wrote a separate standalone HTML file. All four files landed on disk, all four
well-formed and different.

---

## Troubleshooting

**`UPSTREAM_API_KEY is not set`**
Set it (see [Getting an API key](#getting-an-api-key)). On Windows remember
`setx` only applies to **new** terminals.

**`ccproxy is not answering on http://127.0.0.1:8181`**
The proxy isn't running, or it's on another port. Start it with `start.sh` /
`start.bat` and leave that window open.

**Claude Code says a tool doesn't exist (Agent, WebSearch, …)**
Check the model isn't talking about the relay's own default tools
(`read_tabular`, `system_todo_write`, …). Those are not this session's tools.
Restart the proxy so the tool preamble is rebuilt, and start a **fresh** Claude
Code session — a long contaminated history can keep the model confused.

**Getting `Upstream 524` timeouts**
The payload is too big. In `config.json` lower `max_history_chars` (e.g.
`220000` → `120000`) and set `max_tool_result_chars` to `2000`.

**Getting `Upstream 400`**
The proxy already retries with a slim payload (system as a plain string, no
`cache_control`). If it still fails, check `ccproxy_log.txt`.

**A tool call is being dropped**
Search `ccproxy_log.txt` for `DROP tool_call` or `BAD JSON tool_call`. The JSON
on that line is the case to add to the repair.

**Port 8181 is taken**
Change `listen_port` in `config.json`, then set `PROXY=http://127.0.0.1:<port>`
before running `run-claude.sh` / `run-claude.bat`.

**Where are the logs?**
`ccproxy_log.txt` — the live log. It rotates at 2 MB into `ccproxy_log.txt.1`.

---

## Configuration and token cost

Everything lives under `features` in `config.json`:

```jsonc
"max_history_chars": 220000,   // history budget, ~55k tokens. THE big lever.
"max_tool_result_chars": 4000, // how much of a large bash/file output to forward
"compact_tools": true,         // false = full tool descriptions (many more tokens)
"upstream_retries": 2,         // every retry re-sends the whole payload = tokens!
"usage_baseline_tokens": 0,    // set to 10380 to hide this relay's phantom tokens
"dump_requests": false,        // true = save every request to debug_dump/ (uses disk)
```

**The biggest lever is `max_history_chars`.** Claude Code sends the entire
session on every request. Going from `220000` (~55k tokens) to `120000`
(~30k tokens) roughly halves the cost — at the price of the model remembering
less of the earlier conversation.

`dump_requests: true` writes every request to `debug_dump/`. It is very useful
while chasing a bug and it **grows to hundreds of MB fast** — turn it back off
afterwards.

---

## Files

| File | Purpose |
|---|---|
| `ccproxy.py` | the proxy — **this is the one you run** |
| `dashboard.py` | the dashboard served at `/` (imported by ccproxy) |
| `config.json` | settings; the API key can go here or in `UPSTREAM_API_KEY` |
| `requirements.txt` | flask + requests |
| `start.sh` / `start.bat` | start the proxy (macOS/Linux · Windows) |
| `run-claude.sh` / `run-claude.bat` | start Claude Code against the proxy |
| `run_tests.sh` / `run-tests.bat` | run the offline test suite |
| `test_offline.py` | the test suite, with its own mock upstream |
| `names_probe.py` | probe that finds which tool names a relay implements natively |
| `agent_proxy.py` | **old version — kept for reference only, use `ccproxy.py`** |
| `ccproxy_log.txt` | the live log (created at runtime) |

---

## License

**PolyForm Noncommercial License 1.0.0** — the full text is in [LICENSE](LICENSE).

**Free to use for:** personal use, hobby projects, study, research, experiment,
teaching, and by charitable, educational, public research, public safety/health,
environmental and government organizations.

**Not permitted without a separate written commercial license:**

* reselling, sublicensing or rebranding this software, or a modified copy of it
* running it as a hosted or paid service (SaaS, paid API, managed deployment)
* embedding it in a commercial product
* using it internally at a for-profit company in support of revenue-generating work
* monetising it with ads or subscriptions

Anyone who receives a copy from you must also receive the license terms and the
`Required Notice:` line — see the [Notices](LICENSE#notices) section.

For a **commercial license**, open an issue or contact
[@abdurrehmandaudi](https://github.com/abdurrehmandaudi).

This project is **source-available, not open source**. The source is public on
purpose: so you can read it, audit it, and check for yourself that a proxy
sitting between you and your API key isn't doing anything hidden.

---

## Notes

* Everything is local. The proxy binds `127.0.0.1`; your relay key never leaves
  your machine except in requests to the relay you configured.
* `agent_proxy.py` is the earlier, simpler proxy. It works for
  `Read`/`Write`/`Edit`/`Bash` but drops many other tool calls and cannot run
  web search. `ccproxy.py` replaces it.
* The model name in `ANTHROPIC_MODEL` is passed through to the relay as-is. Set
  it to whatever model string your relay expects.
