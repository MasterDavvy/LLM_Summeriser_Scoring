import os, io, json, base64, urllib.parse, logging, traceback, textwrap
import boto3, pandas as pd
from botocore.exceptions import ClientError

# AWS clients
s3      = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

# ENV
BUCKET       = os.getenv("UPLOAD_BUCKET", "my-model-evalution")
AUTO_DELETE  = os.getenv("AUTO_DELETE", "1") == "1"
TEMP         = float(os.getenv("BEDROCK_TEMP", 0.7))
MAX_TOKENS   = int(os.getenv("MAX_TOKENS", 300))

# Llama3 inference profile ARN (always use this for Llama 3)
LLAMA_PROFILE_ARN = "arn:aws:bedrock:us-east-1:349440382087:inference-profile/us.meta.llama3-1-8b-instruct-v1:0"

# Logging & CORS
log = logging.getLogger()
log.setLevel(logging.INFO)
CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
}

def _resp(code: int, body=None):
    return {"statusCode": code, "headers": CORS, "body": json.dumps(body or {})}

def call_bedrock(model_id: str, prompt: str) -> str:
    """
    Universal Bedrock wrapper: Handles Llama3 via inference profile,
    all others as per model family.
    """
    # ----- Llama 3 (Profile ARN only!)
    if (model_id.startswith("meta.llama3") or
        model_id.startswith("us.meta.llama3") or
        model_id == LLAMA_PROFILE_ARN):
        actual_id = LLAMA_PROFILE_ARN
        prompt = textwrap.dedent(f"""\
            <|begin_of_text|><|start_header_id|>user<|end_header_id|>
            {prompt}
            <|eot_id|>
            <|start_header_id|>assistant<|end_header_id|>
        """)
        out = bedrock.invoke_model(
            modelId=actual_id,
            body=json.dumps({
                "prompt": prompt,
                "max_gen_len": MAX_TOKENS,
                "temperature": TEMP,
                "top_p": 0.9
            }),
            contentType="application/json",
            accept="application/json"
        )
        j = json.loads(out["body"].read())
        return j.get("generation", "").strip()

    # ----- Other models using Converse API (Nova, Mistral, etc.)
    if model_id.startswith(("amazon.nova", "mistral.")):
        out = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": TEMP}
        )
        return out["output"]["message"]["content"][0]["text"].strip()

    # ----- Chat-style (Claude 3, Cohere, etc.)
    body = (
        {"messages": [{"role": "user", "content": prompt}],
         "max_tokens": MAX_TOKENS, "temperature": TEMP}
        if model_id.startswith(("anthropic.", "cohere."))
        else {"inputText": prompt, "maxTokens": MAX_TOKENS, "temperature": TEMP}
    )

    raw = bedrock.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )["body"].read()

    j = json.loads(raw)
    return (
        j.get("results", [{}])[0].get("outputText")
        or j.get("completions", [{}])[0].get("data", {}).get("text")
        or j.get("generation")
        or j.get("outputText", "")
    ).strip()

# --- Lambda entry point
def lambda_handler(event, _ctx):
    try:
        method = (event.get("httpMethod") or "GET").upper()
        path   = event.get("path", "")
        log.info("%s %s", method, path)

        # OPTIONS – CORS
        if method == "OPTIONS":
            return _resp(200)

        # GET  /summerizeData/presign?name=<key>
        if method == "GET" and path.endswith("/presign"):
            qs  = event.get("queryStringParameters") or {}
            key = qs.get("name")
            if not key:
                return _resp(400, {"error": "query param 'name' required"})
            url = s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": BUCKET, "Key": key, "ContentType": "text/csv"},
                ExpiresIn=900, HttpMethod="PUT"
            )
            return _resp(200, {"url": url})

        # POST /summerizeData
        if method == "POST":
            pld = json.loads(event.get("body") or "{}")
            for f in ("target_columns", "model_ids"):
                if f not in pld:
                    return _resp(400, {"error": f"Missing {f}"})

            # ---- pull CSV -------------------------------------------------
            if "csv_content" in pld:
                b = pld["csv_content"]
                csv_bytes = b.encode() if isinstance(b, str) else base64.b64decode(b)
            elif "s3_key" in pld:
                key = pld["s3_key"]
                try:
                    csv_bytes = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                except ClientError:
                    return _resp(404, {"error": f"{key} not found in {BUCKET}"})
            else:
                return _resp(400, {"error": "Need 'csv_content' or 's3_key'"})

            # ---- slice rows ----------------------------------------------
            rs = pld.get("row_start", 1) or 1
            re = pld.get("row_end")
            df = pd.read_csv(io.BytesIO(csv_bytes))
            df = df.iloc[rs-1:re] if re else df.iloc[rs-1:]
            df["__txt__"] = df[pld["target_columns"]].astype(str).agg(" ".join, axis=1)

            # ---- summarise ----------------------------------------------
            out = []
            for idx, row in df.iterrows():
                per = {}
                for mid in pld["model_ids"]:
                    try:
                        per[mid] = call_bedrock(mid, row["__txt__"])
                    except Exception as e:
                        per[mid] = f"Error: {e}"
                out.append({"row": int(idx)+1, "models": per})

            # ---- delete temp file (ONLY if final_run and AUTO_DELETE) ---
            if pld.get("final_run") and AUTO_DELETE and "s3_key" in pld:
                try:
                    s3.delete_object(Bucket=BUCKET, Key=pld["s3_key"])
                except ClientError:
                    pass

            return _resp(200, {"summaries": out})

        return _resp(404, {"error": f"No route for {method} {path}"})

    except Exception as exc:
        log.error("UNHANDLED\n%s", traceback.format_exc())
        return _resp(500, {"error": str(exc)})
