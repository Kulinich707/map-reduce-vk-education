#!/usr/bin/env python3
"""Reproduce lab in a dedicated kind cluster; never touches Git or other clusters."""
import argparse,json,math,os,secrets,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'logs'; MAN=ROOT/'k8s'; RES=ROOT/'results'
for p in (LOG,MAN,RES):p.mkdir(exist_ok=True)
a=argparse.ArgumentParser();a.add_argument('--kubeconfig',required=True);a.add_argument('--kind',default='kind');a.add_argument('--skip-build',action='store_true');a.add_argument('--resume-scheduling',action='store_true');opt=a.parse_args()
K=['kubectl','--kubeconfig',str(Path(opt.kubeconfig).resolve()),'--cache-dir',str(ROOT/'.kubectl-cache')]

def command(args,filename=None,check=True):
    p=subprocess.run(args,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if filename:(LOG/filename).write_text(p.stdout if filename.endswith('.json') else '$ '+' '.join(args)+'\n'+p.stdout)
    if check and p.returncode: raise RuntimeError(p.stdout)
    return p

def kub(args,filename=None,check=True):return command(K+args,filename,check)
def js(args):return json.loads(kub(args+['-o','json']).stdout)
def apply(name,obj):
    f=MAN/(name+'.yaml'); f.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');kub(['apply','-f',str(f)],name+'-apply.txt')
def snapshot(name,namespace='hw4'):
    for kind in ['pods','jobs','events']:
        kub(['get',kind,'-n',namespace,'-o','json'],name+'-'+kind+'.json')
    kub(['describe','pods','-n',namespace],name+'-describe.txt')
def wait_pod(name,predicate,timeout=180,namespace='hw4'):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        pod=js(['get','pod',name,'-n',namespace])
        if predicate(pod):return pod
        time.sleep(2)
    raise RuntimeError('Timeout waiting for '+name)
def job(name,mode,mem='512Mi',run=None,**extra):
    container={'name':'worker','image':'hw4-skills:1.0','imagePullPolicy':'Never','args':[mode,'--run',run or name],
      'resources':{'requests':{'cpu':'250m','memory':minmem(mem)},'limits':{'cpu':'1000m','memory':mem}},
      'env':[{'name':'S3_ENDPOINT','value':'http://rustfs:9000'},{'name':'S3_ACCESS_KEY','valueFrom':{'secretKeyRef':{'name':'s3-auth','key':'access'}}},{'name':'S3_SECRET_KEY','valueFrom':{'secretKeyRef':{'name':'s3-auth','key':'secret'}}}]}
    obj={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'hw4'},'spec':{'backoffLimit':0,'activeDeadlineSeconds':300,'template':{'spec':{'restartPolicy':'Never','containers':[container]}}}}
    obj['spec'].update(extra);apply(name,obj)
    start=time.monotonic()
    while time.monotonic()-start<360:
        pods=js(['get','pods','-n','hw4','-l','job-name='+name])['items']
        status=js(['get','job',name,'-n','hw4'])['status']
        if any(c.get('status')=='True' and c['type'] in ('Complete','Failed') for c in status.get('conditions',[])):break
        time.sleep(2)
    else:raise RuntimeError('Job timeout '+name)
    pods=js(['get','pods','-n','hw4','-l','job-name='+name])['items']
    for pod in pods:kub(['logs','-n','hw4',pod['metadata']['name']],name+'-'+pod['metadata']['name']+'.log',False)
    snapshot(name)
    return status,pods

def minmem(mem):return str(min(128,int(mem[:-2])))+'Mi'
def sleeper(name,cpu,priority=None,ns='hw4',preempt=None):
    spec={'restartPolicy':'Never','terminationGracePeriodSeconds':0,'containers':[{'name':'sleep','image':'hw4-skills:1.0','imagePullPolicy':'Never','command':['python','-c','import time; time.sleep(600)'],'resources':{'requests':{'cpu':cpu,'memory':'64Mi'},'limits':{'cpu':cpu,'memory':'64Mi'}}}]}
    if priority:spec['priorityClassName']=priority
    if preempt:spec['preemptionPolicy']=preempt
    apply(name,{'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':ns},'spec':spec})

# Refuse to operate against an arbitrary existing cluster.
context=kub(['config','current-context']).stdout.strip()
assert context=='kind-hw4-skills',f'Expected kind-hw4-skills, got {context}'
if not opt.resume_scheduling:
    kub(['version','-o','json'],'environment-kubernetes.json');kub(['get','nodes','-o','json'],'environment-nodes.json')
    command(['docker','info','--format','Server={{.ServerVersion}} CPU={{.NCPU}} Memory={{.MemTotal}}'],'environment-docker.txt')
    if not opt.skip_build:command(['docker','build','-t','hw4-skills:1.0','.'],'build.log')
    # Import only the host platform: Docker's local multi-platform index can reference
    # unavailable foreign manifests; kind --all-platforms import would then fail.
    node_info=js(['get','nodes'])['items'][0]
    node_name=node_info['metadata']['name']; arch=node_info['status']['nodeInfo']['architecture']
    save=subprocess.Popen(['docker','save','hw4-skills:1.0','rustfs/rustfs:latest'],stdout=subprocess.PIPE)
    load=subprocess.run(['docker','exec','--privileged','-i',node_name,'ctr','--namespace=k8s.io','images','import','--platform','linux/'+arch,'--digests','-'],stdin=save.stdout,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    save.stdout.close(); save_rc=save.wait(); (LOG/'load-images.txt').write_text(load.stdout)
    assert load.returncode==0 and save_rc==0, load.stdout
    apply('namespace',{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'hw4'}})
    # Fresh random lab credentials, generated each run; their values are not logged or packaged.
    creds={'apiVersion':'v1','kind':'Secret','metadata':{'name':'s3-auth','namespace':'hw4'},'stringData':{'access':'labadmin','secret':secrets.token_urlsafe(24)}}
    subprocess.run(K+['apply','-f','-'],input=json.dumps(creds),text=True,check=True,stdout=subprocess.DEVNULL)
    vol=[{'name':f'disk{i}','mountPath':f'/data{i}'} for i in range(1,9)]
    apply('rustfs',{'apiVersion':'apps/v1','kind':'StatefulSet','metadata':{'name':'rustfs','namespace':'hw4'},'spec':{'serviceName':'rustfs','replicas':1,'selector':{'matchLabels':{'app':'rustfs'}},'template':{'metadata':{'labels':{'app':'rustfs'}},'spec':{'securityContext':{'fsGroup':10001},'containers':[{'name':'rustfs','image':'rustfs/rustfs:latest','imagePullPolicy':'Never','args':['/data{1...8}'],'ports':[{'containerPort':9000}], 'env':[{'name':'RUSTFS_ACCESS_KEY','valueFrom':{'secretKeyRef':{'name':'s3-auth','key':'access'}}},{'name':'RUSTFS_SECRET_KEY','valueFrom':{'secretKeyRef':{'name':'s3-auth','key':'secret'}}}]+[{'name':k,'value':v} for k,v in {'RUSTFS_ADDRESS':':9000','RUSTFS_CONSOLE_ENABLE':'false','RUSTFS_STORAGE_CLASS_STANDARD':'EC:4','RUSTFS_ERASURE_SET_DRIVE_COUNT':'8','RUSTFS_UNSAFE_BYPASS_DISK_CHECK':'true'}.items()], 'resources':{'requests':{'cpu':'250m','memory':'256Mi'},'limits':{'cpu':'1000m','memory':'1Gi'}},'volumeMounts':vol,'readinessProbe':{'httpGet':{'path':'/health','port':9000},'initialDelaySeconds':5,'periodSeconds':3}}]}},'volumeClaimTemplates':[{'metadata':{'name':f'disk{i}'},'spec':{'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'256Mi'}}}} for i in range(1,9)]}})
    apply('service',{'apiVersion':'v1','kind':'Service','metadata':{'name':'rustfs','namespace':'hw4'},'spec':{'selector':{'app':'rustfs'},'ports':[{'port':9000,'targetPort':9000}]}})
    kub(['rollout','status','statefulset/rustfs','-n','hw4','--timeout=180s'],'rustfs-ready.txt')
    kub(['logs','rustfs-0','-n','hw4'],'rustfs-runtime.log')
    kub(['get','pvc','-n','hw4','-o','json'],'rustfs-pvc.json')
    kub(['get','service','rustfs','-n','hw4','-o','json'],'rustfs-service.json')
    status,_=job('bootstrap','bootstrap');assert status.get('succeeded')==1
    status,pods=job('profile','single');assert status.get('succeeded')==1
    profilelog=(LOG/('profile-'+pods[0]['metadata']['name']+'.log')).read_text().splitlines()[-1];m=json.loads(profilelog)
    peak=m['cgroup_peak_bytes']; tuned=math.ceil(peak/1048576*1.3/16)*16;low=max(32,math.floor(peak/1048576*.5/8)*8)
    (RES/'memory-sizing.json').write_text(json.dumps({'measured':m,'low_limit_mib':low,'tuned_limit_mib':tuned,'formula':'ceil(cgroup_peak_MiB * 1.30 / 16) * 16'},indent=2))
    status,pods=job('oom','single',f'{low}Mi');assert status.get('failed')==1
    terminated=pods[0]['status']['containerStatuses'][0]['state']['terminated'];assert terminated['reason']=='OOMKilled',terminated
    status,_=job('tuned','single',f'{tuned}Mi');assert status.get('succeeded')==1
    status,_=job('parallel','map',f'{tuned}Mi',completions=4,parallelism=4,completionMode='Indexed');assert status.get('succeeded')==4
    status,_=job('reduce','reduce',f'{max(tuned,256)}Mi');assert status.get('succeeded')==1
else:
    saved=json.loads((LOG/'oom-pods.json').read_text())['items']
    terminated=next(p for p in saved if p['metadata']['labels'].get('job-name')=='oom')['status']['containerStatuses'][0]['state']['terminated']
# Capacity experiment: requests, rather than actual idle CPU usage, govern scheduling.
node=js(['get','nodes'])['items'][0]; alloc=node['status']['allocatable']['cpu']; milli=int(alloc[:-1]) if alloc.endswith('m') else int(alloc)*1000
cpu=f'{milli-2000}m'
for name,value in [('hw4-low',10),('hw4-high',1000),('hw4-wait',10)]:apply(name,{'apiVersion':'scheduling.k8s.io/v1','kind':'PriorityClass','metadata':{'name':name},'value':value,'globalDefault':False,'preemptionPolicy':'Never' if name=='hw4-wait' else 'PreemptLowerPriority'})
sleeper('low',cpu,'hw4-low');victim=wait_pod('low',lambda p:p['status']['phase']=='Running');victim_uid=victim['metadata']['uid']
sleeper('cpu-wait',cpu,'hw4-wait')
wait_pod('cpu-wait',lambda p:any(c.get('reason')=='Unschedulable' and 'Insufficient cpu' in c.get('message','') for c in p['status'].get('conditions',[])))
snapshot('cpu-pending');kub(['delete','pod','cpu-wait','-n','hw4','--wait=true'],'delete-waiter.txt')
sleeper('high',cpu,'hw4-high');wait_pod('high',lambda p:p['status']['phase']=='Running');snapshot('preemption')
preemption_events=js(['get','events','-n','hw4']);assert any(e.get('reason')=='Preempted' and e.get('involvedObject',{}).get('uid')==victim_uid for e in preemption_events['items']),preemption_events
(RES/'scheduling.json').write_text(json.dumps({'allocatable_cpu':alloc,'pod_request':cpu,'victim_uid':victim_uid,'high_running':True,'preempted_event_verified':True},indent=2))
kub(['delete','pod','high','-n','hw4','--wait=true'],'delete-high.txt')
apply('quota-namespace',{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'hw4-quota'}})
apply('quota',{'apiVersion':'v1','kind':'ResourceQuota','metadata':{'name':'lab-quota','namespace':'hw4-quota'},'spec':{'hard':{'requests.cpu':'200m','requests.memory':'128Mi','limits.cpu':'200m','limits.memory':'128Mi','pods':'1'}}})
sleeper('quota-first','150m',ns='hw4-quota');wait_pod('quota-first',lambda p:p['status']['phase']=='Running',namespace='hw4-quota')
first=json.loads((MAN/'quota-first.yaml').read_text());first['metadata']['name']='quota-rejected';f=MAN/'quota-rejected.yaml';f.write_text(json.dumps(first,indent=2))
rejected=kub(['apply','-f',str(f)],'quota-rejection.txt',False);assert rejected.returncode!=0 and 'exceeded quota' in rejected.stdout
kub(['describe','resourcequota','-n','hw4-quota'],'quota-describe.txt');snapshot('quota','hw4-quota')
kub(['delete','pod','quota-first','-n','hw4-quota','--wait=true'],'quota-release.txt');kub(['apply','-f',str(f)],'quota-after-release.txt');wait_pod('quota-rejected',lambda p:p['status']['phase']=='Running',namespace='hw4-quota');snapshot('quota-recovered','hw4-quota')
kub(['delete','pod','quota-rejected','-n','hw4-quota'],'quota-cleanup.txt')
# Export actual S3 results without exposing S3 outside the cluster.
status,pods=job('export','export','512Mi');assert status.get('succeeded')==1
for line in (LOG/('export-'+pods[0]['metadata']['name']+'.log')).read_text().splitlines()[1:]:
    obj=json.loads(line)
    if 'key' in obj:
        path=RES/obj['key'];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj['value'],ensure_ascii=False,indent=2))
    elif 'inventory' in obj:(RES/'s3-inventory.json').write_text(json.dumps(obj,indent=2))
(RES/'experiment-status.json').write_text(json.dumps({'oom_reason':terminated,'cpu_pending_verified':True,'preemption_verified':True,'quota_rejection_verified':True,'quota_recovery_verified':True,'completed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2))
print('All experiments passed. Evidence saved in logs/ and results/.')
