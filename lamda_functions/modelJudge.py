"""
modelJudge Lambda (v5)  –  understands 2-row grouped header
----------------------------------------------------------------
* GET  /modelJudge/presign  -> presigned PUT for temp2/ uploads
* POST /modelJudge          -> stub evaluation, optional cleanup
"""
from __future__ import annotations
import os, json, csv, io, hashlib, logging, random
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

# ─── Config ──────────────────────────────────────────────────────
# TODO: Replace with your S3 bucket name where CSV files are stored (e.g., "my-model-evaluation")
# Current value is a default; update to match your AWS S3 bucket
BUCKET      = os.getenv("UPLOAD_BUCKET", "my-model-evalution")

# TODO: Replace with your desired presigned URL expiration time in seconds (e.g., 3600 for 1 hour)
# Current value is a default; adjust based on your security or usability needs
PRESIGN_TTL = int(os.getenv("PRESIGN_TTL", 900))

# TODO: Replace with your desired S3 object ACL (e.g., "public-read" or leave empty for private)
# Current value is optional; set to "" if no ACL is needed, or specify a valid AWS ACL
UPLOAD_ACL  = os.getenv("UPLOAD_ACL")            # optional

# TODO: Replace with your preferred logging level (e.g., "DEBUG", "INFO", "ERROR")
# Current value is a default; adjust based on your debugging or production needs
LOG_LEVEL   = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger(__name__)
s3  = boto3.client("s3")

# ─── Helpers ─────────────────────────────────────────────────────
def _cors(code:int, body:Any):
    if not isinstance(body, str):
        body = json.dumps(body, default=str)
    return {
        "statusCode": code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,x-api-key",
        },
        "body": body,
    }

def _presign_put(key:str)->str:
    params = {"Bucket": BUCKET, "Key": key, "ContentType": "text/csv"}
    if UPLOAD_ACL: params["ACL"] = UPLOAD_ACL
    return s3.generate_presigned_url("put_object", Params=params,
                                     ExpiresIn=PRESIGN_TTL, HttpMethod="PUT")

def _stable_rand(seed:str, lo:float, hi:float, d=2)->float:
    random.seed(int(hashlib.sha256(seed.encode()).hexdigest(),16))
    return round(random.uniform(lo, hi), d)

def dummy_metric(m,text): return _stable_rand(m+text[:50], .2,.95)
def dummy_judge(mid,txt): return _stable_rand(mid+txt[:80], 6,9.8,1)

# ─── Main handler ────────────────────────────────────────────────
def lambda_handler(event, _ctx):
    http = event.get("requestContext", {}).get("http", {})
    method, path = http.get("method","GET"), event.get("rawPath","")

    # CORS pre-flight
    if method == "OPTIONS":
        return _cors(200, {})

    # GET presign --------------------------------------------------
    if method=="GET" and path.endswith("/modelJudge/presign"):
        qs = event.get("queryStringParameters") or {}
        name = qs.get("name","")
        if not name.startswith("temp2/") or not name.endswith(".csv"):
            return _cors(400, {"error":"name must start with temp2/ and end with .csv"})
        try: url=_presign_put(name)
        except ClientError as e:
            log.error("presign err %s",e); return _cors(500,{"error":"presign fail"})
        return _cors(200, {"url":url})

    # POST evaluate -----------------------------------------------
    if method=="POST" and path.endswith("/modelJudge"):
        try: body=json.loads(event.get("body") or "{}")
        except json.JSONDecodeError: return _cors(400,{"error":"bad JSON"})

        s3_key   = body.get("s3_key","")
        judges   = body.get("judge_model_ids",[])
        metrics  = body.get("metrics",[])
        final    = bool(body.get("final_run"))

        if not s3_key.startswith("temp2/") or not s3_key.endswith(".csv"):
            return _cors(400,{"error":"s3_key must be in temp2/ and end with .csv"})

        # 1) download & parse 2-row-header CSV
        try:
            obj=s3.get_object(Bucket=BUCKET,Key=s3_key)
            lines=obj["Body"].read().decode("utf-8-sig").splitlines()
        except ClientError as e:
            code=e.response["Error"]["Code"]
            return _cors(404 if code=="NoSuchKey" else 500, {"error":code})

        if len(lines)<3:
            return _cors(400,{"error":"CSV missing data rows"})

        header_row = next(csv.reader([lines[1]]))   # second line = sub-headers
        data_iter  = csv.DictReader(io.StringIO("\n".join(lines[2:])),
                                    fieldnames=header_row)

        input_cols   = [c for c in header_row if c not in ("Row") and not c.endswith("Summary")]
        summary_cols = [c for c in header_row if c.endswith("Summary")]

        # 2) score rows
        judgements=[]
        for row in data_iter:
            row_no = int(row.get("Row",0) or 0)
            input_text = " ".join(row[c] or "" for c in input_cols).strip()
            metr_out = {m:dummy_metric(m,input_text) for m in metrics}
            judge_out={}
            for jm in judges:
                per=[dummy_judge(jm,row.get(col,"")) for col in summary_cols]
                judge_out[jm]=round(sum(per)/len(per),2) if per else None
            judgements.append({"row":row_no,"metrics":metr_out,"scores":judge_out})

        # 3) optional cleanup
        if final:
            try:s3.delete_object(Bucket=BUCKET,Key=s3_key)
            except ClientError as e: log.warning("cleanup %s",e)

        return _cors(200, {"judgements":judgements})

    return _cors(404, {"error":"no route"})
