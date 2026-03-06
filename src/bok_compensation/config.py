"""TypeDB 연결 설정"""

import os
from dataclasses import dataclass


@dataclass
class TypeDBConfig:
    address: str = os.getenv("TYPEDB_ADDRESS", "localhost:1729")
    database: str = os.getenv("TYPEDB_DATABASE", "bok-compensation-regulations")
    username: str = os.getenv("TYPEDB_USERNAME", "admin")
    password: str = os.getenv("TYPEDB_PASSWORD", "password")
    tls_enabled: bool = os.getenv("TYPEDB_TLS_ENABLED", "false").lower() == "true"
    schema_file: str = os.path.join(
        os.path.dirname(__file__), os.pardir, os.pardir, "schema", "compensation_regulation.tql"
    )
