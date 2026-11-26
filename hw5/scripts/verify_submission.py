#!/usr/bin/env python3
"""Offline validation against preserved raw evidence. No external dependencies."""
import hashlib,json,csv
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text())
ref=load('reference/combined_30.json');serial=load('results/results/tuned.json');parallel=load('results/results/parallel.json')
assert ref==serial==parallel
v=load('results/results/verification.json');assert all(v[x] for x in ['all_groups_equal_hw3','serial_equal_hw3','parallel_equal_serial'])
assert len(ref)==v['groups']==170019
mem=load('results/memory-sizing.json');assert mem['tuned_limit_mib']*1048576>=mem['measured']['cgroup_peak_bytes']*1.3
pods=load('logs/oom-pods.json')['items'];oom=next(p for p in pods if p['metadata']['labels'].get('job-name')=='oom')['status']['containerStatuses'][0]['state']['terminated'];assert oom['reason']=='OOMKilled' and oom['exitCode']==137
pods=load('logs/parallel-pods.json')['items'];parts=[p for p in pods if p['metadata']['labels'].get('job-name')=='parallel'];assert len(parts)==4
assert {p['metadata']['annotations']['batch.kubernetes.io/job-completion-index'] for p in parts}=={'0','1','2','3'}
assert all(p['status']['phase']=='Succeeded' for p in parts)
intervals=[p['status']['containerStatuses'][0]['state']['terminated'] for p in parts]
# Kubernetes timestamps have one-second precision; keep the raw interval evidence.
max_concurrency=max(sum(q['startedAt']<=p['startedAt']<q['finishedAt'] for q in intervals) for p in intervals)
assert max_concurrency>=2,intervals
waiter=next(p for p in load('logs/cpu-pending-pods.json')['items'] if p['metadata']['name']=='cpu-wait');assert waiter['status']['phase']=='Pending'
assert any(c.get('reason')=='Unschedulable' and 'Insufficient cpu' in c.get('message','') for c in waiter['status']['conditions'])
sched=load('results/scheduling.json');assert any(x.get('reason')=='Preempted' and x.get('involvedObject',{}).get('uid')==sched['victim_uid'] for x in load('logs/preemption-events.json')['items'])
assert next(p for p in load('logs/preemption-pods.json')['items'] if p['metadata']['name']=='high')['status']['phase']=='Running'
assert 'exceeded quota' in (ROOT/'logs/quota-rejection.txt').read_text()
assert next(p for p in load('logs/quota-recovered-pods.json')['items'] if p['metadata']['name']=='quota-rejected')['status']['phase']=='Running'
pvc=load('logs/rustfs-pvc.json')['items'];assert len(pvc)==8 and all(p['status']['phase']=='Bound' for p in pvc)
expected=load('reference/dataset_manifest.json')['normalized_sha256'];assert hashlib.sha256((ROOT/'data/vacancies.csv').read_bytes()).hexdigest()==expected
status=load('results/experiment-status.json');assert all(status[k] for k in ['cpu_pending_verified','preemption_verified','quota_rejection_verified','quota_recovery_verified'])
with (ROOT/'results/top10_pairs.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f);writer.writerow(['rank','skill_1','skill_2','count'])
    for rank,(key,count) in enumerate(v['top10_pairs'],1):writer.writerow([rank,*json.loads(key),count])
result={'passed':True,'equal_groups':len(ref),'parallel_indices':4,'max_observed_container_overlap':max_concurrency,'oom_verified':True,'memory_margin_verified':True,'cpu_pending_verified':True,'preemption_uid_verified':True,'quota_rejection_and_recovery_verified':True,'eight_pvc_bound':True,'input_sha256_verified':True}
(ROOT/'results/offline-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
