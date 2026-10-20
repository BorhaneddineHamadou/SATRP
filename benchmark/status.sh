#!/bin/bash
# Quick campaign status: queue summary + rows per store.
S=~/satrp_mutation/ads/store
echo "== $(date)"; squeue -u $USER -o "%.12i %.9j %.2t" | awk 'NR>1{split($1,a,"_"); print a[1], $2, $3}' | sort | uniq -c
for st in openpilot transfuser; do
  if [ $st = openpilot ]; then R=$S/$st/results; else R=$S/$st; fi
  for k in base screen matrix; do
    n=$(cat $R/jobs_${k}*_task*.results.jsonl 2>/dev/null | wc -l); tot=$(cat $S/$st/jobs_${k}.jsonl 2>/dev/null | wc -l)
    [ "$k" = screen ] && tot=612
    printf "%-10s %-6s %5d / %5d\n" $st $k $n $tot
  done
done
echo "-- matrix outcome mix"; for st in openpilot transfuser; do if [ $st = openpilot ]; then R=$S/$st/results; else R=$S/$st; fi; cat $R/jobs_matrix_task*.results.jsonl 2>/dev/null | python3 -c "
import sys,json,collections; rows=[json.loads(l) for l in sys.stdin if l.strip()]
print('$st', len(rows), dict(collections.Counter(str(r.get('outcome'))[:16] for r in rows)))" 2>/dev/null; done
