# services/config.py

import configparser

def load_mysql_config():
    config = configparser.ConfigParser()
    config.read("config.ini")
    return {
        "host": config["mysql"]["host"],
        "port": int(config["mysql"]["port"]),
        "user": config["mysql"]["user"],
        "password": config["mysql"]["password"],
        "database": config["mysql"]["database"]
    }
