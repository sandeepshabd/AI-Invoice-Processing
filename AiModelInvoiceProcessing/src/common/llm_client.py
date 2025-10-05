# src/common/llm_client.py
import os, json, boto3

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307")
REGION   = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION","us-east-1"))

_bedrock = boto3.client("bedrock-runtime", region_name=REGION)

def invoke_bedrock_claude(messages: list[dict], max_tokens=1500, temperature=0):
    """
    messages: [{"role":"system"/"user","content":"..."}]
    """
    # Claude 3 Messages API payload
    body = {
      "model": MODEL_ID,
      "max_tokens": max_tokens,
      "temperature": temperature,
      "messages": messages
    }
    resp = _bedrock.invoke_model(
      modelId=MODEL_ID,
      body=json.dumps(body)
    )
    out = json.loads(resp["body"].read())
    # Claude returns {"content":[{"type":"text","text":"..."}], ...}
    parts = out.get("content", [])
    text = "".join([p.get("text","") for p in parts if p.get("type")=="text"])
    return text

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
