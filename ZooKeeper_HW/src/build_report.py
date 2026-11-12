"""Build a Russian PDF from saved experimental evidence, without inventing results."""
import html,json,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,Preformatted
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from core import ROOT,digest
FONTDIR=Path('/System/Library/Fonts/Supplemental')
# On Linux install fonts-dejavu-core, or pass a directory containing these fonts.
if FONTDIR.exists(): fonts=[('Body','Arial.ttf'),('Bold','Arial Bold.ttf'),('Mono','Andale Mono.ttf')]
else:
 FONTDIR=Path('/usr/share/fonts/truetype/dejavu');fonts=[('Body','DejaVuSans.ttf'),('Bold','DejaVuSans-Bold.ttf'),('Mono','DejaVuSansMono.ttf')]
for name,file in fonts:pdfmetrics.registerFont(TTFont(name,str(FONTDIR/file)))
BLUE=colors.HexColor('#112b46');GREEN=colors.HexColor('#08755d');GRAY=colors.HexColor('#526579')
styles={
 'body':ParagraphStyle('body',fontName='Body',fontSize=10.4,leading=15,spaceAfter=8,textColor=BLUE),
 'h1':ParagraphStyle('h1',fontName='Bold',fontSize=22,leading=27,spaceAfter=16,textColor=BLUE),
 'h2':ParagraphStyle('h2',fontName='Bold',fontSize=13,leading=18,spaceAfter=9,textColor=GREEN),
 'small':ParagraphStyle('small',fontName='Body',fontSize=8.3,leading=12,spaceAfter=7,textColor=GRAY),
 'mono':ParagraphStyle('mono',fontName='Mono',fontSize=8.1,leading=11,spaceAfter=10,textColor=BLUE),
 'cover':ParagraphStyle('cover',fontName='Bold',fontSize=31,leading=38,spaceAfter=20,textColor=BLUE)}
story=[]
def p(t,style='body'):story.append(Paragraph(t,styles[style]))
def h(t):p(t,'h2')
def page(t):story.append(PageBreak());p(t,'h1')
def code(t):story.append(Preformatted(t,styles['mono']))
def table(rows,widths=None):
 data=[[Paragraph(html.escape(str(c)),styles['small']) for c in r] for r in rows]
 t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#eef3f8'),colors.white]),('LINEBELOW',(0,0),(-1,0),1,GREEN)]))
 for c in data[0]:c.style=ParagraphStyle('th',parent=styles['small'],textColor=colors.white,fontName='Bold')
 story.append(t);story.append(Spacer(1,10))
def screen(name):
 f=ROOT/f'figures/{name}.png'
 if not f.exists():raise FileNotFoundError('Browser screenshot required: '+str(f))
 from PIL import Image as PILImage
 with PILImage.open(f) as im:w,h=im.size
 ratio=min(511/w,430/h)
 story.append(Image(str(f),width=w*ratio,height=h*ratio));story.append(Spacer(1,8))
 p('Скриншот браузера: локальная страница просмотра сохранённых результатов. Это представление фактических JSON/TXT, не снимок терминала. Полные журналы приложены.','small')
def load(path):return json.loads((ROOT/path).read_text())
def main():
 inf=load('results/infrastructure.json');u=load('results/unsafe/summary.json');f=load('results/fenced/summary.json');v=load('results/validation.json')
 assert v['all_passed'] and u['passed'] and f['passed']
 p('ДОМАШНЯЯ РАБОТА № 4','h2');p('Отказоустойчивый<br/>расчёт навыков<br/>с Apache ZooKeeper','cover')
 p('Кулинич Павел Васильевич<br/>Инженерия данных 1.3<br/>Вариант 5: «Программист, разработчик на PHP»')
 p('Фактические испытания: 5 ноября 2026 года. Время в отчёте - Москва (UTC+3).','small')
 h('Результат проверки')
 table([['Критерий','Фактический результат'],['Ансамбль','ZooKeeper 3.9.6; Java 17; лидер + 2 follower'],['Отказы серверов','2/3: запись успешна; 1/3: тайм-аут, кворума нет'],['Эфемерный узел','Создан настоящим zkCli; исчез после quit'],['FENCING=0',f"2 записи; версия указателя {u['pointer_version']}; владелец A"],['FENCING=1',f"1 запись; BadVersionError; версия {f['pointer_version']}; владелец B"],['Время смены лидера',f"Без защиты {u['failover_seconds']:.3f} с; с защитой {f['failover_seconds']:.3f} с"],['Совпадение с ДЗ3','Все ключи и частоты при L=5/10/30; 12 словарей']],[141,370])
 h('Как выбрана основа ДЗ3')
 p('Переданная папка содержала Python-вариант, а приложенный PDF - PHP-вариант. Для связи ДЗ4 с PDF использован найденный локальный PHP-проект ДЗ3. Совпадают вариант, объём 8 661 вакансий, контрольные числа и SHA-256 подготовленного входа. Функции фильтрации и MapReduce скопированы без изменений.')
 p('По указанию пользователя подготовлен локальный комплект без создания репозитория, коммитов и отправки кода. Публикация на GitHub остаётся за автором сдачи.','small')
 page('1. Подготовка и ансамбль')
 p('Стенд поднят в трёх Docker-контейнерах. В официальном образе zookeeper:3.9.6 установлена OpenJDK 17.0.21. Вывод java -version, zkServer.sh version и status сохранён в logs/commands.txt. Установка Java в macOS для контейнерного варианта не требуется.')
 table([['Сервер','myid','Порт на Mac','Роль при проверке']]+[[f'zk{i}',i,22180+i,next(x.replace('Mode: ','') for x in inf['roles'][str(22180+i)].splitlines() if x.startswith('Mode:'))] for i in (1,2,3)],[100,70,110,231])
 h('Конфигурация каждого сервера')
 code((ROOT/'infra/zk1/zoo.cfg').read_text())
 p('Строки server.N одинаковы. Файлы myid содержат 1, 2 и 3. Пути /data и /datalog внутри контейнеров одинаково называются, но каждый контейнер использует отдельные Docker volumes; пересечения данных нет. Внешние клиентские порты различаются. Изоляция контейнеров позволяет использовать внутри одинаковые 2181/2888/3888.')
 h('Команды запуска и наблюдения')
 code('docker compose -f infra/compose.yaml up -d\ndocker compose -f infra/compose.yaml exec -T zk1 zkServer.sh status\ndocker compose -f infra/compose.yaml exec -T zk2 zkServer.sh status\ndocker compose -f infra/compose.yaml exec -T zk3 zkServer.sh status')
 p('Образ зафиксирован тегом 3.9.6; фактический registry digest сохранён в logs/image-digest.txt. Параметры Compose: infra/compose.yaml.','small')
 page('2. Кворум и эфемерная сессия')
 screen('infra')
 p('В начале zk3 был лидером. После его остановки zk1 и zk2 сохранили большинство и выбрали нового лидера; реальная create-операция успешно завершилась. После остановки zk2 остался один сервер: create_async не завершился за 5 с (KazooTimeoutError), srvr сообщил, что сервер не обслуживает запросы. После запуска двух серверов новая запись снова прошла.')
 p('Тайм-аут означает отсутствие подтверждённой записи в наблюдаемом интервале, а не гарантированную отмену запроса: отложенный запрос может завершиться после восстановления кворума. В тесте он имеет отдельное уникальное имя и не влияет на расчёт.','small')
 p('Отдельный процесс zkCli создал узел командой create -e. Независимая Kazoo-сессия увидела ненулевой ephemeralOwner. После команды quit этот же наблюдатель подтвердил отсутствие узла. Вывод create/get -s/quit: logs/zkcli-ephemeral.txt; наблюдения: results/infrastructure.json.')
 page('3. Координатор и чекпоинт')
 h('Путь данных и координации')
 code('all_sources.csv -> batches(300) -> mapper(L=5/10/30)\n                -> Counter -> snapshot JSON + SHA-256\nZooKeeper: /vk-hw4/<run>/\n  election/     ephemeral sequential кандидаты Kazoo Lock\n  epoch         монотонная эпоха; CAS-версия для fencing\n  checkpoint    путь + SHA-256 + next_batch + epoch\n  result        опубликованный указатель на результаты')
 p('Две копии запускают одинаковую программу. Kazoo Lock следит за предшественником в очереди кандидатов. Победитель увеличивает epoch условной записью и запоминает версию znode. Запасной получает лидерство после истечения сессии остановленного процесса. Запрошенный и фактически согласованный тайм-аут равен 10 000 мс; это записано в событии CONNECTED.')
 p('Чекпоинт содержит next_batch, хеш входа и все три накопленных счётчика. Большие данные сохраняются в общей папке, а в ZooKeeper записывается маленький указатель. Файл записывается через временный файл, fsync и os.replace. Контрольная сумма проверяется перед восстановлением. Каждая копия имеет собственные имена файлов; публикация чекпоинта защищена атомарной проверкой эпохи.')
 table([['Сценарий','Восстановлен next_batch','Вакансий уже учтено','Эпоха снимка']]+[[s['run'],s['restored']['next_batch'],min(8661,s['restored']['next_batch']*300),s['restored']['from_epoch']] for s in (u,f)],[100,150,150,111])
 p('Новый лидер повторно читает детерминированный вход, пропускает уже посчитанные чанки и продолжает со следующего. Независимый верификатор пересчитал префикс данных и проверил все шесть восстановленных счётчиков. Поэтому доказано восстановление накопленных частот, а не только чтение номера чанка.')
 p('Функции batches и mapper из original_hw3/src/mapreduce.py не изменены. Вместо повторного скачивания из S3 используется идентичный подготовленный all_sources.csv; SHA-256 совпадает с ДЗ3. Задержка 0.75 с после чанка нужна только для наблюдения отказа.','small')
 page('4. Остановка лидера без защиты')
 screen('unsafe')
 p(f"Координатор A остановлен SIGSTOP после сохранения чекпоинта. Через {u['failover_seconds']:.3f} с B записал событие LEADER с эпохой 2. Он восстановился с next_batch={u['restored']['next_batch']}, завершил расчёт и опубликовал результат. A оставался остановленным {u['pause_seconds']:.3f} с, до окончания работы B, после чего получил SIGCONT.")
 p('Старая копия A продолжила свой расчёт с захваченной эпохой 1. Её устаревшие чекпоинты отклонены, но защита публикации в этом режиме выключена. Поэтому результат записан второй раз: сначала B (версия указателя 1), затем A (версия 2). В журналах есть ровно два события RESULT_WRITTEN с текстом «записал результат».')
 p('Итоговый указатель принадлежит A, epoch=1, dataVersion=2. Это демонстрирует риск старого лидера даже при численно одинаковых результатах. Источники: logs/unsafe-A.jsonl, unsafe-B.jsonl; results/unsafe/summary.json.','small')
 page('5. Остановка лидера с FENCING=1')
 screen('fenced')
 p(f"Повторён тот же сценарий с проверкой эпохи у получателя. Время от SIGSTOP до LEADER резервной копии: {f['failover_seconds']:.3f} с. Пауза A: {f['pause_seconds']:.3f} с. B восстановился с next_batch={f['restored']['next_batch']}, получил epoch=2 и опубликовал результат.")
 p('После SIGCONT A сохранил свою исходную эпоху и версию. Получатель попытался атомарно проверить эту версию и обновить указатель; проверка завершилась BadVersionError. Запись отклонена, в журнале A есть RESULT_REJECTED, а RESULT_WRITTEN только один - у B. Итоговый указатель сохранил owner=B, epoch=2, dataVersion=1.')
 p('Первичная проверка выявила гонку SessionExpiredError при переподключении старой копии. Добавлено ограниченное повторение транзакции после восстановления сессии без обновления старой эпохи. Итоговые испытания проведены повторно на исправленном коде. Исходная диагностика сохранена в logs/diagnostics/.','small')
 page('6. Совпадение с результатами ДЗ3')
 p('В обоих сценариях обе копии завершили арифметический расчёт. Сравнение выполнено по всем ключам и частотам: 2 сценария × 2 копии × 3 размера стека = 12 полных словарей. Эталоны ДЗ3 дополнительно проверены независимым прямым перебором сочетаний, без импорта исходного mapper.')
 table([['L','Размер сочетания','Уникальных','Сумма частот']]+[[r['cap'],r['size'],f"{r['unique']:,}".replace(',',' '),f"{r['total']:,}".replace(',',' ')] for r in v['counts']],[50,150,150,161])
 p('Все девять сумм независимо совпали с Σ C(min(m,L),k), где m - число нормализованных навыков вакансии, k=1,2,3. На полном стеке: 33 821 уникальная пара, 285 780 вхождений пар; mysql + php = 3 522, git + php = 2 819, javascript + php = 2 622.')
 h('Контрольные суммы')
 p('Подготовленный вход ДЗ3:','small');code(v['input_sha256'])
 for cap in (5,10,30):
  p(f'Канонический результат L={cap}, одинаковый у всех четырёх вычислителей:','small');code(u['pointer']['files'][str(cap)]['sha256'])
 p('Хеши в отчёте относятся к каноническому JSON: UTF-8, sort_keys=True, без лишних пробелов. Файлы reference/ сохранены в прежнем формате, поэтому их байтовые хеши могут отличаться при равенстве всех данных. Подробная независимая проверка: results/validation.json и logs/validation.txt.','small')
 page('7. Ответы на вопросы')
 h('Почему три сервера, а не два и не четыре?')
 p('Запись должна быть подтверждена строгим большинством. Для N участников кворум равен floor(N/2)+1. Два сервера требуют оба голоса: отказ одного лишает систему кворума. Три требуют два голоса и переживают отказ одного. Четыре требуют три голоса, поэтому тоже переживают только один отказ, но расходуют больше ресурсов. Три - минимальное число для устойчивости к одному отказу; для двух отказов нужны пять. Пересечение любых двух большинств не позволяет независимым меньшинствам подтвердить несовместимые истории.')
 table([['Серверов','Кворум','Допустимо отказов'],[2,2,0],[3,2,1],[4,3,1],[5,3,2]],[170,170,171])
 h('Почему эпоху проверяет получатель записи, а не ZooKeeper?')
 p('ZooKeeper видит сессии, znodes и их версии, но не знает смысла сторонней записи: например, обновления файла, строки БД или отправки платежа. Приостановленный процесс не узнаёт вовремя о потере лидерства и может уже держать подготовленный запрос. Удаление его эфемерного узла само по себе не отменяет такой запрос. Получатель ресурса должен сравнить токен с актуальной эпохой непосредственно в момент применения записи.')
 p('В этом стенде получатель Receiver использует ZooKeeper как хранилище указателя, поэтому реализует проверку средствами версии znode и multi. Политика «проверять epoch» находится в коде получателя; ZooKeeper обеспечивает только атомарность и CAS. При переносе результата во внешнюю БД проверку нужно выполнять в транзакции этой БД. Отдельная проверка в ZooKeeper, а затем запись в БД оставила бы окно гонки.')
 code('tx = zk.transaction()\nif fencing:\n    tx.check(base + "/epoch", version=captured_epoch_version)\ntx.set_data(base + "/result", pointer, version=-1)\n# Один atomic commit; устаревшая эпоха -> BadVersionError.')
 p('Непринятый файл старого вычислителя может существовать как артефакт, но не становится опубликованным результатом: единственная точка публикации - защищённый указатель /result.','small')
 page('8. Воспроизведение и состав сдачи')
 code('python3 -m venv .venv\n.venv/bin/pip install -r requirements.txt\ndocker compose -f infra/compose.yaml up -d\n.venv/bin/python src/run_lab.py > logs/acceptance.txt 2>&1\n.venv/bin/python src/verify_submission.py > logs/validation.txt\n# Остановить стенд, сохранив тома:\ndocker compose -f infra/compose.yaml stop')
 table([['Что проверять','Где находятся доказательства'],['Роли, Java, версия, команды','logs/commands.txt; results/infrastructure.json'],['Эфемерная сессия','logs/zkcli-ephemeral.txt'],['Остановка и смена лидера','results/{unsafe,fenced}/timeline.json и summary.json'],['Две записи / отказ по эпохе','logs/{unsafe,fenced}-{A,B}.jsonl'],['Серверные журналы','logs/servers.txt'],['Совпадение с ДЗ3','reference/; results/*/result-*.json'],['Чекпоинты восстановления','results/*/checkpoint-*.json'],['Независимая проверка','src/verify_submission.py; results/validation.json'],['Конфигурации','infra/compose.yaml; infra/zk1..3/{zoo.cfg,myid}'],['Скриншоты и исходные страницы','figures/*.png; report/evidence-*.html'],['Целостность комплекта','SHA256SUMS.txt; проверка ZIP CRC']],[170,341])
 h('Границы эксперимента')
 p('Это учебный стенд на одном Mac: три контейнера и общая папка не защищают от отказа самого компьютера. Остановка процессов, потеря сессии, смена лидера и проверка публикации были реальными. Старый процесс намеренно продолжает вычисления после потери сессии для демонстрации fencing. В рабочей системе дополнительно прекращают вычисления после LOST. Задержка искусственно растягивает расчёт, поэтому это измерение failover, а не производительности MapReduce. Оценка выставляется преподавателем; публикация в GitHub по просьбе пользователя не выполнялась.')
 h('Документация')
 p('Apache ZooKeeper 3.9.6: <link href="https://zookeeper.apache.org/doc/r3.9.6/zookeeperProgrammers.html" color="#08755d">Programmer’s Guide</link> (сессии, ephemeral, версии); <link href="https://zookeeper.apache.org/doc/r3.9.6/zookeeperAdmin.html" color="#08755d">Administrator’s Guide</link> (ансамбль, кворум). Kazoo: <link href="https://kazoo.readthedocs.io/en/latest/api/recipe/lock.html" color="#08755d">Lock recipe</link>. Использованная версия клиента 2.10.0 зафиксирована в requirements.txt.','small')
 out=ROOT/'report/Report_ZooKeeper_HW4.pdf'
 def footer(c,doc):
  c.setStrokeColor(colors.HexColor('#d5dfe9'));c.line(42,39,553,39)
  c.setFont('Body',8);c.setFillColor(GRAY);c.drawString(42,26,'ДЗ4 · Apache ZooKeeper · Кулинич П. В.');c.drawRightString(553,26,str(doc.page))
 doc=SimpleDocTemplate(str(out),pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=39,bottomMargin=50,title='ДЗ4. Apache ZooKeeper - отказоустойчивый расчёт',author='Кулинич Павел Васильевич')
 doc.build(story,onFirstPage=footer,onLaterPages=footer);print(out)
if __name__=='__main__':main()
