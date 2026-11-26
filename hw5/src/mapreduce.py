"""Own chunked S3 Map -> local Combine -> Reduce implementation, optionally parallel."""
import argparse, csv, io, itertools, json, math, re, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from common import ROOT, BUCKET, KEY, CAPS, client, save_json

def map_chunk(payload):
    rows, cap, combine = payload
    counts = Counter() if combine else []
    for r in rows:
        if not re.search(r'\bpython\b',r['title'],re.I): continue
        skills=sorted(set(re.sub(r'\s+',' ',s.strip().lower()) for s in json.loads(r['skills_json']) if s.strip()))[:cap]
        for k in (1,2,3):
            for combo in itertools.combinations(skills,k):
                # Optimized shuffle keys stay tuples until the final serialization.
                key=combo if combine else json.dumps(combo,ensure_ascii=False,separators=(',',':'))
                if combine: counts[key]+=1
                else: counts.append(key)
    return counts

def chunks(reader, size, seen):
    batch=[]
    for r in reader:
        if r['id'] in seen: continue
        # Filter precedes deduplication, identically to SQL row_number population.
        if not re.search(r'\bpython\b',r['title'],re.I): continue
        seen.add(r['id']); batch.append(r)
        if len(batch)>=size: yield batch; batch=[]
    if batch: yield batch

def run(cap, mode, chunk_rows=100, workers=2):
    s3=client(); body=s3.get_object(Bucket=BUCKET,Key=KEY)['Body']
    # StreamingBody + TextIOWrapper preserves quoted multiline CSV and split UTF-8.
    reader=csv.DictReader(io.TextIOWrapper(body,encoding='utf-8',newline=''))
    seen=set(); reduce=Counter()
    batches=chunks(reader,chunk_rows,seen)
    if mode=='parallel':
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for local in pool.map(map_chunk,((b,cap,True) for b in batches),chunksize=1): reduce.update(local)
    elif mode=='baseline':
        # Deliberate baseline: materialise shuffled key-value emissions before Reduce.
        emissions=[]
        for batch in batches: emissions.extend(map_chunk((batch,cap,False)))
        reduce.update(emissions)
    else:
        for batch in batches: reduce.update(map_chunk((batch,cap,True)))
    body.close()
    if mode!='baseline':
        reduce={json.dumps(k,ensure_ascii=False,separators=(',',':')):v for k,v in reduce.items()}
    return dict(sorted(reduce.items()))

def main():
    p=argparse.ArgumentParser();p.add_argument('--cap',type=int,default=30)
    p.add_argument('--mode',choices=['baseline','combined','parallel'],default='combined')
    p.add_argument('--output',default='');a=p.parse_args()
    result=run(a.cap,a.mode)
    path=ROOT/(a.output or f'results/mr_{a.mode}_{a.cap}.json')
    save_json(path,result)
    print(json.dumps({'engine':'MapReduce','mode':a.mode,'cap':a.cap,'unique_groups':len(result),
      'emissions':sum(result.values()),'input':f's3://{BUCKET}/{KEY}'},ensure_ascii=False))

if __name__=='__main__':main()
