"""
The real address of the caller (app/core/client_ip.py).

Behind the production proxy every connection comes from the proxy, so rate limits, audit entries and key address lists
need the address the proxy reports in X-Forwarded-For. That header is under the caller's control, so these tests pin down
when it is believed (only from a trusted proxy), how much of it (only what the proxies added, read from the right), and
that a caller can neither invent an address nor borrow someone else's.
"""
from types import SimpleNamespace

import pytest

from app.core.client_ip import client_ip, ip_allowed, normalise_address_list, parse_networks

PROXIES = parse_networks("10.0.0.0/8, 172.16.0.0/12")


def _req(peer, forwarded=None):
    headers = {} if forwarded is None else {"x-forwarded-for": forwarded}
    return SimpleNamespace(client=SimpleNamespace(host=peer) if peer else None, headers=headers)


def test_without_a_trusted_proxy_the_connection_address_is_used_and_the_header_ignored():
    assert client_ip(_req("203.0.113.5", "6.6.6.6"), trusted=()) == "203.0.113.5"


def test_a_header_from_an_address_that_is_not_a_trusted_proxy_is_ignored():
    assert client_ip(_req("198.51.100.9", "6.6.6.6"), trusted=PROXIES) == "198.51.100.9"


def test_a_trusted_proxy_reports_the_real_caller():
    assert client_ip(_req("10.0.0.5", "203.0.113.5"), trusted=PROXIES) == "203.0.113.5"


def test_an_address_invented_by_the_caller_is_never_reached():
    # the caller wrote 6.6.6.6; the proxy appended the real address on the right
    assert client_ip(_req("10.0.0.5", "6.6.6.6, 203.0.113.5"), trusted=PROXIES) == "203.0.113.5"


def test_several_trusted_proxies_in_a_row_are_skipped():
    assert client_ip(_req("10.0.0.5", "203.0.113.5, 172.20.0.2, 10.0.0.9"), trusted=PROXIES) == "203.0.113.5"


def test_when_every_address_is_a_proxy_the_caller_is_the_proxy():
    assert client_ip(_req("10.0.0.5", "10.0.0.9, 172.20.0.2"), trusted=PROXIES) == "10.0.0.5"


@pytest.mark.parametrize("header", [None, "", "  ,  ", "not-an-address", "203.0.113.5, garbage"])
def test_a_missing_or_unreadable_header_falls_back_to_the_proxy_never_to_a_guess(header):
    assert client_ip(_req("10.0.0.5", header), trusted=PROXIES) == "10.0.0.5"


def test_spaces_around_the_addresses_do_not_matter():
    assert client_ip(_req("10.0.0.5", "  203.0.113.5 ,10.0.0.9 "), trusted=PROXIES) == "203.0.113.5"


def test_an_ipv6_caller_is_reported_in_its_canonical_form():
    assert client_ip(_req("10.0.0.5", "2001:DB8:0:0:0:0:0:1"), trusted=PROXIES) == "2001:db8::1"


def test_an_ipv4_proxy_written_in_ipv6_form_is_still_recognised():
    assert client_ip(_req("::ffff:10.0.0.5", "203.0.113.5"), trusted=PROXIES) == "203.0.113.5"


def test_a_peer_that_is_not_an_address_is_returned_as_it_is():
    assert client_ip(_req("testclient", "6.6.6.6"), trusted=PROXIES) == "testclient"


def test_no_client_at_all_is_unknown_not_an_error():
    assert client_ip(_req(None), trusted=PROXIES) == "unknown"


def test_the_list_of_proxies_must_be_made_of_addresses_and_networks():
    assert len(parse_networks("10.0.0.0/8, 192.168.1.5")) == 2 and parse_networks("") == ()
    with pytest.raises(ValueError):
        parse_networks("10.0.0.0/8, nonsense")


@pytest.mark.parametrize("text, expected", [
    (None, None), ("", None), ("   ", None), (" , ,", None),
    ("203.0.113.7", "203.0.113.7"), ("203.0.113.7/32", "203.0.113.7"), ("203.0.113.0/24", "203.0.113.0/24"),
    (" 203.0.113.0/24 ,10.1.2.3, ", "203.0.113.0/24, 10.1.2.3"), ("203.0.113.9/24", "203.0.113.0/24"), ("2001:db8::/32", "2001:db8::/32"),
])
def test_a_key_list_is_normalised(text, expected):
    assert normalise_address_list(text) == expected


@pytest.mark.parametrize("text", ["nonsense", "300.1.1.1", "10.0.0.0/33", "10.0.0.1; 10.0.0.2", ",".join(f"10.0.0.{i}" for i in range(21))])
def test_a_bad_key_list_is_refused(text):
    with pytest.raises(ValueError):
        normalise_address_list(text)


@pytest.mark.parametrize("address, spec, allowed", [
    ("203.0.113.7", "203.0.113.0/24, 10.1.2.3", True), ("10.1.2.3", "203.0.113.0/24, 10.1.2.3", True),
    ("10.1.2.4", "203.0.113.0/24, 10.1.2.3", False), ("2001:db8::1", "203.0.113.0/24", False), ("2001:db8::1", "2001:db8::/32", True),
    ("not-an-address", "203.0.113.0/24", False), ("203.0.113.7", "garbage", False), ("203.0.113.7", "", False),
])
def test_an_address_is_checked_against_a_key_list_and_a_broken_list_refuses_everyone(address, spec, allowed):
    assert ip_allowed(address, spec) is allowed
