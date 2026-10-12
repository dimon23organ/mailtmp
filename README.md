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
```

Make sure `~/.local/bin` is on your `PATH`.

## Commands

| Command | Does |
|---|---|
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

Codes are matched in two passes:

1. **Labelled** — `code`, `код`, `pin`, `otp`, `verification`, `verify`,
   `подтверж`, followed within 30 characters by 4–8 digits.
2. **Any** — the first run of 4–8 digits anywhere in the message.

Links are matched against the raw HTML and the plain-text parts.

Known limitation: an ordinary message containing unrelated numbers
(`Order 99201 shipped`) will yield those numbers as the "code". This is a
deliberate trade-off for a zero-dependency single file.

Known roughness: the poll loop sleeps 4 seconds, so `wait` can overrun its
timeout by up to 4 seconds. Measured: `mailtmp wait 6` returned after 9
seconds with exit code 2.

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

The extraction logic in particular went through two bug-fix rounds during
that session — one for URLs lost inside HTML attributes, one for a
regression that dropped the message subject — which is why the test cases
below are in the repository.

## Tests

`tests/test_extract.py` runs without network access and covers the extraction
logic:

```bash
python3 tests/test_extract.py
```

Live mail delivery is **not** covered by automated tests — sending SMTP mail
from a test environment is not reliably possible. Verify it once by hand.

## License

MIT. See [LICENSE](LICENSE).