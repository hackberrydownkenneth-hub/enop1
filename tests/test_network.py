"""ネットワーク制限ロジックのユニットテスト。"""

from timecard import network


def test_parse_networks_empty():
    assert network.parse_networks(None) == []
    assert network.parse_networks("") == []


def test_parse_networks_cidr_and_ip():
    nets = network.parse_networks("192.168.10.0/24, 203.0.113.5")
    assert len(nets) == 2


def test_is_allowed_no_restriction():
    # ネットワーク未設定なら常に許可
    assert network.is_allowed("8.8.8.8", []) is True


def test_is_allowed_within_subnet():
    nets = network.parse_networks("192.168.10.0/24")
    assert network.is_allowed("192.168.10.42", nets) is True
    assert network.is_allowed("192.168.11.42", nets) is False


def test_is_allowed_single_ip():
    nets = network.parse_networks("203.0.113.5")
    assert network.is_allowed("203.0.113.5", nets) is True
    assert network.is_allowed("203.0.113.6", nets) is False


def test_is_allowed_invalid_ip():
    nets = network.parse_networks("192.168.10.0/24")
    assert network.is_allowed("not-an-ip", nets) is False
    assert network.is_allowed(None, nets) is False


def test_client_ip_direct():
    assert network.client_ip("10.0.0.1", None, trust_proxy=False) == "10.0.0.1"


def test_client_ip_uses_forwarded_when_trusted():
    ip = network.client_ip("10.0.0.1", "203.0.113.9, 10.0.0.1", trust_proxy=True)
    assert ip == "203.0.113.9"


def test_client_ip_ignores_forwarded_when_untrusted():
    ip = network.client_ip("10.0.0.1", "203.0.113.9", trust_proxy=False)
    assert ip == "10.0.0.1"
