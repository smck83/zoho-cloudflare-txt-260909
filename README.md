# Inconsistent TXT RRset for `zoho.com` from Cloudflare's public resolver

`1.1.1.1` intermittently returns **19 of the 25 TXT records** `zoho.com`
publishes. The SPF record is among the six omitted, so a receiver using that
resolver sees **no SPF policy** for the domain.

The same query to `8.8.8.8` and `9.9.9.9`, and to all eight of the domain's
authoritative servers, returns the complete set every time.

**Live, continuously sampling:** <https://zoho-cloudflare-prod.mck.la>

That page samples every 60 seconds from a fixed vantage point and shows the
distribution rather than a single query, because the behaviour alternates.
`/api/records` on the same host does a live diff of the two answers.
`/api/summary` returns everything as JSON.

This repository is the method and the reasoning. It is not a claim about the
cause, which is not visible from outside.

## Reproduce

```
pip install dnspython
python probe.py
```

Every query is **TCP**, so UDP buffer size and truncation are not in play.
Records are sorted and hashed, so answers are compared by content rather than
by count: a resolver returning the same number of different records shows as a
distinct variant rather than as agreement.

`probe.py` prints `id.server` for each resolver, so runs from different regions
can be compared.

## What is observed

Ten TCP samples per resolver, from Sydney, Australia:

| resolver | records | RDATA | digest | SPF | seen |
| --- | --- | --- | --- | --- | --- |
| **Cloudflare** | **19** | **964 B** | `23f4ad6b903f` | **no** | **9** |
| Cloudflare | 25 | 1601 B | `16870b05d8ef` | yes | 1 |
| Google | 25 | 1601 B | `16870b05d8ef` | yes | 10 |
| Quad9 | 25 | 1601 B | `16870b05d8ef` | yes | 10 |

Cloudflare served an incomplete answer in **9 of 10** samples. Google and Quad9
served the identical complete answer in all 20 between them.

An earlier 20-sample run from a different host on the same network gave 15 of
20. The live page carries the current figure.

### More than one node, and one node giving both answers

From `id.server` (CHAOS TXT):

| node | samples | missing SPF |
| --- | --- | --- |
| syd01 | 4 | 4 |
| syd06 | 1 | 1 |
| syd07 | 3 | **2** |
| syd08 | 3 | 3 |

Four nodes have shown the behaviour. **`syd07` served both a complete and an
incomplete answer**, which is the most specific thing here: it is not one bad
machine, and it is not a single stale cache entry that will simply expire.

### The six records that go missing

```
_9xdko5m9wh9tx7q8vz3vs0eo2y6l239
 _wcrm20bvcnsi6903akx0tvwk6knbzi8
v=spf1 include:spf.zoho.com include:zcsend.net include:spf.zohomail.com include:popspf.zohomail.com -all
postman-domain-verification=034222fc…   (3 records, ~135 bytes each)
```

## What has been ruled out

**Response size.** `zoho.com`'s complete RRset is **1601 bytes**, the smallest
of the five domains tested. Every larger one is served consistently:

| domain | records | RDATA | distinct answers across all three resolvers |
| --- | --- | --- | --- |
| **zoho.com** | 25 | **1601 B** | **2** |
| uber.com | 42 | 2693 B | 1 |
| crowdstrike.com | 48 | 2752 B | 1 |
| wiz.io | 41 | 2823 B | 1 |
| wework.com | 58 | **3701 B** | 1 |

`wework.com` is 2.3× the size of the answer that fails and is served
identically every time.

**Delegation.** The NS set at the `.com` registry is identical to the NS set in
the zone. No stale or third-party delegation.

```
ns1.zohocorp.com  ns11/21/31/41.zns-53.com|net  pdns90.ultradns.biz|com|net
parent == child: true
```

**The authoritative servers.** All eight return 25 records including the SPF
record.

**Truncation handling at the authority.** Queried directly with varying EDNS
buffer sizes, they set `TC` correctly rather than dropping records to fit:

| EDNS buffer | TC | records | size |
| --- | --- | --- | --- |
| 512 / 1220 / 1232 / 1400 | yes | 1 | 61 B |
| 4096 | no | 25 | 2176 B |

**Interception on the path.** Cloudflare's DoH endpoint
(`https://cloudflare-dns.com/dns-query`) returns the same 19-record answer from
this vantage point, so the short answer is not produced by something on the
wire. `id.server` answers with a Cloudflare node name.

## Correlation, not a claimed cause

`zoho.com` is the only domain of the five carrying malformed TXT records. Two
entries begin with a space:

```
' 2nb6vfc9zm9t9f941qhzh8c66z5x6lxp'
' _wcrm20bvcnsi6903akx0tvwk6knbzi8'
```

None of the four control domains has any, and none of the five uses
multi-string TXT RRs or empty character-strings, so this is the only structural
difference in the set.

It is offered only as something cheap to test. It does not on its own explain
the behaviour: one of the two space-prefixed records survives in the short
variant while the other does not, so "drops the malformed records" is not the
rule.

## Impact

A receiver resolving via an affected node sees SPF `none` for `zoho.com` and
cannot evaluate SPF for mail from that domain. Because the behaviour
alternates, the same check can pass and fail minutes apart with nothing
changed, which is what makes it hard to attribute to anything.

## Vantage point

All measurements here are from Sydney, Australia. Queries from other regions
have returned the complete RRset, so this may be limited to particular nodes.
Runs from elsewhere are welcome — `probe.py` prints `id.server` so results can
be compared directly.

## For the domain owner

Independent of the above, the two space-prefixed TXT records look like
copy-paste damage and are worth removing.
