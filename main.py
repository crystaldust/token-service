import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    "http://developer-activity-console"
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

ck_server = CKServer(CK_HOST, CK_PORT, CK_USER, CK_PASS, CK_DB)


def ensure_table_exist():
    print(CREATE_TABLE_SQL)
    ck_server.execute_no_params(CREATE_TABLE_SQL)


@app.get('/tokens/list', response_model=list[GitHubToken])
async def list_tokens():
    list_tokens_sql = f"SELECT * from {CK_DB}"
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


@app.post("/tokens/upload")
async def upload_tokens(tokens: list[GitHubToken]):
    print(tokens)
    values = [(t.account, t.token, t.limit, t.status) for t in tokens]
    result = ck_server.execute(f'INSERT INTO {CK_DB} VALUES ', values)
    print(f'INSERT INTO {CK_DB} VALUES ', values)

    print(result)
    return 'ok'


if __name__ == "__main__":
    ensure_table_exist()
    uvicorn.run(app, host="0.0.0.0", port=8000)
