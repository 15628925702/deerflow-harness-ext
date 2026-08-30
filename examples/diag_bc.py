"""Diagnose one BrowseComp question: what does the model actually emit per turn?"""
import io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import SYSTEM, _parse_action, call_model  # noqa: E402
from web_tools import web_search, web_fetch  # noqa: E402

DS = os.environ.get("BC_DS",
                    r"C:/Users/22909/AppData/Roaming/CherryStudio/Data/Agents/system/2026-08-28/3660005b-ac33-4453-8fea-4db4e6a6b513/drb_data/benchmarks/datasets/BrowseComp/standardized_data.jsonl")
IDX = int(os.environ.get("BC_IDX", "5"))
STEPS = int(os.environ.get("BC_STEPS", "8"))

ds = [json.loads(l) for l in io.open(DS, encoding="utf-8")]
q = ds[IDX]["task_question"]
gt = ds[IDX]["ground_truth"]
print("Q:", q[:100])
print("GT:", gt)
system = SYSTEM + "\nTOOLS\n  web_search(query)\n  web_fetch(url)"
transcript = [{"role": "user", "content": f"QUESTION\n{q}"}]

for step in range(STEPS):
    r = call_model([{"role": "system", "content": system}] + transcript)
    print(f"\n--- step {step} ---")
    print("REPLY:", r[:250].replace("\n", " "))
    a = _parse_action(r)
    print("ACTION:", a)
    if a and "final_answer" in a:
        print("FINAL:", a["final_answer"])
        break
    transcript.append({"role": "assistant", "content": r})
    tool = a.get("tool") if a else None
    if tool == "web_search":
        obs = web_search(str(a.get("query") or a.get("q") or ""))
        n = len(obs.get("results", []))
        print(f"  -> web_search {n} results:", [x['title'][:40] for x in obs.get('results', [])][:3])
    elif tool == "web_fetch":
        obs = web_fetch(str(a.get("url") or ""))
        print(f"  -> web_fetch len {len(obs.get('text',''))}")
    else:
        obs = {"error": "no valid tool action"}
        print("  -> NO VALID ACTION")
    transcript.append({"role": "user", "content": json.dumps(obs, ensure_ascii=False)[:2000]})
