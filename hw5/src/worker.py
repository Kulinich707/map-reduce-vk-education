"""S3 -> original HW3 Map/Combine -> S3; globally deduplicated record shards."""
import argparse,csv,io,json,os,resource,time,hashlib,math
from collections import Counter
from pathlib import Path
from common import client,BUCKET
from mapreduce import chunks,map_chunk

def put(key,obj):
    data=json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()
    client().put_object(Bucket=BUCKET,Key=key,Body=data)
    return hashlib.sha256(data).hexdigest()

def get(key):
    return json.loads(client().get_object(Bucket=BUCKET,Key=key)['Body'].read())

def count(key):
    body=client().get_object(Bucket=BUCKET,Key=key)['Body']
    c=Counter(); seen=set()
    with io.TextIOWrapper(body,encoding='utf-8',newline='') as stream:
        for batch in chunks(csv.DictReader(stream),100,seen): c.update(map_chunk((batch,30,True)))
    return {json.dumps(k,ensure_ascii=False,separators=(',',':')):v for k,v in c.items()}

def metrics(start):
    peak=Path('/sys/fs/cgroup/memory.peak')
    return {'elapsed_seconds':time.monotonic()-start,'rss_peak_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'cgroup_peak_bytes':int(peak.read_text()) if peak.exists() else None}

def main():
    a=argparse.ArgumentParser(); a.add_argument('mode',choices=['bootstrap','single','map','reduce','export']);a.add_argument('--run',default='single');x=a.parse_args();start=time.monotonic()
    if x.mode=='bootstrap':
        s=client()
        if BUCKET not in [b['Name'] for b in s.list_buckets()['Buckets']]: s.create_bucket(Bucket=BUCKET)
        source=Path('data/vacancies.csv'); s.upload_file(str(source),BUCKET,'input/vacancies.csv')
        body=s.get_object(Bucket=BUCKET,Key='input/vacancies.csv')['Body'].read()
        assert hashlib.sha256(body).digest()==hashlib.sha256(source.read_bytes()).digest()
        streams=[io.StringIO(newline='') for _ in range(4)]
        with source.open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f); writers=[csv.DictWriter(t,fieldnames=reader.fieldnames) for t in streams]
            for w in writers:w.writeheader()
            seen=set();n=0
            for batch in chunks(reader,100,seen):
                for row in batch: writers[n%4].writerow(row);n+=1
        for i,t in enumerate(streams): s.put_object(Bucket=BUCKET,Key=f'shards/{i}.csv',Body=t.getvalue().encode())
        print(json.dumps({'uploaded_sha256':hashlib.sha256(body).hexdigest(),'unique_python_rows':n,'shards':4}))
    elif x.mode in ('single','map'):
        idx=os.environ.get('JOB_COMPLETION_INDEX','0');key='input/vacancies.csv' if x.mode=='single' else f'shards/{idx}.csv'
        print(json.dumps({'started':x.mode,'input':key,'index':idx}),flush=True)
        counts=count(key);out=f'results/{x.run}.json' if x.mode=='single' else f'partials/{idx}.json'
        put(out,counts);m=metrics(start);put(f'metrics/{x.run}-{idx}.json',m);print(json.dumps({'output':out,'groups':len(counts),**m}))
    elif x.mode=='reduce':
        c=Counter()
        for i in range(4):c.update(get(f'partials/{i}.json'))
        serial=get('results/tuned.json');ref=json.loads(Path('reference/combined_30.json').read_text())
        pairs=sorted([(k,v) for k,v in c.items() if len(json.loads(k))==2],key=lambda kv:(-kv[1],kv[0]))[:10]
        result={'all_groups_equal_hw3':dict(c)==ref,'serial_equal_hw3':serial==ref,'parallel_equal_serial':dict(c)==serial,'groups':len(c),'top10_pairs':pairs,**metrics(start)}
        put('results/parallel.json',dict(c));put('results/verification.json',result);print(json.dumps(result,ensure_ascii=False))
        assert all(result[k] for k in ['all_groups_equal_hw3','serial_equal_hw3','parallel_equal_serial'])
    else:
        s=client();inventory=[]
        for page in s.get_paginator('list_objects_v2').paginate(Bucket=BUCKET):
            for o in page.get('Contents',[]):
                key=o['Key'];inventory.append({'key':key,'bytes':o['Size']})
                if key.startswith(('results/','metrics/')): print(json.dumps({'key':key,'value':get(key)},ensure_ascii=False))
        print(json.dumps({'inventory':inventory}))
if __name__=='__main__':main()
