"""
URL validation utilities for SSRF protection.
Prevents requests to internal networks, localhost, and other dangerous destinations.
"""

import ipaddress
import socket
from typing import Optional, Set
from urllib.parse import urlparse

# Private IP ranges that should be blocked
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),  # This network
]

# Blocked hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "metadata.azure.com",  # Azure metadata
    "kubernetes.default.svc",  # Kubernetes
}

# Allowed URL schemes
ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in PRIVATE_IP_RANGES:
            if ip in network:
                return True
        return False
    except ValueError:
        # Invalid IP address format
        return False


def resolve_hostname(hostname: str) -> Set[str]:
    """Resolve hostname to IP addresses."""
    try:
        # Get both IPv4 and IPv6 addresses
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        return {info[4][0] for info in infos}
    except socket.gaierror:
        return set()


def validate_url(
    url: str,
    allow_localhost: bool = False,
    allow_private: bool = False,
    allowed_schemes: Optional[Set[str]] = None,
    blocked_hosts: Optional[Set[str]] = None,
) -> str:
    """
    Validate a URL for SSRF protection.

    Args:
        url: The URL to validate
        allow_localhost: Whether to allow localhost (default: False)
        allow_private: Whether to allow private IP ranges (default: False)
        allowed_schemes: Set of allowed URL schemes (default: http, https)
        blocked_hosts: Additional hostnames to block

    Returns:
        The validated URL

    Raises:
        SSRFError: If the URL fails validation
    """
    if not url:
        raise SSRFError("URL is required")

    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFError(f"Invalid URL format: {e}")

    # Check scheme
    schemes = allowed_schemes or ALLOWED_SCHEMES
    if parsed.scheme.lower() not in schemes:
        raise SSRFError(f"URL scheme '{parsed.scheme}' is not allowed. Allowed: {schemes}")

    # Get hostname
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL must contain a hostname")

    hostname_lower = hostname.lower()

    # Check blocked hostnames
    all_blocked = BLOCKED_HOSTNAMES.copy()
    if blocked_hosts:
        all_blocked.update(blocked_hosts)

    if not allow_localhost and hostname_lower in all_blocked:
        raise SSRFError(f"Access to hostname '{hostname}' is not allowed")

    # Check if hostname is an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if not allow_localhost and ip.is_loopback:
            raise SSRFError("Access to loopback addresses is not allowed")
        if not allow_private and ip.is_private:
            raise SSRFError("Access to private IP addresses is not allowed")
        if ip.is_multicast:
            raise SSRFError("Access to multicast addresses is not allowed")
        if ip.is_reserved:
            raise SSRFError("Access to reserved addresses is not allowed")
    except ValueError:
        # Not an IP address, resolve the hostname
        resolved_ips = resolve_hostname(hostname)

        if not resolved_ips:
            raise SSRFError(f"Could not resolve hostname: {hostname}")

        for ip_str in resolved_ips:
            try:
                ip = ipaddress.ip_address(ip_str)
                if not allow_localhost and ip.is_loopback:
                    raise SSRFError(f"Hostname '{hostname}' resolves to loopback address")
                if not allow_private and ip.is_private:
                    raise SSRFError(f"Hostname '{hostname}' resolves to private address")
                if ip.is_multicast:
                    raise SSRFError(f"Hostname '{hostname}' resolves to multicast address")
                if ip.is_reserved:
                    raise SSRFError(f"Hostname '{hostname}' resolves to reserved address")
            except ValueError:
                continue

    # Check for suspicious port numbers
    port = parsed.port
    if port is not None:
        # Block common internal service ports
        blocked_ports = {22, 23, 25, 110, 143, 389, 445, 3306, 5432, 6379, 27017}
        if port in blocked_ports:
            raise SSRFError(f"Access to port {port} is not allowed")

    return url


def validate_webhook_url(url: str) -> str:
    """
    Validate a webhook URL with stricter rules.

    Webhooks should only go to public HTTPS endpoints.
    """
    return validate_url(
        url,
        allow_localhost=False,
        allow_private=False,
        allowed_schemes={"https"},
    )


def validate_feed_url(url: str) -> str:
    """
    Validate an RSS/Atom feed URL.

    Feeds can use HTTP or HTTPS but not internal addresses.
    """
    return validate_url(
        url,
        allow_localhost=False,
        allow_private=False,
        allowed_schemes={"http", "https"},
    )
