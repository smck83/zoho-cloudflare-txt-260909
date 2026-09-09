#!/usr/bin/env python3
"""Compare a domain's TXT RRset across recursive resolvers, repeatedly.

A continuously sampling instance of this comparison runs at
https://zoho-cloudflare-prod.mck.la -- this script is the same measurement,
runnable from your own location so the result is not taken on trust.

    pip install dnspython
    python probe.py                     # the default domain set
    python probe.py zoho.com wiz.io     # specific domains
    python probe.py --samples 20 zoho.com

Each sample is a TCP query, so truncation and UDP buffer size are not in play.
Records are sorted and hashed, so two answers are compared by content rather
than by count: a resolver returning the same number of different records would
show as a distinct variant.

Prints one line per resolver per domain listing every distinct variant seen. A
domain whose RRset is served consistently produces exactly one variant per
resolver and the same hash on all of them.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import platform
import socket
import sys
import time
from datetime import datetime, timezone

try:
    import dns.flags
    import dns.message
    import dns.query
    import dns.resolver
    import dns.rdataclass
    import dns.rdatatype
except ImportError:
    sys.exit("needs dnspython:  pip install dnspython")

RESOLVERS = [("1.1.1.1", "Cloudflare"), ("8.8.8.8", "Google"), ("9.9.9.9", "Quad9")]

#: What 1.1.1.1 advertises as its maximum UDP payload. The number matters:
#: a responder that ignores it and sends more is the fault this repository
#: ended up documenting.
EDNS_BUFSIZE = 1232

DEFAULT_DOMAINS = ["zoho.com", "wiz.io", "crowdstrike.com", "uber.com", "wework.com"]


def fingerprint(server: str, domain: str, timeout: float = 12.0):
    """(record count, rdata bytes, short hash, has_spf) for one TCP query."""
    q = dns.message.make_query(domain, "TXT")
    r = dns.query.tcp(q, server, timeout=timeout)
    recs = sorted(
        b"".join(rd.strings).decode("utf-8", "replace")
        for rs in r.answer
        for rd in rs
    )
    rdata = sum(len(x.encode()) for x in recs)
    digest = hashlib.sha256("\x00".join(recs).encode()).hexdigest()[:8]
    has_spf = any(x.lower().startswith("v=spf1") for x in recs)
    return len(recs), rdata, digest, has_spf


def node_id(server: str) -> str:
    """Which node of an anycast resolver answered, where it will say."""
    try:
        q = dns.message.make_query("id.server", dns.rdatatype.TXT, dns.rdataclass.CH)
        r = dns.query.udp(q, server, timeout=5)
        vals = [
            b"".join(rd.strings).decode("utf-8", "replace")
            for rs in r.answer
            for rd in rs
        ]
        return vals[0] if vals else "-"
    except Exception:
        return "-"


def edns_compliance(domain: str, bufsize: int = EDNS_BUFSIZE) -> int:
    """Do a domain's own nameservers respect the EDNS buffer they were given?

    RFC 6891 s6.2.5: a responder whose answer will not fit the requester's
    advertised payload size MUST truncate and set TC, so the requester knows to
    retry over TCP. A responder that instead sends the whole thing leaves the
    requester holding an oversized datagram, and what happens next is up to the
    requester.

    This is the check that would have found the cause of the zoho.com behaviour
    on day one, and the one that was missed: the earlier testing queried a
    single nameserver of eight, happened to pick a compliant one, and concluded
    the whole set was fine.
    """
    print(f"EDNS compliance for {domain}, advertising {bufsize} bytes")
    print("RFC 6891 6.2.5: too big for the advertised buffer MUST mean TC=1")
    print()
    try:
        ns_names = sorted(str(r.target).rstrip(".")
                          for r in dns.resolver.resolve(domain, "NS"))
    except Exception as exc:
        print(f"  could not list nameservers: {exc}")
        return 2

    print(f"{'nameserver':<26} {'proto':<6} {'TC':<6} {'bytes':>6}   verdict")
    offenders = []
    for name in ns_names:
        for rdtype, proto in (("A", "IPv4"), ("AAAA", "IPv6")):
            try:
                addr = dns.resolver.resolve(name, rdtype)[0].address
            except Exception:
                continue
            try:
                q = dns.message.make_query(domain, "TXT", use_edns=0, payload=bufsize)
                r = dns.query.udp(q, addr, timeout=12)
                tc = bool(r.flags & dns.flags.TC)
                size = len(r.to_wire())
            except Exception as exc:
                print(f"{name:<26} {proto:<6} {'-':<6} {'-':>6}   ERROR {type(exc).__name__}")
                continue
            if tc:
                verdict = "correct: TC=1"
            elif size > bufsize:
                verdict = "*** OVERSIZED, NO TC ***"
                offenders.append(f"{name} ({proto})")
            else:
                verdict = "fits, no TC needed"
            print(f"{name:<26} {proto:<6} {str(tc):<6} {size:>6}   {verdict}")

    print()
    if offenders:
        print("Nameservers ignoring the advertised buffer:")
        for o in offenders:
            print(f"  - {o}")
        print()
        print("A recursive resolver that advertised a smaller buffer than the answer")
        print("needs will receive an oversized datagram from these. What it does with")
        print("it is its own choice, and at least one truncates it, which silently")
        print("drops records from the answer it caches and serves.")
        return 1
    print("All nameservers respected the advertised buffer.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("domains", nargs="*", default=DEFAULT_DOMAINS)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.25)
    ap.add_argument("--edns", metavar="DOMAIN",
                    help="check whether DOMAIN's nameservers respect the EDNS "
                         "buffer size, and exit")
    args = ap.parse_args()
    if args.edns:
        return edns_compliance(args.edns)
    domains = args.domains or DEFAULT_DOMAINS

    print(f"# {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"# host {platform.system()} {platform.machine()}  fqdn {socket.getfqdn()}")
    for server, label in RESOLVERS:
        print(f"# {label:<11} {server:<9} id.server={node_id(server)}")
    print(f"# {args.samples} TCP samples per resolver per domain\n")

    unstable, disagree = [], []
    for domain in domains:
        per_resolver = {}
        for server, label in RESOLVERS:
            seen = collections.Counter()
            for _ in range(args.samples):
                try:
                    seen[fingerprint(server, domain)] += 1
                except Exception as exc:
                    seen[(-1, -1, type(exc).__name__, False)] += 1
                time.sleep(args.delay)
            per_resolver[label] = seen
            variants = "  |  ".join(
                f"{n}rec {b}B {h} spf={'Y' if s else 'N'} x{c}"
                for (n, b, h, s), c in seen.most_common()
            )
            flag = "" if len(seen) == 1 else "   <-- UNSTABLE"
            print(f"{domain:<18} {label:<11} {variants}{flag}")
            if len(seen) > 1:
                unstable.append(f"{domain} @ {label}")

        hashes = {lbl: c.most_common(1)[0][0][2] for lbl, c in per_resolver.items()}
        agreed = len(set(hashes.values())) == 1
        print(f"{'':<18} {'':<11} cross-resolver identical: "
              f"{'yes' if agreed else 'NO -> ' + repr(hashes)}\n")
        if not agreed:
            disagree.append(domain)

    print("summary")
    print(f"  unstable (one resolver, differing answers): {unstable or 'none'}")
    print(f"  resolvers disagree:                         {disagree or 'none'}")
    return 1 if (unstable or disagree) else 0


if __name__ == "__main__":
    sys.exit(main())
