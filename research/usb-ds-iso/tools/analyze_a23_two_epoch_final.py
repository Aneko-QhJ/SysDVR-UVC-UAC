"""Read-only final model archive checks. No executable is run and no live root is consulted."""
import argparse,json
from pathlib import Path
from a23_final_archive import analyze
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--build',type=Path,required=True);p.add_argument('--require-complete',action='store_true');v=p.parse_args()
    try:result=analyze(v.archive,v.build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(result,indent=2));raise SystemExit(2 if v.require_complete and not result['analysis']['supplied_model_chain_complete'] else 0)
