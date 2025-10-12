import os, json, boto3
from botocore.exceptions import ClientError

MODEL_ID = os.environ["BEDROCK_MODEL_ID"]  # e.g. anthropic.claude-3-haiku-20240307-v1:0
REGION   = os.environ.get("BEDROCK_REGION", "us-east-1")
brt = boto3.client("bedrock-runtime", region_name=REGION)

def invoke_bedrock_claude(messages):
    """
    messages: list of {"role": "user" | "assistant" | "system", "content": "text"}
    We convert "system" entries to top-level `system` and keep only user/assistant in `messages`.
    """
    system_chunks = []
    anthro_msgs = []
    for m in messages:
        role = m.get("role")
        text = m.get("content", "")
        if role == "system":
            if text:
                system_chunks.append(text)
            continue
        # Anthropic messages require content as an array of blocks
        if role not in ("user", "assistant"):
            # default unknown roles to user to avoid schema errors
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
        resp = brt.invoke_model(
            modelId=MODEL_ID,                 # <- pass model here
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
    except ClientError as e:
        raise RuntimeError(f"Bedrock invoke failed: {e}") from e

    payload = json.loads(resp["body"].read())
    # Anthropic returns {content:[{type:"text",text:"..."}], ...}
    parts = payload.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def invoke_bedrock_llama(prompt: str, max_tokens=1500, temperature=0):
    """
    For meta.llama3* models on Bedrock. Uses a simple text prompt.
    """
    body = {
      "prompt": prompt,
      "max_gen_len": max_tokens,
      "temperature": temperature,
      "top_p": 0.9
    }
    resp = _bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    out = json.loads(resp["body"].read())
    return out.get("generation","")
