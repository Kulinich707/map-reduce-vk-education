"""Offline independent verification of data, checkpoints, and both real experiments."""
import csv,hashlib,itertools,json,math,re
from collections import Counter
from core import ROOT,digest,encode,save

def load(p):return json.loads((ROOT/p).read_text())
def main():
    manifest=load('reference/manifest.json')
    source_hash=digest((ROOT/'data/all_sources.csv').read_bytes())
    assert source_hash==manifest['normalized_sha256']
    seen=set();rows=[]
    for r in csv.DictReader((ROOT/'data/all_sources.csv').open(encoding='utf-8',newline='')):
        if r['id'] in seen:continue
        seen.add(r['id'])
        skills=json.loads(r['skills_json'])
        if r['role']!='Программист, разработчик':continue
        pattern=r'php(?:[578](?:\.\d+)*)?'
        if not (re.search(r'\b'+pattern+r'\b',r['title'],re.I) or any(re.fullmatch(pattern,s.strip(),re.I) for s in skills)):continue
        rows.append(sorted(set(re.sub(r'\s+',' ',s.strip().lower()) for s in skills if s.strip())))
    assert len(rows)==8661
    checks=[];independent={}
    for cap in [5,10,30]:
        counted=Counter()
        for skills in rows:
            for n in [1,2,3]:
                for combo in itertools.combinations(skills[:cap],n):counted[json.dumps(combo,ensure_ascii=False,separators=(',',':'))]+=1
        reference=load(f'reference/combined_{cap}.json');assert counted==reference
        independent[str(cap)]=counted
        for n in [1,2,3]:
            counts={k:v for k,v in counted.items() if len(json.loads(k))==n}
            total=sum(math.comb(min(cap,len(s)),n) for s in rows)
            assert total==sum(counts.values())
            checks.append({'cap':cap,'size':n,'unique':len(counts),'total':total})
    for mode in ['unsafe','fenced']:
        summary=load(f'results/{mode}/summary.json');assert summary['passed']
        assert summary['pointer_version']==(2 if mode=='unsafe' else 1)
        assert summary['pointer']['owner']==('A' if mode=='unsafe' else 'B')
        restored=summary['restored'];cp=load(restored['checkpoint_path'])
        assert digest((ROOT/restored['checkpoint_path']).read_bytes())==restored['checkpoint_sha256']
        assert cp['input_sha256']==source_hash and cp['next_batch']>0
        for owner in ['A','B']:
            for cap in [5,10,30]:assert load(f'results/{mode}/result-{owner}-{cap}.json')==independent[str(cap)]
        for cap in [5,10,30]:
            prefix=Counter()
            for s in rows[:cp['next_batch']*300]:
                for n in [1,2,3]:
                    for combo in itertools.combinations(s[:cap],n):prefix[json.dumps(combo,ensure_ascii=False,separators=(',',':'))]+=1
            assert prefix==cp['counts'][str(cap)]
        for info in summary['pointer']['files'].values():assert digest((ROOT/info['path']).read_bytes())==info['sha256']
    infra=load('results/infrastructure.json')
    assert infra['one_server_lost']['write_succeeded'] and not infra['two_servers_lost']['write_succeeded']
    assert not infra['ephemeral']['exists_after_quit']
    result={'all_passed':True,'input_sha256':source_hash,'php_population':len(rows),
            'independent_algorithm':'CSV filter and direct combinations; no original mapper imports',
            'counts':checks,'full_result_dictionaries_compared':12,
            'restored_checkpoint_counters_independently_verified':6}
    save(ROOT/'results/validation.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
