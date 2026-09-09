# Report: Cloudflare (1.1.1.1) — RESOLVED

**Outcome: not a Cloudflare fault.** Max Worsley of the Cloudflare team
identified the cause within a day: four of zoho.com's own nameservers ignore
the EDNS buffer size and never set TC, so 1.1.1.1 receives an oversized
datagram and truncates it. See [zoho.md](zoho.md), which is the report that
now matters, and the repository README for the confirmed mechanism.

One correction to the reply for the record: it named IPv6 specifically, and
independent testing shows the same behaviour over IPv4. The fix is not
protocol-specific.

Kept below as filed, because the reasoning and the eliminations are the
reason it got a useful answer — including the one elimination that was
wrong. The original testing checked truncation behaviour on a single
nameserver out of eight, picked a compliant one, and ruled out the actual
cause on that basis.

---

# As filed

Channel: <https://community.cloudflare.com/> under 1.1.1.1, or a support ticket.
Cloudflare does not triage resolver behaviour through GitHub, so this repository
is the thing to link to rather than the place to raise it.

Formatted so it stays readable pasted into a plain textarea. Nothing below
depends on Markdown rendering.

---

**Subject:** 1.1.1.1 Sydney nodes return an incomplete TXT RRset for zoho.com

Four Cloudflare nodes in Sydney intermittently return 19 of the 25 TXT records
zoho.com publishes. Six records are dropped, including the domain's SPF record,
so a client using those nodes sees no SPF policy for zoho.com and cannot
evaluate SPF for mail from it.

Some Cloudflare nodes are unaffected, which is what makes this specific rather
than a general "resolver returns wrong answer". It splits by node, not by
region, and at least two nodes have served both answers.

    node     location         complete   incomplete
    syd01    Sydney           0          4
    syd06    Sydney           0          1
    syd08    Sydney           0          3
    syd07    Sydney           1          2     <- both answers
    iad07    Washington DC    1          11    <- both answers
    dfw13    Dallas           8          0
    sjc07    San Jose         8          0

Sydney figures are from a fixed host there. The rest are from GitHub Actions
runners, so those logs are public and this report does not depend on my network
being believed.

Three things in that table:

1. syd07 and iad07 each returned a complete and an incomplete RRset at different
   times. So this is not one bad machine, and not a single cache entry that will
   expire on its own.

2. dfw13 and sjc07 have never returned anything but the full 25 records, so the
   difference is between nodes rather than between regions or routes.

3. iad07 and the Sydney nodes have nothing in common but the resolver, which
   rules out anything local to my network or my part of the world.

The two answers:

    19 records,  964 bytes RDATA, sha256 23f4ad6b903f, no SPF
    25 records, 1601 bytes RDATA, sha256 16870b05d8ef, SPF present

8.8.8.8 and 9.9.9.9 return the 25-record answer 100% of the time, from every
location tested.

Reproduce (every query is TCP, so truncation and EDNS buffer size are not in
play):

    pip install dnspython
    python probe.py

Source: https://github.com/smck83/zoho-cloudflare-txt-260909

Ruled out already, with method and figures in the repository:

- Response size. zoho.com's complete RRset is 1601 bytes, the SMALLEST of five
  domains tested. wework.com at 3701 bytes and 58 records is served identically
  every time, as are uber.com, crowdstrike.com and wiz.io.
- Delegation. Parent and child NS sets are identical.
- The authoritative servers. All eight return 25 records.
- Truncation at the authority. Queried directly with EDNS buffers of 512, 1220,
  1232 and 1400, they set TC correctly rather than dropping records to fit; at
  4096 they return all 25 in 2176 bytes.
- Interception on the path. cloudflare-dns.com DoH returns the same 19-record
  answer from Sydney, so the short answer is not produced on the wire, and the
  Actions runs reproduce it from an unrelated network.

One observation offered only as something cheap to test, not as a claimed cause:
zoho.com is the only domain of the five publishing malformed TXT records. Two
begin with a space. It does not by itself explain the behaviour, because one of
those two survives in the short answer and the other does not.

Links:

- Repository, method and eliminations:
  https://github.com/smck83/zoho-cloudflare-txt-260909
- Live sampling from Sydney, updated continuously:
  https://zoho-cloudflare-prod.mck.la
- Scheduled runs from GitHub Actions, twelve rounds an hour, committed:
  https://github.com/smck83/zoho-cloudflare-txt-260909/tree/main/results

Happy to run anything specific from the Sydney vantage point, or to add nodes
to the comparison.
