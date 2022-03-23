import os

CK_DB = os.environ.get('CK_DB')
CK_TABLE = os.environ.get('CK_TABLE')

CREATE_TABLE_SQL = f'''
CREATE TABLE IF NOT EXISTS {CK_DB}.{CK_TABLE}
(

    `account` String,

    `token` String,

    `limit` UInt16,

    `status` String
)
ENGINE = MergeTree
ORDER BY token
PRIMARY KEY token
SETTINGS index_granularity = 8192;
'''