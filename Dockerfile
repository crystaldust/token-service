FROM python:3.10-alpine
RUN apk add gcc musl-dev
ADD ck.py /project/
ADD main.py /project/
ADD requirements.txt /project/
WORKDIR /project/

RUN pip install -r ./requirements.txt
CMD ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0"]
