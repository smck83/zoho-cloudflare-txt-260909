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
    import dns.message
    import dns.query
    import dns.rdataclass
    import dns.rdatatype
except ImportError:
    sys.exit("needs dnspython:  pip install dnspython")

RESOLVERS = [("1.1.1.1", "Cloudflare"), ("8.8.8.8", "Google"), ("9.9.9.9", "Quad9")]

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("domains", nargs="*", default=DEFAULT_DOMAINS)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args()
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
