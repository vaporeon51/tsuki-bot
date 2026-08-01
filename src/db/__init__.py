import os

import psycopg
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL")
CONN_DICT = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
POOL = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10, open=False)
