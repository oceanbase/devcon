import sys
import os
from collections import namedtuple
from sentence_transformers import SentenceTransformer
import pyseekdb
#import pylibseekdb
from pyseekdb import HNSWConfiguration
from pyseekdb.client import DefaultEmbeddingFunction
import logging
import argparse

# Handle both relative and absolute imports
try:
    from .meta_info import MetaInfo, ClientSettings, Tourism
except ImportError:
    from meta_info import MetaInfo, ClientSettings, Tourism

_logger = logging.getLogger(__name__)


def _parse_tourism_file(filepath: str) -> Tourism:
    with open(filepath) as fp:
        name = fp.readline().strip()
        place = fp.readline().strip()
        height = int(fp.readline().strip())
        introduce = fp.read().strip()
        return Tourism(name, place, height, introduce)

def main(client_settings, tourism_path, collection_name, embedding_model_name, clean:bool):

    # Use server mode if host is provided, otherwise use embedded mode
    if client_settings.host:
        client = pyseekdb.Client(
            host=client_settings.host,
            port=client_settings.port,
            user=client_settings.user,
            password=client_settings.password,
            database=client_settings.database
        )
    else:
        client = pyseekdb.Client(
            path=client_settings.path,
            database=client_settings.database
        )

    if clean and client.has_collection(collection_name):
        client.delete_collection(collection_name)
    collection = client.create_collection(name=collection_name, embedding_function=DefaultEmbeddingFunction(model_name=embedding_model_name))
    tourism_list = [ _parse_tourism_file(tourism_path + '/' + filename) for filename in os.listdir(tourism_path) ]
    if len(tourism_list) == 0:
        print('no tourism data found')
        return
    ids = [ tourism.name for tourism in tourism_list ]
    documents = [ tourism.introduce for tourism in tourism_list ]
    metadatas = [ {'name': tourism.name, 'place': tourism.place, 'height': tourism.height} for tourism in tourism_list ]
    collection.add(ids=ids, documents=documents, metadatas=metadatas)

def _parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='127.0.0.1', help='The host of the database')
    parser.add_argument('--port', type=int, default=2881, help='The port of the database')
    parser.add_argument('--user', type=str, default='root', help='The user of the database')
    parser.add_argument('--password', type=str, default='', help='The password of the database')
    parser.add_argument('--database', type=str, default='test', help='The database of the database')
    parser.add_argument('--data-dir', type=str, default=os.environ.get('HOME', '') + '/seekdb', help='The directory of the data')
    parser.add_argument('--seekdb-mode', type=str, default='embeded', help='The seekdb mode, can be one of {embeded, server}')
    parser.add_argument('--embedding-model', type=str, default=MetaInfo.EMBEDDING_MODEL_NAME, help='The name of the embedding model')
    parser.add_argument('--collection-name', type=str, default=MetaInfo.COLLECTION_NAME, help='The name of the collection')
    parser.add_argument('--clean', action='store_true', help='Clean the collection')
    parser.add_argument('--log-level', type=str, default='WARNING', help='The log level, can be one of {DEBUG, INFO, WARNING, ERROR, CRITICAL}')
    return parser.parse_args(argv)

if __name__ == '__main__':
    argv = sys.argv[1:]
    args = _parse_args(argv)

    logging.basicConfig( level=args.log_level.upper(),
         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    if args.seekdb_mode.lower() == 'embeded':
        client_settings = ClientSettings(path=args.data_dir, database=args.database)
    else:
        client_settings = ClientSettings(host=args.host,
                                         port=args.port,
                                         user=args.user,
                                         password=args.password,
                                         database=args.database)
    main(client_settings=client_settings,
         tourism_path=MetaInfo.tourism_path(),
         collection_name=args.collection_name,
         clean=args.clean,
         embedding_model_name=args.embedding_model)
