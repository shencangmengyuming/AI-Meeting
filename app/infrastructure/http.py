import httpx


def create_http_client(
    connect_timeout: float,
    read_timeout: float,
    write_timeout: float,
    pool_timeout: float,
) -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=write_timeout,
        pool=pool_timeout,
    )
    return httpx.AsyncClient(timeout=timeout)
