# Report: Zoho

Channel: a Zoho support ticket. There is no GitHub presence for their DNS, and
this needs to reach whoever owns the zoho.com zone.

Two unrelated issues. The second is small and entirely theirs to fix, so it is
worth raising even if they take no interest in the first.

Formatted so it stays readable pasted into a plain textarea.

---

**Subject:** zoho.com SPF record not visible to some Cloudflare 1.1.1.1 nodes,
and two malformed TXT records

I have been measuring TXT records across public resolvers and found two things
affecting zoho.com. They are independent of each other.

## 1. A major resolver cannot see your SPF record from some of its nodes

zoho.com publishes 25 TXT records. Cloudflare's public resolver (1.1.1.1)
intermittently returns only 19 of them from several of its nodes, and the six
it drops include your SPF record:

    v=spf1 include:spf.zoho.com include:zcsend.net include:spf.zohomail.com include:popspf.zohomail.com -all

The practical effect is that a receiving mail server using 1.1.1.1, if it lands
on one of the affected nodes, sees SPF "none" for zoho.com and cannot evaluate SPF for your mail.
Because it is intermittent, the same check can pass and fail minutes apart,
which makes it hard for anyone to attribute to a cause.

Measured from Sydney over about an hour, Cloudflare returned the incomplete
answer in 9 of 10 samples. It is not confined to one region: a node in
Washington DC returned the incomplete answer in 11 of 12 samples in separate
testing, while nodes in Dallas and San Jose returned the complete set every
time. So it affects some Cloudflare nodes and not others, in more than one
part of the world.

Google (8.8.8.8) and Quad9 (9.9.9.9) returned the complete set every time from
every location tested, as did all eight of your authoritative servers.

**Your zone is not at fault here, as far as I can measure.** Parent and child NS
sets match, all eight authoritative servers return the full 25 records, and they
set the TC flag correctly when the answer does not fit a UDP buffer. I have
reported it to Cloudflare separately.

I am raising it with you because it affects deliverability for mail from
zoho.com in that region, and because you are better placed than I am to press
Cloudflare on it.

Full method, measurements and a reproduction script:
https://github.com/smck83/zoho-cloudflare-txt-260909

## 2. Two malformed TXT records on zoho.com

Separately, and regardless of the above, two of your TXT records begin with a
space character:

    " 2nb6vfc9zm9t9f941qhzh8c66z5x6lxp"
    " _wcrm20bvcnsi6903akx0tvwk6knbzi8"

These look like copy-paste damage from whatever verification flow created them.
A leading space is legal in a TXT record but almost certainly not what was
intended, and any verification service matching on an exact string will not
match these.

For context, I compared zoho.com against four other domains with larger TXT
record sets (wework.com, crowdstrike.com, uber.com, wiz.io). None of them has a
record with leading or trailing whitespace; zoho.com is the only one. I am not
claiming this causes the resolver issue above, and I do not think it does, but
it is worth cleaning up on its own merits.
