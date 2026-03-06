"""TypeDB 드라이버 연결 유틸리티"""

from typing import Optional

from typedb.driver import TypeDB, Credentials, DriverOptions

from .config import TypeDBConfig


def get_driver(config: Optional[TypeDBConfig] = None):
    """TypeDB 드라이버 인스턴스 반환"""
    if config is None:
        config = TypeDBConfig()
    creds = Credentials(config.username, config.password)
    opts = DriverOptions(is_tls_enabled=config.tls_enabled)
    return TypeDB.driver(config.address, creds, opts)
