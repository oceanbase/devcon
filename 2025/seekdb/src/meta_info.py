import os
from pathlib import Path
from collections import namedtuple

Tourism = namedtuple('Tourism', ['name', 'place', 'height', 'introduce'])

BGE_SMALL_ZH = 'BAAI/bge-small-zh'
BGE_BASE_ZH = 'BAAI/bge-base-zh'
DISTILUSE_BASE_MULTILINGUAL_CASED = 'distiluse-base-multilingual-cased'

class MetaInfo:
    COLLECTION_NAME = "workshop"
    EMBEDDING_MODEL_NAME = BGE_SMALL_ZH

    @staticmethod
    def tourism_path() -> str:
        # Get parent directory: go up one level from src/ to seekdb/
        parent_dir = Path(__file__).parent.parent
        return str(parent_dir / 'tourism')

class ClientSettings:
    def __init__(self, path:str = None, host: str = None, port: int = None, user: str = None, password: str = '', database: str = None):
        self.path = path
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database