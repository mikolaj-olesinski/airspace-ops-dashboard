"""HTTP session with a working SSL verification path, connection-level retries, and a
real wall-clock request timeout.

Root cause of the multi-minute hangs seen while building this backend: `requests`
verifies TLS certificates against the `certifi` package's bundled CA file by default.
In this environment (Python 3.14 on Windows, project on a UNC path), loading that
bundle into an SSLContext for verification was pathologically slow / effectively hung
(confirmed via isolated tests: raw sockets using `ssl.create_default_context()` -- the
OS/Windows certificate store -- connected in ~0.3s, while plain `requests.get()` to the
same host with default (certifi) verification exceeded 30s+; `verify=False` was
instant, isolating it to certificate verification specifically). SystemCertAdapter
below verifies against the OS trust store instead of certifi's, which is fast, without
disabling verification.

On top of that: retries are kept modest (2 attempts, short backoff) -- a live-dashboard
endpoint should fail fast and let the next poll cycle try again, not block the request
retrying against something that's still down. And `requests`' own `timeout=` only
bounds the connect phase and the gap between individual reads, not the total request
duration -- a server that trickles a response slowly (a chunk every few seconds, never
going fully silent) could still keep a request alive well past that number.
run_with_hard_timeout() adds an actual wall-clock cap on top, running the call in a
worker thread and giving up on `Future.result(timeout=...)` if it doesn't return in
time (the abandoned thread is left to finish in the background since Python can't
forcibly kill a thread, but the caller is no longer blocked on it).
"""

import concurrent.futures
import ssl

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SystemCertAdapter(HTTPAdapter):
    """Verifies TLS certs against the OS trust store instead of certifi's bundle."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = ssl.create_default_context()
        return super().init_poolmanager(*args, **kwargs)

    def cert_verify(self, conn, url, verify, cert):
        conn.cert_reqs = "CERT_REQUIRED"


def make_session(total_retries: int = 2) -> requests.Session:
    """A fresh Session per caller, not a shared module-level singleton, so concurrent
    callers (e.g. /predictions firing 7 weather requests from a ThreadPoolExecutor)
    each get their own connection pool."""
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = SystemCertAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_TIMEOUT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=16)


def run_with_hard_timeout(fn, *args, timeout: float, **kwargs):
    """Run fn(*args, **kwargs) with a true wall-clock timeout (see module docstring
    for why requests' own timeout= isn't enough here). Raises
    concurrent.futures.TimeoutError if it doesn't finish in time."""
    future = _TIMEOUT_EXECUTOR.submit(fn, *args, **kwargs)
    return future.result(timeout=timeout)
