# Report: Zoho

Channel: a Zoho support ticket, and worth also sending to whoever runs the
zns-53.com nameservers, since that is where the fix has to happen.

Formatted so it stays readable pasted into a plain textarea.

---

**Subject:** Four zoho.com nameservers ignore EDNS buffer size, causing SPF
record loss

Four of the eight nameservers for zoho.com return a 2176-byte UDP response
regardless of the EDNS payload size the requester advertised, and never set the
TC flag:

    ns11.zns-53.com
    ns21.zns-53.net
    ns31.zns-53.com
    ns41.zns-53.net

RFC 6891 section 6.2.5 requires a responder whose answer will not fit the
requester's advertised payload size to truncate the response and set TC, so the
requester knows to retry over TCP. These four never do.

The other four (ns1.zohocorp.com, pdns90.ultradns.biz, .com and .net) behave
correctly, returning a 61-byte response with TC=1.

## Why this matters

Cloudflare's public resolver advertises a 1232-byte buffer. When it queries one
of the four, it receives an oversized datagram and truncates it internally,
which drops the last six records of the TXT RRset. One of those six is your SPF
record:

    v=spf1 include:spf.zoho.com include:zcsend.net include:spf.zohomail.com include:popspf.zohomail.com -all

A receiving mail server resolving through that path sees SPF "none" for
zoho.com and cannot evaluate SPF for your mail.

Because a resolver picks a different nameserver per query, and four of your
eight are affected, this comes and goes. The same check passes and fails minutes
apart, which makes it very difficult for anyone downstream to attribute to a
cause. We spent a day believing it was a resolver fault before Cloudflare
identified the nameservers.

## Why some resolvers are fine and others are not

This is worth being clear about, because it is the reason the problem looks
random and the reason it will get worse rather than better.

Your four nameservers send the same 2176-byte reply no matter what the asker
said it could accept. Whether that causes a problem depends entirely on one
number in the query:

    resolver advertises 1232 bytes  ->  2176-byte reply is oversized
    resolver advertises >= 2176     ->  2176-byte reply fits, nothing goes wrong

Cloudflare advertises 1232. That is not a low or unusual figure: it is the value
recommended by DNS Flag Day 2020 and widely adopted since, chosen so replies do
not get fragmented in transit. Google and Quad9 evidently advertise enough to
fit 2176, so for them the same broken reply is just a normal answer.

The distinction matters. These four are not working correctly and failing only
against Cloudflare. They are non-compliant everywhere, and get away with it
wherever the asker happened to request a large buffer. As more resolvers adopt
the smaller, current recommendation, the more often it will bite.

Two further points against waiting it out:

**A larger buffer is not a fix, only a different failure.** From a GitHub
Actions runner the 2176-byte reply does not arrive at all, because it is too
large for that path. A resolver there gets nothing rather than a truncated
something. Setting TC is what prevents both outcomes.

**Every one of these resolvers truncates correctly toward its own clients.**
Asked for a 512-byte limit, all three return TC=1 and a 37-byte reply. What is
being asked of ns11/21/31/41 is what every other party in the chain, including
your own other four nameservers, already does.

## Verify it yourself

    pip install dnspython
    python probe.py --edns zoho.com

from https://github.com/smck83/zoho-cloudflare-txt-260909

Or directly, with dig:

    dig +bufsize=1232 +ignore TXT zoho.com @ns11.zns-53.com
    dig +bufsize=1232 +ignore TXT zoho.com @pdns90.ultradns.com

The first returns the full 2176-byte answer with TC unset. The second returns
61 bytes with TC set, which is the correct behaviour.

The four do not truncate at any advertised size. Asked with no EDNS at all,
where RFC 1035 caps UDP at 512 bytes, ns11.zns-53.com still returns 2165 bytes.

## The fix

ns11, ns21, ns31 and ns41.zns-53.com|net need to set TC when a response exceeds
the requester's advertised EDNS payload size, over both IPv4 and IPv6. This is
usually a configuration option in the authoritative server software rather than
a code change.

Reducing the zoho.com TXT RRset below about 1232 bytes would also avoid the
symptom today, but it treats the symptom. The nameservers would stay
non-compliant for any other large RRset on any zone they serve, now or later,
and the failure would reappear the next time a record set grew.

## Separately: two malformed TXT records

Unrelated to the above, two of your TXT records begin with a space character:

    " 2nb6vfc9zm9t9f941qhzh8c66z5x6lxp"
    " _wcrm20bvcnsi6903akx0tvwk6knbzi8"

These look like copy-paste damage from whatever verification flow created them.
A leading space is legal but almost certainly not intended, and any verification
service matching on an exact string will not match these. Removing them also
takes a little weight out of the RRset.

## Credit

The nameservers and the mechanism were identified by Max, a Cloudflare
engineer, from a report we raised on their community forum.
