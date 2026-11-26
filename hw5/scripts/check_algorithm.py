"""Run inside the built image: python scripts/check_algorithm.py."""
import csv,io,json,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'src'))
from mapreduce import chunks,map_chunk

def aggregate(rows):
    c=Counter()
    for batch in chunks(iter(rows),100,set()):c.update(map_chunk((batch,30,True)))
    return {json.dumps(k,ensure_ascii=False,separators=(',',':')):v for k,v in c.items()}

with Path('data/vacancies.csv').open(newline='',encoding='utf-8') as f:actual=aggregate(csv.DictReader(f))
reference=json.loads(Path('reference/combined_30.json').read_text());assert actual==reference
# A duplicate id in another partition, a preceding non-Python row with same id,
# quoted multiline UTF-8 fields and repeated skill normalization.
rows=[{'id':'a','title':'Java','skills_json':'["Java"]'},
      {'id':'a','title':'Python\nDeveloper','skills_json':'[" Python ","SQL", "sql"]'},
      {'id':'a','title':'Python','skills_json':'["wrong"]'},
      {'id':'b','title':'PYTHON engineer','skills_json':'["Python", "PostgreSQL"]'}]
allrows=[row for batch in chunks(iter(rows),1,set()) for row in batch]
assert len(allrows)==2
merged=Counter()
for i in range(4):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=['id','title','skills_json']);writer.writeheader();writer.writerows(allrows[i::4]);stream.seek(0)
    merged.update(aggregate(csv.DictReader(stream)))
expected=aggregate(rows);assert dict(merged)==expected
assert expected['["python","sql"]']==1
assert not any('wrong' in k for k in merged)
print(json.dumps({'full_input_equal_hw3':True,'groups':len(actual),'multiline_csv_roundtrip':True,'global_dedup_before_split':True,'filter_before_dedup':True,'parallel_shard_sum_equal':True},indent=2))
