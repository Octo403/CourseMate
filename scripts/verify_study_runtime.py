"""Exercise personal marks and real ChatGPT using an isolated public-course copy."""
import argparse
import json
import shutil
import sqlite3
import threading
import time
import uuid
import sys
from pathlib import Path

import httpx

from aitown.config import Settings
from aitown.question_bank.models import COURSE_ID
from aitown.ui.demo import settings_for_ui
from aitown.ui.server import make_server
from aitown.ui.service import UIService


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('data/question_bank'))
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--upload',action='store_true',help='Check image reference search and one-method illustrated solution')
    args=parser.parse_args()
    source=args.source.resolve()
    run=Path('data/evaluation')/('study-runtime-'+uuid.uuid4().hex[:10])
    bank=run/'question_bank';bank.mkdir(parents=True)
    original=sqlite3.connect((source/'question_bank.sqlite3').as_uri()+'?mode=ro',uri=True)
    clone=sqlite3.connect(bank/'question_bank.sqlite3');original.backup(clone);original.close()
    clone.row_factory=sqlite3.Row
    # Only public FDU course sources enter the online validation copy.
    with clone:
        keep=[r[0] for r in clone.execute("SELECT id FROM sources WHERE course_id=? AND repository='victkk/FDU-Sharing'",(COURSE_ID,))]
        if not keep:raise RuntimeError('没有可验证的公开课程来源。')
        marks=','.join('?' for _ in keep)
        clone.execute('DELETE FROM question_duplicates')
        clone.execute('DELETE FROM answers WHERE source_id NOT IN ('+marks+')',keep)
        clone.execute('DELETE FROM questions WHERE source_id NOT IN ('+marks+')',keep)
        clone.execute('DELETE FROM pages WHERE source_id NOT IN ('+marks+')',keep)
        clone.execute('DELETE FROM rendered_pages WHERE source_id NOT IN ('+marks+')',keep)
        clone.execute('DELETE FROM jobs')
        clone.execute('DELETE FROM sources WHERE id NOT IN ('+marks+')',keep)
        clone.execute('DELETE FROM courses WHERE id<>?',(COURSE_ID,))
        for sid in keep:
            folder=source/'processed'/str(sid)
            if folder.is_dir():shutil.copytree(folder,bank/'processed'/str(sid),dirs_exist_ok=True)
        def moved(name):
            return str((bank/'processed'/Path(name).resolve().relative_to(source/'processed')).resolve()) if name else name
        for row in clone.execute('SELECT id,images FROM questions').fetchall():
            clone.execute('UPDATE questions SET images=? WHERE id=?',(json.dumps([moved(p) for p in json.loads(row['images'])]),row['id']))
        for table in ('pages','rendered_pages'):
            for row in clone.execute(f'SELECT source_id,ordinal,image FROM {table} WHERE image IS NOT NULL').fetchall():
                clone.execute(f'UPDATE {table} SET image=? WHERE source_id=? AND ordinal=?',(moved(row['image']),row['source_id'],row['ordinal']))
    clone.close()
    installed=Settings.from_env(mode='demo').model_copy(update={'question_bank_dir':bank.resolve()})
    service=UIService(settings_for_ui(installed,run/'application',data='study'),run/'application/ui.sqlite3',data='study')
    checks={};results={};started=time.perf_counter()
    try:
        session=service.call('_create_session',{})['id']
        service.call('_question_scope',{'session':session,'course':COURSE_ID})
        def chat(text):return service.call('_chat',{'session':session,'question':text})['reply']
        if args.upload:
            from aitown.question_bank.models import GetArgs
            original=service.pool.submit(lambda:service.agent.question_bank.get(GetArgs(question_ids=[210])).results[0]).result()
            reference=Path(original['images'][0])
            print('真实图片附件检索：上传已核对的公开原题截图',flush=True)
            upload_server=make_server(service,0);upload_thread=threading.Thread(target=upload_server.serve_forever,daemon=True);upload_thread.start()
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{upload_server.server_port}',trust_env=False,timeout=10) as client:
                    job_id=client.post('/api/question-upload',data={'session':session,'query':'找两道与此题知识点和主要方法相似的题'},
                        files={'files':('公开参考题.png',reference.read_bytes(),'image/png')}).raise_for_status().json()['job_id']
                    last=''
                    while True:
                        job=client.get('/api/job',params={'id':job_id}).raise_for_status().json()
                        if job['phase']!=last:print(job['phase'],flush=True);last=job['phase']
                        if job['status']!='running':break
                        time.sleep(.5)
                    if job['status']!='complete':raise RuntimeError(str(job))
                    reply=job['result']['reply']
                uploaded=service.call('_history',session)['turns'][-1]
                results['recognized_reference']=uploaded['reference']
                checks['recognized_complete_reference']=uploaded['reference']['status']=='complete' and '8' in uploaded['reference']['text'] and '3' in uploaded['reference']['text']
                checks['upload_reference_is_not_sticky']=not service.agent.question_bank.uploaded_references
                checks['compact_final_result']='https://' not in reply['answer'] and len(reply['answer'])<100
                checks['attachment_history_preserved']=bool(uploaded['attachments'])
            finally:upload_server.shutdown();upload_server.server_close();upload_thread.join()
        else:
            print('真实 ChatGPT 检索：集合大小为8、恰有3个等价类',flush=True)
            reply=chat('找一道集合大小为8、恰有3个等价类的等价关系计数题')
        results['search']=reply
        checks['real_chatgpt_selection']=reply['output_kind']=='question_selected' and bool(reply['questions'])
        if not checks['real_chatgpt_selection']:raise RuntimeError('真实 ChatGPT 检索未成功，详见报告。')
        chosen=next(q for q in reply['questions'] if q['id']==210) if args.upload else next(q for q in reply['questions'] if '8' in str(q) and '3' in str(q))
        qid=chosen['id']
        service.call('_study_mark',{'session':session,'question_id':qid,'state':'incorrect'})
        service.call('_study_filter',{'session':session,'state':'incorrect'})
        if not args.upload:
            print('真实 ChatGPT 按做错状态筛题',flush=True)
            filtered=chat('找一道等价关系计数题')
            checks['filter_before_selection']=[q['id'] for q in filtered['questions']]==[qid]
        print('真实 ChatGPT 解题：书面解答与方法归纳',flush=True)
        service.call('_solve_question',{'session':session,'question_id':qid})
        history=service.call('_history',session)
        record=next(q for q in history['turns'][0]['reply']['questions'] if q['id']==qid)['study']
        results['solution']=record['solution']
        checks['solution_preserves_manual_mark']=record['state']=='incorrect'
        checks['solution_has_written_answer_and_methods']=bool(record['solution']['written_answer'] and record['solution']['methods'])
        checks['count_answer_966']='966' in record['solution']['written_answer']
        checks['one_primary_method']=len(record['solution']['methods'])==1
        if args.upload:
            # Counting can reasonably use no figure; a graph exchange argument
            # separately exercises the optional illustration on a visual task.
            print('真实 ChatGPT 图解：最小生成树阈值分割',flush=True)
            service.call('_solve_question',{'session':session,'question_id':241})
            graph=next(q for q in service.call('_study_library')['questions'] if q['id']==241)['study']['solution']
            results['graph_solution']=graph
            checks['graph_has_one_main_method_and_figure']=len(graph['methods'])==1 and bool(graph['diagrams'])
        # The known public two-part partial-order question exercises all subquestions.
        def select_proof():
            from aitown.question_bank.models import GetArgs
            from aitown.question_bank.repository import BankRepository
            with BankRepository(bank/'question_bank.sqlite3',readonly=True) as repo:
                return next(q['id'] for q in repo.rows(COURSE_ID) if '充要条件' in q['text'] and 'B^A' in q['text'])
        if not args.upload:
            proof=select_proof()
            print('真实 ChatGPT 解题：函数空间偏序与最大元的充要条件',flush=True)
            service.call('_study_filter',{'session':session,'state':'all'})
            service.call('_solve_question',{'session':session,'question_id':proof})
            library=service.call('_study_library')['questions']
            results['proof_solution']=next(q for q in library if q['id']==proof)['study']['solution']
            checks['second_solution_saved']=bool(results['proof_solution']['methods'])
        service.pool.submit(lambda:(service.agent.close(),service.meta.close(),service._start())).result()
        persisted=service.call('_history',session)
        checks['restart_preserves_marks_solutions_and_scope']=persisted['session']['question_course']==COURSE_ID and next(q for q in persisted['turns'][0]['reply']['questions'] if q['id']==qid)['study']['state']=='incorrect'
        server=make_server(service,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        with httpx.Client(base_url=url,trust_env=False) as client:
            checks['http_library_and_local_formula_asset']=bool(client.get('/api/study').json()['questions']) and client.get('/vendor/katex.min.js').status_code==200
        report={'checks':checks,'passed':all(checks.values()),'seconds':time.perf_counter()-started,'url':url+'/?session='+session,
            'run':str(run.resolve()),'results':results,'limits':'公开课程题的小样本；计数核对966，方法与示意图仍需结合原题人工核查，不代表全库解题准确率。'}
        (run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False),flush=True)
        try:
            if args.serve:
                print('界面验证服务已就绪，Ctrl+C 停止。',flush=True)
                while True:time.sleep(1)
        finally:server.shutdown();server.server_close();thread.join()
    finally:
        service.close()
        if not (run/'report.json').exists():
            (run/'report.json').write_text(json.dumps({'checks':checks,'results':results,'passed':False},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
