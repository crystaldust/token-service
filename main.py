import os

import requests
import uvicorn
from fastapi import FastAPI, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from ck import CKServer
from sqls import CREATE_TABLE_SQL


class GitHubToken(BaseModel):
    account: str
    token: str
    limit: int
    status: str


app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:8888",
    "http://developer-activity-console",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CK_HOST = os.environ.get('CK_HOST')
CK_PORT = os.environ.get('CK_PORT')
CK_USER = os.environ.get('CK_USER')
CK_PASS = os.environ.get('CK_PASS')
CK_DB = os.environ.get('CK_DB')
CK_TABLE = os.environ.get('CK_TABLE')
SYNC_TARGET_URL = os.environ.get('SYNC_TARGET_URL')
ENV = os.environ.get('ENV') or 'development'

ck_server = CKServer(CK_HOST, CK_PORT, CK_USER, CK_PASS, CK_DB)


def ensure_table_exist():
    ck_server.execute_no_params(CREATE_TABLE_SQL)


ensure_table_exist()


@app.get('/tokens/list', response_model=list[GitHubToken])
async def list_tokens():
    list_tokens_sql = f"SELECT * from {CK_TABLE}"
    result = ck_server.execute_no_params(list_tokens_sql)

    tokens = []
    for tup in result:
        account, token, limit, status = tup
        kwargs = {
            'account': account,
            'token': token,
            'limit': limit,
            'status': status
        }
        tokens.append(GitHubToken(**kwargs))

    return tokens


@app.post('/tokens/fetch', response_model=list[GitHubToken])
async def fetch_tokens(exclude_tokens: list[str] = [], num: int = 10):
    fetch_tokens_sql = f"SELECT * FROM {CK_TABLE} WHERE status = 'available'"
    if exclude_tokens:
        fetch_tokens_sql += f" AND token NOT IN {exclude_tokens}"

    fetch_tokens_sql += f' LIMIT {num}'

    result = ck_server.execute_no_params(fetch_tokens_sql)
    tokens = []
    for tup in result:
        account, token, limit, status = tup
        kwargs = {
            'account': account,
            'token': token,
            'limit': limit,
            'status': status
        }
        tokens.append(GitHubToken(**kwargs))

    return tokens


def fetch_all_tokens():
    result = ck_server.execute_no_params(f'SELECT * FROM {CK_TABLE}')
    tokens = []
    for tup in result:
        account, token, limit, status = tup
        kwargs = {
            'account': account,
            'token': token,
            'limit': limit,
            'status': status
        }
        tokens.append(GitHubToken(**kwargs))
    return tokens


@app.post('/tokens/sync')
async def sync_tokens():
    if ENV == 'production':
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f'api not provided in {ENV} env')

    all_tokens = fetch_all_tokens()
    jsonable_data = jsonable_encoder(all_tokens)
    requests.post(f'{SYNC_TARGET_URL}/tokens/recv_sync', json=jsonable_data)

    return ''


@app.post('/tokens/recv_sync')
async def sync_tokens(tokens: list[GitHubToken]):
    if ENV != 'production':
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f'api not provided in {ENV} env')

    for t in tokens:
        result = ck_server.execute_no_params(f"SELECT count() FROM {CK_TABLE} WHERE token = '{t.token}'")
        if result[0][0] > 0:
            logger.info(f"token {t.token} already exists, skip")
        else:
            tup = (t.account, t.token, t.limit, t.status)
            ck_server.execute_no_params(f"INSERT INTO {CK_TABLE} VALUES {tup}")


@app.post("/tokens/upload")
async def upload_tokens(tokens: list[GitHubToken]):
    duplicated = []
    inserted = []
    num_inserted = 0
    for t in tokens:
        result = ck_server.execute_no_params(f"SELECT count() FROM {CK_TABLE} WHERE token = '{t.token}'")
        if result[0][0] > 0:
            duplicated.append(t.token)
            continue
        num_inserted += ck_server.execute(f'INSERT INTO {CK_TABLE} VALUES ', [(t.account, t.token, t.limit, t.status)])
        inserted.append(t.token)

    res_obj = {
        'num_inserted': num_inserted,
        'duplicated': duplicated,
        'inserted': inserted
    }
    return res_obj


if __name__ == "__main__":
    ensure_table_exist()
    uvicorn.run(app, host="0.0.0.0", port=8000)
