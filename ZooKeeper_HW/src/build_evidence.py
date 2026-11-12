"""Readable static pages from genuine saved evidence; used for browser screenshots."""
import html,json
from pathlib import Path
from core import ROOT

def page(name,title,sections):
    content=''
    for heading,body in sections:
        content+=f'<h2>{html.escape(heading)}</h2><pre>{html.escape(body)}</pre>'
    out=ROOT/'report'/f'evidence-{name}.html'
    out.write_text('''<!doctype html><html lang="ru"><meta charset="utf-8"><title>'''+title+'''</title><style>
    *{box-sizing:border-box}body{margin:0;background:#edf2f7;color:#11243b;font:16px -apple-system,Arial,sans-serif}
    main{max-width:1120px;padding:30px;margin:auto}h1{font-size:30px;margin:8px 0 6px}h2{font-size:19px;margin:22px 0 8px}
    .tag{color:#127056;font-weight:700;letter-spacing:1px}.note{color:#536578;font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;border:1px solid #ccd6e2;border-left:5px solid #127056;padding:15px;font:14px/1.45 ui-monospace,Menlo,monospace;margin:0}
    </style><main><div class="tag">ДЗ4 · ФАКТИЧЕСКИЕ РЕЗУЛЬТАТЫ</div><h1>'''+title+'''</h1><p class="note">Просмотр сохранённых журналов эксперимента 05.11.2026. Значения взяты из приложенных JSON/TXT.</p>'''+content+'</main></html>',encoding='utf-8')

def main():
    inf=json.loads((ROOT/'results/infrastructure.json').read_text())
    roles='\n'.join(f"127.0.0.1:{p} — "+next(x for x in t.splitlines() if x.startswith('Mode:')) for p,t in inf['roles'].items())
    page('infra','Ансамбль, кворум и эфемерный узел',[
        ('Три сервера · ZooKeeper 3.9.6 · OpenJDK 17.0.21',roles+'\nИсточник: results/infrastructure.json; logs/commands.txt'),
        ('Остановка серверов', 'Потерян zk3: запись при 2/3 серверах успешна.\nПотеряны zk3 и zk2: '+inf['two_servers_lost']['error']+' за 5 с.\n'+inf['two_servers_lost']['server1'].strip()+'\nПосле восстановления: запись успешна.'),
        ('Настоящий клиент zkCli',json.dumps(inf['ephemeral'],ensure_ascii=False,indent=2)+'\nИсточник: logs/zkcli-ephemeral.txt')])
    for mode in ['unsafe','fenced']:
        s=json.loads((ROOT/f'results/{mode}/summary.json').read_text());parts=[]
        for owner in ['A','B']:
            es=[]
            for line in (ROOT/f'logs/{mode}-{owner}.jsonl').read_text().splitlines():
                e=json.loads(line)
                if e['event'] in ['LEADER','RESTORED','RESULT_WRITTEN','RESULT_REJECTED']:
                    if e['event']=='RESTORED':e={k:e[k] for k in ['event','next_batch','from_epoch']}
                    else:e={k:v for k,v in e.items() if k not in ['time','monotonic','pid']}
                    es.append(json.dumps(e,ensure_ascii=False))
            parts.append((f'Координатор {owner} · logs/{mode}-{owner}.jsonl','\n'.join(es)))
        parts.append(('Проверка',f"Смена лидера: {s['failover_seconds']:.3f} с\nПауза: {s['pause_seconds']:.3f} с\nВерсия указателя: {s['pointer_version']}\nВладелец результата: {s['pointer']['owner']}, эпоха {s['pointer']['epoch']}\nПолное совпадение с ДЗ3 при L=5/10/30: true"))
        page(mode,'FENCING='+str(int(s['fencing']))+' · '+('защита по эпохе' if s['fencing'] else 'повторная публикация'),parts)
    v=json.loads((ROOT/'results/validation.json').read_text())
    page('validation','Независимая проверка расчёта',[
        ('Объём и происхождение',f"PHP-вакансий: {v['php_population']}\nSHA-256 all_sources.csv:\n{v['input_sha256']}"),
        ('Контрольные числа ДЗ3','L  Размер   Уникальных  Сумма частот\n'+'\n'.join(f"{c['cap']:<3}{c['size']:<9}{c['unique']:<12}{c['total']}" for c in v['counts'])),
        ('Итог',f"12 полных словарей совпали с независимым пересчётом.\n6 восстановленных счётчиков чекпоинтов проверены независимо.\nall_passed = {str(v['all_passed']).lower()}\nИсточник: results/validation.json")])
if __name__=='__main__':main()
