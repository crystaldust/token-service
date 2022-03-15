import os

CK_DB = os.environ.get('CK_DB')

CREATE_TABLE_SQL = f'''
CREATE TABLE IF NOT EXISTS {CK_DB}
(

    `account` String,

    `token` String,

    `limit` UInt16,

    `status` String
)
ENGINE = MergeTree
ORDER BY account
SETTINGS index_granularity = 8192;
'''