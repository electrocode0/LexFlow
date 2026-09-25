import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL

def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)