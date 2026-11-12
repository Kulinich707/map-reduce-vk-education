"""Two instances run this same real PHP MapReduce job; SIGSTOP pauses all threads."""
import argparse,csv,json,logging,os,time
from collections import Counter
from pathlib import Path
from kazoo.exceptions import BadVersionError
from core import ROOT,encode,digest,save,connect,commit,Receiver
import sys
sys.path.insert(0,str(ROOT/'original_hw3/src'))
# The original aggregation and filtering functions are reused without edits.
# Its optional S3 imports are installed through requirements-original.txt.
from mapreduce import batches,mapper

def emit(event,**fields):
    print(json.dumps(dict(time=time.time(),monotonic=time.monotonic(),pid=os.getpid(),
                         event=event,**fields),ensure_ascii=False),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True)
    p.add_argument('--name',required=True);p.add_argument('--delay',type=float,default=.75)
    a=p.parse_args();base='/vk-hw4/'+a.run;out=ROOT/'results'/a.run
    config=json.loads((out/'config.json').read_text())
    fencing=os.getenv('FENCING',str(int(config['fencing'])))=='1'
    if fencing!=config['fencing']:raise ValueError('FENCING conflicts with run config')
    logging.basicConfig(level=logging.WARNING)
    zk=connect();zk.add_listener(lambda state:emit('SESSION',state=state))
    emit('CONNECTED',session_id=hex(zk.client_id[0]),requested_timeout_ms=10000,
         negotiated_timeout_ms=zk._session_timeout)
    lock=zk.Lock(base+'/election',identifier=a.name)
    emit('CANDIDATE',name=a.name)
    try:
        if not lock.acquire(timeout=150):raise TimeoutError('election timeout')
        # A contender that waited for successful completion must not start another job.
        current,_=zk.get(base+'/result')
        if current!=b'{}':emit('ALREADY_COMPLETE');return
        data,stat=zk.get(base+'/epoch');epoch=int(data)+1
        tx=zk.transaction();tx.set_data(base+'/epoch',str(epoch).encode(),version=stat.version)
        epoch_version=commit(tx)[0].version
        emit('LEADER',name=a.name,epoch=epoch,epoch_version=epoch_version)
        receiver=Receiver(zk,base);cpdata,_=zk.get(base+'/checkpoint');cpp=json.loads(cpdata)
        counts={str(c):Counter() for c in (5,10,30)};start=0
        if cpp:
            raw=(ROOT/cpp['path']).read_bytes()
            if digest(raw)!=cpp['sha256']:raise ValueError('checkpoint checksum mismatch')
            cp=json.loads(raw)
            if cp['input_sha256']!=config['input_sha256']:raise ValueError('input changed')
            counts={c:Counter(v) for c,v in cp['counts'].items()};start=cp['next_batch']
        emit('RESTORED',next_batch=start,from_epoch=cpp.get('epoch'),
             checkpoint_path=cpp.get('path'),checkpoint_sha256=cpp.get('sha256'))
        with (ROOT/'data/all_sources.csv').open(newline='',encoding='utf-8') as f:
            all_batches=list(batches(csv.DictReader(f),size=300))
        assert sum(map(len,all_batches))==8661
        cp_allowed=True
        for i,batch in enumerate(all_batches):
            if i<start:continue
            for cap in (5,10,30):
                local=mapper(batch,cap,True)
                counts[str(cap)].update({json.dumps(k,ensure_ascii=False,separators=(',',':')):v for k,v in local.items()})
            cp={'next_batch':i+1,'input_sha256':config['input_sha256'],
                'counts':{c:dict(v) for c,v in counts.items()}}
            # Each leader uses its own immutable checkpoint files.
            cpfile=out/f'checkpoint-{a.name}-{i+1:03d}.json'
            if cp_allowed:
                sha=save(cpfile,cp);pointer={'path':str(cpfile.relative_to(ROOT)),
                       'sha256':sha,'epoch':epoch,'next_batch':i+1}
                try:
                    receiver.checkpoint(pointer,epoch_version)
                    emit('CHECKPOINT',next_batch=i+1,epoch=epoch,path=pointer['path'],sha256=sha)
                except BadVersionError:
                    emit('CHECKPOINT_REJECTED',error='BadVersionError',epoch=epoch)
                    cp_allowed=False
            time.sleep(a.delay) # reproducible failure window; does not alter calculations
        files={};checks={}
        for c,value in counts.items():
            result=dict(sorted(value.items()));path=out/f'result-{a.name}-{c}.json'
            sha=save(path,result);files[c]={'path':str(path.relative_to(ROOT)),'sha256':sha}
            expected=json.loads((ROOT/f'reference/combined_{c}.json').read_text())
            checks[c]={'equal_all_keys':result==expected,'unique_groups':len(result),
                       'emissions':sum(result.values()),'sha256':sha}
            if result!=expected:raise AssertionError(f'HW3 mismatch cap={c}')
        emit('VERIFIED_HW3',checks=checks)
        pointer={'owner':a.name,'epoch':epoch,'files':files,'checks':checks}
        # On session expiration Kazoo may need time to establish a new connection.
        # The captured epoch_version must NEVER be refreshed here.
        deadline=time.monotonic()+25
        while not zk.connected and time.monotonic()<deadline:time.sleep(.1)
        try:
            st=receiver.publish(pointer,epoch_version,fencing)
            emit('RESULT_WRITTEN',message='записал результат',epoch=epoch,
                 pointer_version=st.version,fencing=fencing)
        except BadVersionError:
            emit('RESULT_REJECTED',error='BadVersionError',epoch=epoch,fencing=fencing)
    finally:
        try:lock.release()
        except Exception:pass
        zk.stop();zk.close()
if __name__=='__main__':main()
