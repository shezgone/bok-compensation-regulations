"""Neo4j 드라이버 연결 유틸리티"""

from typing import Optional
from neo4j import GraphDatabase
from .config import Neo4jConfig


def get_driver(config: Optional[Neo4jConfig] = None):
    """Neo4j 드라이버 인스턴스 반환"""
    if config is None:
        config = Neo4jConfig()
    return GraphDatabase.driver(config.uri, auth=(config.username, config.password))
