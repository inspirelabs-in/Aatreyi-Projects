from enum import Enum


class MediaType(str, Enum):
    TEXT = "TEXT"
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"
    POLL = "POLL"
    UNKNOWN = "UNKNOWN"


LOG_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "logs/app.log"

SUMMARY_SEPARATOR = "=" * 50

# Domain fragments used to detect affiliate / referral links.
# A URL is flagged as affiliate when it contains any of these substrings.
# Add or remove entries as your supported affiliate networks change.
AFFILIATE_PATTERNS: list[str] = [
    # Generic tracking parameters
    "ref=",
    "affiliate",
    "aff_id",
    "aff=",
    "partner",
    "promo=",
    "coupon=",
    # Major Indian affiliate networks
    "amzn.to",          # Amazon short links (almost always affiliate)
    "fkrt.it",          # Flipkart short links
    "clnk.in",          # Cuelinks
    "bitli.in",         # Bitlinks affiliate
    "go.social",        # Social affiliate
    "dealsheaven.in",
    "cashkaro.com",
    "desidime.com",
    "grabon.in",
    "mydala.com",
    # Global affiliate networks
    "shareasale.com",
    "clickbank.net",
    "jvzoo.com",
    "warriorplus.com",
    "impact.com",
    "partnerize.com",
    "awin.com",
    "cj.com",
    "rakutenmarketing.com",
    "pepperjam.com",
]
