# Bamban

Personal, **human-in-the-loop** tooling for your own BAM (bsb.bmi.ir) account.

This repo is being built in phases. **Phase 1 (here) is a read-only capture
tool.** It does not log in for you, does not submit anything, and does not
bypass any login, OTP, or dynamic password. You drive a real browser by hand;
the tool only records the traffic so we can learn which endpoints carry your
balance and transactions — then later build the bot on top of the genuine
browser session.

## What it captures

Each run writes to `artifacts/<timestamp>/`:

| file | contents | share? |
|------|----------|--------|
| `endpoint_map.json` | redacted structure: methods, URLs (values masked), JSON field names + types | ✅ **safe to share** |
| `raw.har` | full traffic incl. cookies, tokens, real balances | ❌ secret, git-ignored |
| `trace.zip` | replayable Playwright trace | ❌ may contain secrets |
| `storage_state.json` | your logged-in session (for later reuse by the bot) | ❌ secret, git-ignored |

The redactor keeps **field names** (they tell us where the balance lives) but
replaces every **value** with its type. Only `endpoint_map.json` should ever
leave your machine.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Run (on your own machine/server)

```bash
python capture.py
```

Then, in the browser window that opens:

1. Log in **by hand** (type your own password and dynamic/OTP yourself).
2. Open your account so the **balance** loads.
3. Open the **recent transactions** list so it loads.
4. *(Optional)* open the transfer page — but **do not submit anything**.

Come back to the terminal and press **ENTER**. The tool stops, saves the
artifacts, and prints the JSON endpoints it found (with their field names) so
we can spot which one is the balance and which is the transactions list.

Send me only `endpoint_map.json`.

## Configuration

See `config.yaml`. No credentials are needed for this phase. Key settings:

- `bank.base_url` / `bank.login_path` — where to open.
- `browser.headless` — keep `false` (you need to see the page to log in).
- `capture.include_hosts` — which hosts go into the shareable map (default:
  the base host plus anything under `bmi.ir`).

## What's intentionally NOT here

No automated login, no OTP/dynamic-password handling, no transfer, no Telegram.
Those come in later phases and will keep the same rule: **you** enter the
dynamic password for every transfer, by hand, every time.
