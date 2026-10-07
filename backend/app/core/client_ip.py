"""
The real address of the caller, for rate limits, audit entries and the address list of an API key.

Behind a reverse proxy (nginx, in production) every request arrives from the PROXY's address. Using the connection
address would give every user ONE shared rate-limit bucket (a single caller could then lock everybody out of signing in)
and would put the proxy's address in every audit entry. The proxy reports the real caller in X-Forwarded-For, but that
header is also under the caller's control, so it is believed only in two cases, and only in part:

  1. the connection itself comes from a TRUSTED proxy (the networks in TRUSTED_PROXIES); from anyone else the header is ignored;
  2. the list is read from the RIGHT, skipping trusted proxies; the first address that is not one of ours is the caller.
     Whatever a caller wrote further left (to invent an address) is never reached.

When nothing is configured nothing is trusted and the connection address is used, which is right without a proxy.
"""
import ipaddress
from functools import lru_cache

MAX_LIST_ENTRIES = 20


@lru_cache(maxsize=32)
def parse_networks(spec: str) -> tuple:
    """'10.0.0.0/8, 192.168.1.5' -> a tuple of networks. Raises ValueError on anything that is not an address or a network."""
    nets = []
    for part in (spec or "").split(","):
        part = part.strip()
        if part:
            nets.append(ipaddress.ip_network(part, strict=False))
    return tuple(nets)


def _addr(text):
    """An address object, or None. An IPv4 address written in IPv6 form (::ffff:10.0.0.5) counts as the IPv4 address."""
    try:
        addr = ipaddress.ip_address((text or "").strip())
    except ValueError:
        return None
    mapped = getattr(addr, "ipv4_mapped", None)
    return mapped if mapped is not None else addr


def _in(addr, nets) -> bool:
    return any(addr in net for net in nets)


def _configured() -> tuple:
    from app.core.config import settings   # imported here so this module has no dependency of its own
    return parse_networks(settings.TRUSTED_PROXIES)


def validate_trusted_proxies() -> None:
    """Called when the application starts: a mistake in TRUSTED_PROXIES must stop it, not be silently ignored."""
    from app.core.config import settings
    try:
        nets = parse_networks(settings.TRUSTED_PROXIES)
    except ValueError as exc:
        raise RuntimeError(f"TRUSTED_PROXIES is not a comma-separated list of addresses or networks: {exc}") from exc
    if not nets:
        import logging
        from app.core.startup_checks import is_production
        if is_production(settings.ENVIRONMENT):
            logging.getLogger(__name__).warning(
                "TRUSTED_PROXIES is empty in production: behind a proxy, every rate limit and audit entry will see only the proxy's address."
            )


def client_ip(request, trusted=None) -> str:
    """The address of the real caller as text (the connection address when no trusted proxy is involved)."""
    peer = request.client.host if getattr(request, "client", None) else "unknown"
    nets = _configured() if trusted is None else trusted
    peer_addr = _addr(peer)
    if not nets or peer_addr is None or not _in(peer_addr, nets):
        return peer                                  # no proxy configured, or not from one: believe nothing in the headers
    chain = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    for item in reversed(chain):
        addr = _addr(item)
        if addr is None:
            return peer                              # something that is not an address among ours: do not guess
        if not _in(addr, nets):
            return str(addr)
    return peer                                      # empty, or every address is a proxy of ours: the caller is the proxy


def normalise_address_list(text):
    """For a key's allowed addresses: 'a, b' -> canonical text, or None for blank. Raises ValueError on a bad entry."""
    if text is None or not text.strip():
        return None
    items = [p.strip() for p in text.split(",") if p.strip()]
    if not items:
        return None                      # only commas and spaces: the same as no list
    if len(items) > MAX_LIST_ENTRIES:
        raise ValueError(f"at most {MAX_LIST_ENTRIES} addresses or networks")
    out = []
    for item in items:
        try:
            net = ipaddress.ip_network(item, strict=False)
        except ValueError:
            raise ValueError(f"'{item}' is not an IP address or network (for example 203.0.113.7 or 203.0.113.0/24)")
        out.append(str(net.network_address) if net.prefixlen == net.max_prefixlen else str(net))
    return ", ".join(out)


def ip_allowed(address: str, spec: str) -> bool:
    """Is this address inside the list? A list that cannot be read, or an address that is not one, is refused (fail closed)."""
    try:
        nets = parse_networks(spec)
    except ValueError:
        return False
    addr = _addr(address)
    return bool(nets) and addr is not None and _in(addr, nets)
