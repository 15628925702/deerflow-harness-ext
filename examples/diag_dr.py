"""Diagnose what the deep-research model actually returns in plain chat completions."""
import io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import call_model  # noqa: E402

DS = r"C:/Users/22909/AppData/Roaming/CherryStudio/Data/Agents/system/2026-08-28/3660005b-ac33-4453-8fea-4db4e6a6b513/drb_data/benchmarks/datasets/BrowseComp/standardized_data.jsonl"
ds = [json.loads(l) for l in io.open(DS, encoding="utf-8")]
q = ds[0]["task_question"]

prompt = (
    "You are a deep-research agent. Answer the question by searching the web.\n"
    "Reply with ONE JSON tool call:\n"
    '{"tool": "web_search", "query": "..."}\n'
    f"QUESTION: {q}"
)
r = call_model([{"role": "user", "content": prompt}], max_tokens=600)
print("MODEL:", os.environ.get("APODEX_MODEL"))
print("REPLY (first 600):")
print(r[:600])
print("---ends---")
