"""Executable acceptance tests; no fake ZooKeeper, elections, or failure simulation."""
import argparse,json,logging,os,signal,socket,subprocess,sys,time
from pathlib import Path
from kazoo.client import KazooClient
from core import ROOT,HOSTS,connect,encode,digest,save
COMPOSE=['docker','compose','-f',str(ROOT/'infra/compose.yaml')]
LOG=ROOT/'logs';LOG.mkdir(exist_ok=True)

def command(args,timeout=60):
    r=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    with (LOG/'commands.txt').open('a') as f:
        f.write('$ '+' '.join(args)+'\n'+r.stdout+r.stderr+'\n')
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout

def srvr(port):
    with socket.create_connection(('127.0.0.1',port),timeout=3) as s:
        s.sendall(b'srvr');s.settimeout(3);parts=[]
        while True:
            b=s.recv(65536)
            if not b:break
            parts.append(b)
    return b''.join(parts).decode()

def wait_until(fn,timeout=60):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            v=fn()
            if v:return v
        except Exception:pass
        time.sleep(.2)
    raise TimeoutError(str(fn))

def events(path):
    if not path.exists():return []
    result=[]
    for line in path.read_text().splitlines():
        try:result.append(json.loads(line))
        except ValueError:pass
    return result

def find_event(path,event,**fields):
    return next((e for e in events(path) if e['event']==event and all(e.get(k)==v for k,v in fields.items())),None)

def infrastructure():
    command(COMPOSE+['up','-d']);wait_until(lambda:all('Mode:' in srvr(p) for p in (22181,22182,22183)))
    command(COMPOSE+['exec','-T','zk1','java','-version'])
    command(COMPOSE+['exec','-T','zk1','zkServer.sh','version'])
    roles={str(p):srvr(p) for p in (22181,22182,22183)}
    assert sum('Mode: leader' in s for s in roles.values())==1
    assert sum('Mode: follower' in s for s in roles.values())==2
    for i in (1,2,3):command(COMPOSE+['exec','-T',f'zk{i}','zkServer.sh','status'])
    zk=connect();zk.ensure_path('/vk-hw4')
    command(COMPOSE+['stop','zk3']);time.sleep(3)
    zk.create('/vk-hw4/quorum-one-'+str(time.time_ns()),b'write with 2/3 servers')
    one={'write_succeeded':True,'roles':{str(p):srvr(p) for p in (22181,22182)}}
    command(COMPOSE+['stop','zk2']);time.sleep(4)
    try:
        zk.create_async('/vk-hw4/no-quorum-'+str(time.time_ns()),b'must not commit now').get(timeout=5)
        raise AssertionError('write unexpectedly succeeded without quorum')
    except Exception as exc:
        if isinstance(exc,AssertionError):raise
        two={'write_succeeded':False,'error':type(exc).__name__,'server1':srvr(22181)}
    command(COMPOSE+['start','zk2','zk3'])
    wait_until(lambda:all('Mode:' in srvr(p) for p in (22181,22182,22183)))
    wait_until(lambda:zk.connected)
    zk.create('/vk-hw4/recovered-'+str(time.time_ns()),b'ok')
    # Real zkCli process owns this ephemeral node; our separate Kazoo client observes it.
    name='/vk-hw4/ephemeral-'+str(time.time_ns());cliout=LOG/'zkcli-ephemeral.txt'
    with cliout.open('w') as f:
        cli=subprocess.Popen(COMPOSE+['exec','-T','zk2','zkCli.sh','-server','zk1:2181'],
                             stdin=subprocess.PIPE,stdout=f,stderr=subprocess.STDOUT,text=True)
        try:
            cli.stdin.write('create -e '+name+' hello\n');cli.stdin.flush()
            stat=wait_until(lambda:zk.exists(name),timeout=25)
            owner=stat.ephemeralOwner;assert owner!=0
            cli.stdin.write('get -s '+name+'\nquit\n');cli.stdin.flush()
            cli.wait(timeout=20)
            wait_until(lambda:zk.exists(name) is None,timeout=20)
        finally:
            if cli.poll() is None:cli.kill();cli.wait()
    result={'roles':roles,'one_server_lost':one,'two_servers_lost':two,
            'recovered':True,'ephemeral':{'path':name,'ephemeralOwner':hex(owner),
            'exists_before_quit':True,'exists_after_quit':False}}
    save(ROOT/'results/infrastructure.json',result);print('Infrastructure PASS',flush=True)
    zk.stop();zk.close()

def scenario(fencing):
    run='fenced' if fencing else 'unsafe';out=ROOT/'results'/run
    out.mkdir(parents=True,exist_ok=True);base='/vk-hw4/'+run;zk=connect()
    if zk.exists(base):zk.delete(base,recursive=True)
    zk.ensure_path(base)
    for n,v in [('epoch',b'0'),('checkpoint',b'{}'),('result',b'{}')]:zk.create(base+'/'+n,v)
    save(out/'config.json',{'fencing':fencing,'input_sha256':digest((ROOT/'data/all_sources.csv').read_bytes())})
    children=[];handles=[];timeline=[]
    def mark(event,**kw):
        e=dict(event=event,time=time.time(),monotonic=time.monotonic(),**kw)
        timeline.append(e);print(json.dumps(e),flush=True);return e
    def launch(name):
        f=(LOG/f'{run}-{name}.jsonl').open('w');handles.append(f)
        err=(LOG/f'{run}-{name}.stderr.txt').open('w');handles.append(err)
        p=subprocess.Popen([sys.executable,str(ROOT/'src/coordinator.py'),'--run',run,'--name',name],stdout=f,stderr=err,env={**os.environ,'FENCING':str(int(fencing))})
        children.append(p);return p
    a_path=LOG/f'{run}-A.jsonl';b_path=LOG/f'{run}-B.jsonl'
    paused=False
    try:
        a=launch('A');wait_until(lambda:find_event(a_path,'CHECKPOINT',next_batch=2),timeout=60)
        b=launch('B');wait_until(lambda:find_event(b_path,'CANDIDATE'),timeout=30)
        os.kill(a.pid,signal.SIGSTOP);paused=True;pause=mark('SIGSTOP',pid=a.pid)
        leader=wait_until(lambda:find_event(b_path,'LEADER'),timeout=35)
        mark('STANDBY_LEADER',pid=b.pid,epoch=leader['epoch'])
        restored=wait_until(lambda:find_event(b_path,'RESTORED'),timeout=15)
        assert restored['next_batch']>0
        b.wait(timeout=100);assert b.returncode==0
        assert find_event(b_path,'RESULT_WRITTEN')
        # Keep the leader suspended for at least 40 sec and until B completed.
        remaining=40-(time.monotonic()-pause['monotonic'])
        if remaining>0:time.sleep(remaining)
        os.kill(a.pid,signal.SIGCONT);paused=False;resume=mark('SIGCONT',pid=a.pid)
        a.wait(timeout=100);assert a.returncode==0
        raw,stat=zk.get(base+'/result');pointer=json.loads(raw)
        combined=events(a_path)+events(b_path)
        writes=[e for e in combined if e['event']=='RESULT_WRITTEN']
        rejects=[e for e in combined if e['event']=='RESULT_REJECTED']
        assert len(writes)==(1 if fencing else 2)
        assert stat.version==(1 if fencing else 2)
        assert len(rejects)==(1 if fencing else 0)
        assert pointer['owner']==('B' if fencing else 'A')
        assert all(v['equal_all_keys'] for e in combined if e['event']=='VERIFIED_HW3' for v in e['checks'].values())
        result={'run':run,'fencing':fencing,'failover_seconds':leader['monotonic']-pause['monotonic'],
            'pause_seconds':resume['monotonic']-pause['monotonic'],'restored':restored,
            'writes':writes,'rejections':rejects,'pointer_version':stat.version,'pointer':pointer,
            'timeline':timeline,'passed':True}
        save(out/'summary.json',result);save(out/'pointer.json',pointer)
        save(out/'timeline.json',timeline)
        # Retain all snapshots used for failover and the last snapshot of each owner.
        keep={Path(restored['checkpoint_path']).name}
        for name in ['A','B']:
            cps=sorted(out.glob('checkpoint-'+name+'-*.json'))
            if cps:keep.add(cps[-1].name)
        for f in out.glob('checkpoint-*.json'):
            if f.name not in keep:f.unlink()
        print(run+' PASS',flush=True)
    finally:
        if paused:os.kill(a.pid,signal.SIGCONT)
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        for h in handles:h.close()
        zk.stop();zk.close()

def main():
    logging.basicConfig(level=logging.ERROR)
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['all','infra','unsafe','fenced'],default='all');a=ap.parse_args()
    if a.stage in ('all','infra'):infrastructure()
    for mode in ('unsafe','fenced'):
        if a.stage in ('all',mode):scenario(mode=='fenced')
    serverlog=command(COMPOSE+['logs','--no-color'],timeout=30)
    (LOG/'servers.txt').write_text(serverlog)
    print('ALL SELECTED CHECKS PASSED',flush=True)
if __name__=='__main__':main()
