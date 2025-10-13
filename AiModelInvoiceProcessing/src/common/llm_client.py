# src/common/llm_client.py
import os, json, boto3
from botocore.exceptions import ClientError
from .config import BEDROCK_MODEL_ID, BEDROCK_REGION  # uses safe defaults

def _client():
    return boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

def _is_anthropic(model_id: str) -> bool:
    return model_id.startswith("anthropic.")

def _is_llama(model_id: str) -> bool:
    return model_id.startswith("meta.llama")

def invoke_bedrock_claude(messages):
    """
    messages: list of {"role": "user"|"assistant"|"system", "content": "text"}
    Convert 'system' entries to top-level system; content must be array blocks.
    """
    system_chunks, anthro_msgs = [], []
    for m in messages:
        role = m.get("role")
        text = m.get("content", "")
        if role == "system":
            if text:
                system_chunks.append(text)
            continue
        if role not in ("user", "assistant"):
            role = "user"
        anthro_msgs.append({"role": role, "content": [{"type": "text", "text": text}]})

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "messages": anthro_msgs,
        "temperature": 0
    }
    if system_chunks:
        body["system"] = "\n".join(system_chunks)

    try:
        resp = _client().invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
    except ClientError as e:
        raise RuntimeError(f"Bedrock invoke failed (model='{BEDROCK_MODEL_ID}', region='{BEDROCK_REGION}'): {e}") from e

    payload = json.loads(resp["body"].read())
    parts = payload.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")

def invoke_bedrock_llama(prompt: str, max_tokens=1500, temperature=0):
    """
    For meta.llama3* models on Bedrock. Simple prompt format.
    """
    body = {
        "prompt": prompt,
        "max_gen_len": max_tokens,
        "temperature": temperature,
        "top_p": 0.9
    }
    try:
        resp = _client().invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
    except ClientError as e:
        raise RuntimeError(f"Bedrock invoke failed (model='{BEDROCK_MODEL_ID}', region='{BEDROCK_REGION}'): {e}") from e

    out = json.loads(resp["body"].read())
    return out.get("generation", "")
