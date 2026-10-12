"""Duplicate detection.

Two levels: the same URL (after canonicalisation) is the same article and is
stored once; the same story from different publishers shares a cluster, and
every publisher stays visible with its own link.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .classify import normalize_ar

_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|ref_src$|cmpid$|ocid$|"
                       r"at_medium$|at_campaign$|ito$|__twitter_impression$)")


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") or host.startswith("amp."):
        host = host.split(".", 1)[1]
    path = re.sub(r"/(amp|amp\.html)/?$", "", parts.path) or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not _TRACKING.match(k.lower())))
    return urlunsplit((scheme, host, path, query, ""))


_STOP = {
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "at", "as", "by", "with", "is",
    "are", "after", "from", "over", "says", "say", "live", "update", "updates", "news",
    "في", "من", "علي", "الي", "عن", "مع", "بعد", "و", "ان", "قال", "اخبار", "عاجل", "مباشر",
}
_WORD = re.compile(r"[\w]+", re.UNICODE)


def title_fingerprint(title: str) -> str:
    """Order-insensitive hash of a title's significant words.

    Publisher suffixes (" - Reuters", " | Al Jazeera") are stripped first, so
    the same wire story carried by two outlets lands in one cluster.
    """
    title = re.split(r"\s[-|–—]\s(?=[^-|–—]{1,40}$)", title.strip())[0]
    words = [w for w in _WORD.findall(normalize_ar(title.lower())) if w not in _STOP and len(w) > 1]
    key = " ".join(sorted(set(words)))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:32]
