import os
import random
import threading

import requests
import uvicorn
from fastapi import FastAPI, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
from redis import Redis

GITHUB_LIMIT_API_URL = "http://api.github.com/rate_limit"


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

REDIS_HOST = os.environ.get('REDIS_HOST') or 'localhost'
REDIS_PORT = os.environ.get('REDIS_PORT') or 6379
REDIS_USER = os.environ.get('REDIS_USER')
REDIS_PASS = os.environ.get('REDIS_PASS')

SYNC_TARGET_URL = os.environ.get('SYNC_TARGET_URL')
ENV = os.environ.get('ENV') or 'development'

REDIS_TOKEN_PREFIX = 'OSS_KNOW_GITHUB_TOKEN'
redis_cli = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASS,
    username=REDIS_USER,
    decode_responses=True)

all_keys = redis_cli.keys('*')


@app.get('/tokens/list', response_model=list[GitHubToken])
async def list_tokens():
    keys = redis_cli.keys(f'{REDIS_TOKEN_PREFIX}::ghp_*')

    tokens = []
    for key in keys:
        redis_hash = redis_cli.hgetall(key)
        tokens.append(GitHubToken(**redis_hash))

    validate_and_update_tokens(tokens)
    return tokens


@app.post('/tokens/fetch', response_model=list[GitHubToken])
async def fetch_tokens(exclude_tokens: list[str] = [], num: int = 10):
    temp_set_key = f'TEMP::{REDIS_TOKEN_PREFIX}::{random.randint(0, 0xffffff)}'
    redis_cli.sadd(temp_set_key, *exclude_tokens)
    # all_availabel_tokens is of type set
    all_availabel_tokens = redis_cli.sdiff(f'{REDIS_TOKEN_PREFIX}::available', temp_set_key)
    redis_cli.delete(temp_set_key)

    end_index = num
    if len(all_availabel_tokens) < num:
        end_index = len(all_availabel_tokens)

    available_tokens = list(all_availabel_tokens)[:end_index]
    tokens = []
    for token_str in available_tokens:
        redis_dict = redis_cli.hgetall(f'{REDIS_TOKEN_PREFIX}::{token_str}')
        tokens.append(GitHubToken(**redis_dict))

    return tokens


def fetch_all_tokens():
    keys = redis_cli.keys(f'{REDIS_TOKEN_PREFIX}::*')

    tokens = []
    for key in keys:
        redis_dict = redis_cli.hgetall(key)
        tokens.append(GitHubToken(**redis_dict))
    return tokens


def validate_and_update_token(token_model: GitHubToken):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
        'Authorization': 'token ' + token_model.token
    }
    response = requests.get(url=GITHUB_LIMIT_API_URL, headers=headers)

    if response.status_code >= 300:
        token_model.status = 'invalid'
        token_model.limit = -1
        redis_cli.sadd(f'{REDIS_TOKEN_PREFIX}::invalid', token_model.token)
    elif 200 <= response.status_code < 300:
        remaining = response.json()['rate']['remaining']
        token_model.status = 'available'
        token_model.limit = remaining
        # TODO: Should I put a run-out token into another set?
        # Like f'{REDIS_TOKEN_PREFIX}::runout', with expiration? (Then things become more complicated)
        redis_cli.sadd(f'{REDIS_TOKEN_PREFIX}::available', token_model.token)

    logger.debug(f"{token_model.token}, {token_model.status}, {token_model.limit}")
    key = f'{REDIS_TOKEN_PREFIX}::{token_model.token}'
    jsonable_dict = jsonable_encoder(token_model)
    success = redis_cli.hmset(key, jsonable_dict)
    if not success:
        logger.warning(f'Failed to update token {token_model.token}, {token_model.limit}, {token_model.status}')


def validate_and_update_tokens(token_models: list[GitHubToken]):
    """token_models(list) is a ref type, all items will be updated after validation"""
    threads = []
    for model in token_models:
        t = threading.Thread(target=validate_and_update_token, args=(model,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    return token_models


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

    tokens_to_sync = []
    for t in tokens:
        key = f'{REDIS_TOKEN_PREFIX}::{t.token}'
        if redis_cli.exists(key):
            logger.info(f"token {t.token} already exists, skip")
        else:
            tokens_to_sync.append(t)

    # validate_and_update_tokens(tokens_to_sync)
    for t in tokens_to_sync:
        jsonable_data = jsonable_encoder(t)
        key = f'{REDIS_TOKEN_PREFIX}::{t.token}'
        redis_cli.hmset(key, jsonable_data)


@app.post("/tokens/upload")
async def upload_tokens(tokens: list[GitHubToken]):
    duplicated = []
    inserted = []
    num_inserted = 0
    for t in tokens:
        key = f'{REDIS_TOKEN_PREFIX}::{t.token}'
        if redis_cli.exists(key):
            duplicated.append(t.token)
            continue

        mapping = {"account": t.account, "token": t.token, "limit": t.limit, "status": t.status}
        redis_cli.hmset(key, mapping)
        num_inserted += 1
        inserted.append(t.token)

    res_obj = {
        'num_inserted': num_inserted,
        'duplicated': duplicated,
        'inserted': inserted
    }
    return res_obj


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
