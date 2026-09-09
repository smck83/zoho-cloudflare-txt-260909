# Four of zoho.com's nameservers ignore the EDNS buffer size

**Resolved. The cause is in `zoho.com`'s own DNS, not in Cloudflare's resolver.**

Four of the eight nameservers for `zoho.com` return a 2176-byte UDP response
regardless of the EDNS payload size the requester advertised, and never set the
`TC` flag. RFC 6891 §6.2.5 requires a responder whose answer will not fit the
advertised buffer to truncate and set `TC`, so the requester knows to retry over
TCP.

`1.1.1.1` advertises 1232 bytes. When it happens to query one of the four, it
receives an oversized datagram and truncates it internally, which drops the last
six records of the RRset — including `zoho.com`'s SPF record. A client then sees
**no SPF policy** for the domain.

Which nameserver a resolver picks varies per query, which is why the answer
alternated and why this was so hard to pin down.

## Reproduce

```
pip install dnspython
python probe.py --edns zoho.com
```

```
nameserver                 proto  TC     bytes   verdict
ns1.zohocorp.com           IPv4   True      61   correct: TC=1
ns11.zns-53.com            IPv4   False   2176   *** OVERSIZED, NO TC ***
ns11.zns-53.com            IPv6   False   2176   *** OVERSIZED, NO TC ***
ns21.zns-53.net            IPv4   False   2176   *** OVERSIZED, NO TC ***
ns21.zns-53.net            IPv6   False   2176   *** OVERSIZED, NO TC ***
ns31.zns-53.com            IPv4   False   2176   *** OVERSIZED, NO TC ***
ns31.zns-53.com            IPv6   False   2176   *** OVERSIZED, NO TC ***
ns41.zns-53.net            IPv4   False   2176   *** OVERSIZED, NO TC ***
ns41.zns-53.net            IPv6   False   2176   *** OVERSIZED, NO TC ***
pdns90.ultradns.biz        IPv4   True      61   correct: TC=1
pdns90.ultradns.com        IPv4   True      61   correct: TC=1
pdns90.ultradns.net        IPv4   True      61   correct: TC=1
```

`python probe.py` still runs the original comparison across resolvers.

## The four never truncate, at any buffer size

`ns11.zns-53.com`, asked the same question with different advertised buffers:

| EDNS buffer | TC | response |
| --- | --- | --- |
| 512 | no | 2176 B |
| 1220 | no | 2176 B |
| 1232 | no | 2176 B |
| 1400 | no | 2176 B |
| 2000 | no | 2176 B |
| 4096 | no | 2176 B |
| none (classic 512) | no | **2165 B** |

The last row is the clearest: with no EDNS at all, the limit is 512 bytes by
RFC 1035, and it still returns 2165 over UDP. These servers do not truncate.

The four compliant servers return 61 bytes with `TC=1` in every one of those
cases.

## Why it looked like a resolver problem

Everything observed from outside was consistent with a broken cache:

- The same resolver returned two different answers minutes apart.
- Some Cloudflare nodes served the short answer and others the full one.
- One node served both at different times.
- Google and Quad9 were always correct.

All of that follows from nameserver selection. A resolver picks one of the eight
per query; four are broken, four are not. Google and Quad9 advertise a larger
buffer, so the oversized response fits and nothing is dropped.

## The mistake in this repository's earlier testing

An earlier version of this document listed "truncation handling at the
authority" as **ruled out**, on the strength of this:

| EDNS buffer | TC | records |
| --- | --- | --- |
| 512 / 1220 / 1232 / 1400 | yes | 1 |
| 4096 | no | 25 |

That test queried **one nameserver out of eight** — `pdns90.ultradns.com` — and
happened to pick a compliant one. The conclusion "the authoritative servers set
TC correctly" was drawn from a sample of one and stated about all eight.

That single unexamined choice is why the actual cause was ruled out on day one
and the investigation pointed at Cloudflare instead. Everything else in the
original write-up was carefully checked against controls; this one step was not,
and it was the step that mattered.

`probe.py --edns` now checks every nameserver, over both protocols, which is
what the original test should have done.

## What narrows it further

**The fault line is the platform boundary.** Over CHAOS `version.bind`, the four
compliant nameservers all answer `UltraDNS Nameserver` — including
`ns1.zohocorp.com`, despite the name. The four that misbehave refuse every
identification query, which is ordinary hardening rather than a fault, but it
places the boundary exactly between Zoho's own `zns-53` infrastructure and the
UltraDNS platform. More likely one shared setting or build than four separately
broken hosts.

**TCP/53 already works on all eight.** A server setting `TC` is directing the
client to retry over TCP, so it would matter a great deal if these four did not
answer there. They do — all eight return the complete 25-record RRset over TCP.
The retry destination is already correct; only the signal telling clients to use
it is missing, which makes enabling truncation both safe and sufficient.

Over TCP the answer measures 2165 bytes against 2176 over UDP; the difference is
the EDNS `OPT` pseudo-record the UDP queries carry.

## Credit

Diagnosed by Max, a Cloudflare engineer, who identified the four nameservers
and the mechanism from the community thread. His reply named IPv6 specifically;
independent testing shows the same behaviour over IPv4, so the fix is not
protocol-specific.

## The fix

For Zoho, these four must set `TC` when a response exceeds the requester's
advertised EDNS payload size, over **both IPv4 and IPv6**:

```
ns11.zns-53.com
ns21.zns-53.net
ns31.zns-53.com
ns41.zns-53.net
```

> Two notes for anyone reading the [Cloudflare thread][thread] alongside this.
> It lists all four as `.com`; `ns21.zns-53.com` and `ns41.zns-53.com` are
> NXDOMAIN, and the real hostnames are the `.net` ones above. It also gives the
> oversized response as 2484 bytes where every measurement here is 2176,
> including with DNSSEC-OK set. Neither changes the mechanism or the fix.

[thread]: https://community.cloudflare.com/t/19-rows-of-txt-for-zoho-dot-com-instead-of-25/957207 Until then, any resolver advertising a buffer smaller than 2176 bytes
may serve an incomplete RRset for `zoho.com`, and dropping the SPF record from
it is a live deliverability problem.

Trimming the TXT RRset below ~1232 bytes would also avoid it, but that treats
the symptom. Two of the 25 records are malformed and worth removing anyway —
see below — though that alone will not bring it under the limit.

## Also worth fixing: two malformed TXT records

Independent of the above, two of `zoho.com`'s TXT records begin with a space:

```
' 2nb6vfc9zm9t9f941qhzh8c66z5x6lxp'
' _wcrm20bvcnsi6903akx0tvwk6knbzi8'
```

Almost certainly copy-paste damage. Any verification service matching an exact
string will not match these. None of the four control domains tested
(`wework.com`, `crowdstrike.com`, `uber.com`, `wiz.io`) has anything similar.

## Impact while it stands

A receiving mail server resolving via an affected path sees SPF `none` for
`zoho.com` and cannot evaluate SPF for mail from that domain. Because it depends
on which nameserver was picked, the same check passes and fails minutes apart,
which makes it very hard for anyone downstream to attribute.

## Live monitoring

<https://zoho-cloudflare-prod.mck.la> samples continuously and will show the
behaviour stopping once the nameservers are fixed.

Scheduled runs from GitHub Actions are committed to [`results/`](results/),
giving a public record from a second location.

## Reports

- [reports/zoho.md](reports/zoho.md) — the actionable one
- [reports/cloudflare.md](reports/cloudflare.md) — kept as filed, with the
  outcome appended
