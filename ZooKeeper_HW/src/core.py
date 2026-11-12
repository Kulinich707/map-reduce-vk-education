"""Shared data format, checkpoint integrity, and atomic receiver publication."""
import hashlib,json,os,time
from pathlib import Path
from kazoo.client import KazooClient
from kazoo.exceptions import BadVersionError,SessionExpiredError
ROOT=Path(__file__).resolve().parents[1]
HOSTS=os.getenv('ZK_HOSTS','127.0.0.1:22181,127.0.0.1:22182,127.0.0.1:22183')

def encode(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def digest(data):return hashlib.sha256(data).hexdigest()

def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=encode(obj);tmp=path.with_suffix(path.suffix+f'.{os.getpid()}.tmp')
    with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    return digest(data)

def connect():
    zk=KazooClient(hosts=HOSTS,timeout=10.0);zk.start(timeout=20)
    return zk

def commit(tx):
    results=tx.commit()
    for r in results:
        if isinstance(r,BadVersionError):raise r
    for r in results:
        if isinstance(r,Exception):raise r
    return results

class Receiver:
    """The recipient enforces an epoch, using ZooKeeper multi as atomic CAS storage.

    Bulk immutable data is in a shared directory, only small pointers are in ZK.
    The epoch check and pointer update are one transaction, with no check/write gap.
    """
    def __init__(self,zk,base):self.zk,self.base=zk,base
    def _execute(self,build):
        # A request racing the old session's expiration can fail before the
        # replacement session is ready. Rebuild the transaction but retain the
        # original fencing version. Never obtain a fresh epoch here.
        for attempt in range(4):
            try:return commit(build())
            except SessionExpiredError:
                if attempt==3:raise
                deadline=time.monotonic()+25
                while not self.zk.connected and time.monotonic()<deadline:
                    time.sleep(.1)
                time.sleep(.1)
        raise RuntimeError('session recovery failed')
    def publish(self,pointer,epoch_version,fencing):
        def build():
            tx=self.zk.transaction()
            if fencing:tx.check(self.base+'/epoch',version=epoch_version)
            tx.set_data(self.base+'/result',encode(pointer),version=-1)
            return tx
        return self._execute(build)[-1]
    def checkpoint(self,pointer,epoch_version):
        def build():
            tx=self.zk.transaction();tx.check(self.base+'/epoch',version=epoch_version)
            tx.set_data(self.base+'/checkpoint',encode(pointer),version=-1)
            return tx
        self._execute(build)
