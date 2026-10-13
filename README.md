# mailtmp

Disposable email addresses from the command line. No domain, no VPS, no mail
server, no dependencies.

Built on top of the public [mail.tm](https://mail.tm) API. Addresses are real
and receive real mail — which is the whole point, because most "local mail"
tools only catch what your own machine sends.

```bash
mailtmp new           # → k3f9x1m2q@maxxspace.com
mailtmp wait 120      # → 482913   (or an activation link)
```

Paste the address into a signup form, run `wait` in a second terminal, paste
the code back. Done.

## Why

There is no way to run your own mail server without a domain and an inbound
port 25. If you want a real receiving address on demand, the domain has to
belong to somebody. So either you have the infrastructure, or you use a
service that already does. This is a small client for the second case.

If you want the first case — self-hosted mail on your own domain — this tool
is not what you want.

## Install

Requires Python 3.6+ and nothing else.

```bash
git clone <this-repo>
install -m 755 mailtmp ~/.local/bin/
install -m 755 mailtmp-tui ~/.local/bin/
```

Both files are needed: `mailtmp-tui` is the client, `mailtmp` is its
backend and it loads the client by path. Make sure `~/.local/bin` is on
your `PATH`.

## The TUI client

```bash
mailtmp            # open the client (same as `mailtmp tui`)
mailtmp tui new    # create an address first, then open it
```

Typing `mailtmp` with no arguments opens the client — the mailprogram of
this tool. When stdout is not a terminal (a pipe, a script, CI), it prints
the usage text instead of hanging in curses.

Three panes, like a normal mail client:

```
┌──────────┐┌──────────────────┐┌───────────────────────────┐
│ ПОЧТА    ││ Входящие — 5     ││ От:    noreply@github.com│
│ Входящие ││  ★●from  10-13   ││ Тема:  Your code         │
│ ★        ││     subject      ││                           │
│ ОТПРАВКА ││  ●from2  10-13   ││ КОД: 731294               │
│ Черновик ││     subject      ││                           │
└──────────┘└──────────────────┘└───────────────────────────┘
```

| Key | |
|---|---|
| `↑ ↓ j k` | select message |
| `Enter` | open in the reading pane |
| `u` | back to the list |
| `d` / `s` | delete / star |
| `c` | copy the code to the clipboard |
| `n` | wait for a new message, with a countdown |
| `N` / `y` | new address / copy the address |
| `r` / `A` | refresh / auto-refresh |
| `/` / `c` | search / clear search |
| `Tab` / `1` `2` `3` | switch pane |
| `?` / `q` | help / quit |

Stars and read markers are kept in `~/.local/state/mailtmp-tui.json`,
separate from `state.json` — the core rewrites that file wholesale on
`mailtmp new`, so anything stored there would be wiped.

The client does not reimplement message parsing: it imports this script
as a module and uses `extract()` as is.

The current address is always visible in the sidebar — not only in the
corner of the title bar, where a freshly created one is easy to miss — and
`y` copies it to the clipboard, which is what you actually want when
pasting it into a signup form.

## Commands

| Command | Does |
|---|---|
| `mailtmp` | open the TUI client |
| `mailtmp tui [new]` | the same, explicitly |
| `mailtmp new` | Create a new address and remember it |
| `mailtmp addr` | Print the current address |
| `mailtmp domains` | List domains available right now |
| `mailtmp inbox` | List received messages |
| `mailtmp read N` | Print message `N` (first 8 chars of its id) |
| `mailtmp wait [SEC]` | Wait for a *new* message, print code or link |
| `mailtmp reset` | Forget the current address and password |
| `mailtmp help` | Usage |

`wait` only reports messages that arrived after it started. Anything already
sitting in the inbox is ignored.

### Exit codes

```
0   success
1   error (network, HTTP failure, no current address)
2   no message before the timeout, or invoked with no arguments
```

## Code and link extraction

`wait` prints a verification code if it finds one, otherwise an activation
link.

Codes are matched in two passes, and the **body is searched before the
subject** — subjects usually carry a ticket number, not the code.

1. **Labelled** — a marker word (`code`, `код`, `pin`, `otp`, `verification`,
   `verify`, `passcode`, `пароль`, `token`) followed within 40 characters by a
   candidate token. The token is accepted if it is 4–8 digits, or 4–10
   characters containing both digits and letters — which is how `K3M9XP`
   style codes get caught.
2. **Any digits** — 4–8 consecutive digits, after separators *inside* a
   number are removed, so `48 29 13` reads as `482913` and `1234-5678` as
   `12345678`.

Links are matched against the raw HTML and the plain-text parts, and only
after both code passes come up empty.

Known limitation: an ordinary message containing unrelated numbers
(`Order 99201 shipped`) will yield those numbers as the "code". This is a
deliberate trade-off for a zero-dependency single file.

Two more documented non-behaviours: a bare alphanumeric token in a subject
with no marker word is not treated as a code, and runs longer than 8 digits
are skipped.

The poll loop sleeps at most 4 seconds, and never past the deadline, so
`wait` returns close to when it was told to. Measured on the same account:
`mailtmp wait 6` took 8.9 s before the fix and 6.3 s after — the 0.3 s
remainder is one API round trip. The inbox is also polled immediately on
start rather than after a first 4-second pause.

## Where state lives

```
~/.local/state/mailtmp/state.json    mode 600
```

Contains the address, its password and the bearer token. The password is
generated with `random.SystemRandom`.

## Limits

Inherited from the service, not from this client:

- Mail is retained **7 days**.
- API rate limit is **8 requests/second**.
- Receiving only — these addresses cannot send.
- The domain is shared, and signup forms increasingly block disposable
  domains. Small sites, forums and game registrations usually still work.

## Security

- One-shot addresses. Do not tie anything valuable to them — no payments, no
  recovery codes for accounts that matter.
- Do not commit `state.json`.
- Do not put `state.json` in any directory that syncs to a server.

## AI assistance disclosure

**This code was written by an AI coding assistant.**

The implementation was produced in a single session by
[opencode](https://opencode.ai) (a terminal coding agent driving a language
model), working from a requirement specification supplied by the repository
author. The author designed the tool, directed the implementation, and
reviewed and tested the result before publishing.

Four bugs were found during development, and the sequence matters more than
the count:

| # | Bug | How it surfaced |
|---|---|---|
| 1 | URLs lost inside HTML attributes | caught immediately, by unit test |
| 2 | Message subject dropped from the code-search blob | caught immediately, regression of fix 1 |
| 3 | Wrong assumption about the API response shape | **only on a live email** |
| 4 | `read` received the whole argv list instead of its first element | **only on a live run** |

Bugs 3 and 4 are the instructive ones. The unit tests fed the code the
author's own idea of the API shape, so they could not catch a wrong idea
about that shape. And `read` was only ever called directly in tests, never
through argument parsing — so a function that had never worked looked fine.

Both were found only after the first real email arrived.

## Tests

`tests/test_extract.py` runs without network access and covers the extraction
logic, including all three response shapes the API returns:

```bash
python3 tests/test_extract.py
```

33 tests. `TestApiShapes` encodes the real responses verbatim — including the
one that caused bug 3.

`tests/test_tui_keys.py` covers the client's navigation, search, stars and
layout — 22 tests, no terminal involved:

```bash
python3 tests/test_tui_keys.py
```

The client itself is checked visually: `tests/fake_tui.py` substitutes canned
messages for the network, and `tools/tui_probe.py` runs it in a
pseudo-terminal and prints a text frame. That last one is a convenience, not a
regression test — key delivery through a pty depends on redraw timing, so the
behavioural checks live in the unit tests instead.

Live mail delivery is **not** covered by automated tests — sending SMTP mail
from a test environment is not reliably possible. Verify it once by hand.

Sending is not supported at all: `POST /messages` answers `405 Method Not
Allowed`. mail.tm is receive-only, so the client has no compose form.

## License

MIT. See [LICENSE](LICENSE).