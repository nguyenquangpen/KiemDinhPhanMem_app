# services/db.py

import mysql.connector
from services.config import load_mysql_config

def get_connection():
    return mysql.connector.connect(**load_mysql_config())
