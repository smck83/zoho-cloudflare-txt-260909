# Report: Cloudflare (1.1.1.1)

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

Cloudflare nodes elsewhere are unaffected, which is what makes this worth
reporting rather than a general "resolver returns wrong answer".

Affected, observed over roughly an hour from Sydney, Australia:

    node     location   samples   missing SPF
    syd01    Sydney     4         4
    syd06    Sydney     1         1
    syd07    Sydney     3         2      <- served both answers
    syd08    Sydney     3         3
    dfw13    Dallas     8         0      <- unaffected

Two things in that table:

1. syd07 returned both a complete and an incomplete answer at different times,
   so this is not one bad machine, and not a single cache entry that will expire.

2. dfw13 is fine. A GitHub Actions runner got the complete 25-record RRset in 8
   of 8 samples, on all three resolvers, in the same period Sydney was failing.
   That run is public and linked below, so this report does not depend on my
   network being believed.

The two answers:

    19 records,  964 bytes RDATA, sha256 23f4ad6b903f, no SPF
    25 records, 1601 bytes RDATA, sha256 16870b05d8ef, SPF present

8.8.8.8 and 9.9.9.9 return the 25-record answer 100% of the time from both
locations.

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
  answer from Sydney, so the short answer is not produced on the wire.

One observation offered only as something cheap to test, not as a claimed cause:
zoho.com is the only domain of the five publishing malformed TXT records. Two
begin with a space. It does not by itself explain the behaviour, because one of
those two survives in the short answer and the other does not.

Links:

- Repository, method and eliminations:
  https://github.com/smck83/zoho-cloudflare-txt-260909
- Live sampling from Sydney, updated continuously:
  https://zoho-cloudflare-prod.mck.la
- Scheduled runs from GitHub Actions, committed every two hours:
  https://github.com/smck83/zoho-cloudflare-txt-260909/tree/main/results

Happy to run anything specific from the Sydney vantage point, or to add nodes
to the comparison.
