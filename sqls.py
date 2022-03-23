import os

CK_DB = os.environ.get('CK_DB')
CK_TABLE = os.environ.get('CK_TABLE')
CK_CLUSTER = os.environ.get('CK_CLUSTER')

CREATE_TABLE_SQL = f'''
CREATE TABLE IF NOT EXISTS {CK_DB}.{CK_TABLE} on CLUSTER `{CK_CLUSTER}`
(

    `account` String,

    `token` String,

    `limit` UInt16,

    `status` String
)
ENGINE = MergeTree
ORDER BY token
SETTINGS index_granularity = 8192;
'''
