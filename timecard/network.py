"""打刻を許可するネットワーク(会社 Wi-Fi)の判定ロジック。

会社の Wi-Fi に接続しているときだけ打刻できるようにするため、
リクエスト元 IP アドレスを許可ネットワーク(CIDR)のリストと照合する。

社内 Wi-Fi 経由のアクセスは、社内 LAN のサブネット(サーバーが社内にある場合)
または会社のグローバル IP(クラウド運用でオフィスから出ていく固定 IP がある場合)
に一致する。これらを `TIMECARD_ALLOWED_NETWORKS` に設定して制限する。
"""

from __future__ import annotations

import ipaddress
from ipaddress import IPv4Network, IPv6Network

Network = IPv4Network | IPv6Network


def parse_networks(spec: str | None) -> list[Network]:
    """カンマ区切りの CIDR / IP 文字列をネットワークのリストに変換する。

    例: "192.168.10.0/24, 203.0.113.5" → [IPv4Network, IPv4Network]
    空文字や None の場合は空リスト(=制限なし)を返す。
    """
    if not spec:
        return []
    networks: list[Network] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        # 単一 IP でも /32・/128 のネットワークとして扱う
        networks.append(ipaddress.ip_network(part, strict=False))
    return networks


def is_allowed(ip_str: str | None, networks: list[Network]) -> bool:
    """指定 IP が許可ネットワークに含まれるか判定する。

    networks が空(未設定)の場合は制限なしとみなし True を返す。
    """
    if not networks:
        return True
    if not ip_str:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def client_ip(remote_addr: str | None, forwarded_for: str | None, trust_proxy: bool) -> str | None:
    """リクエスト元の実 IP を求める。

    リバースプロキシ配下で運用する場合は trust_proxy=True とし、
    X-Forwarded-For の先頭(元クライアント)を採用する。
    """
    if trust_proxy and forwarded_for:
        # "client, proxy1, proxy2" の先頭がオリジナル
        return forwarded_for.split(",")[0].strip()
    return remote_addr
