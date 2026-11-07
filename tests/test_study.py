import json
import threading

import httpx
import pytest

from aitown.config import Settings
from aitown.models import AnswerPayload, Decision, ReviewPayload, SkillCall
from aitown.question_bank.chatgpt import ChatGPTSimilarity, SimilarSelection
from aitown.question_bank.models import COURSE_ID, GetArgs, Page, ParsedSource, Question, SearchArgs, Source
from aitown.question_bank.repository import BankRepository
from aitown.question_bank.search import QuestionBank
from aitown.question_bank.solve import Solution, solve_question
from aitown.question_bank.study import StudyStore
from aitown.ui.demo import settings_for_ui
from aitown.ui.server import make_server
from aitown.ui.service import UIService


def seed(root):
    parsed=ParsedSource(pages=[Page(ordinal=1,text='合成练习')],questions=[
        Question(number='1',text='在整数集上定义 aRb 当且仅当 3 整除 a-b。证明其为等价关系并求等价类。',pages=[1],topics=['等价关系'],question_type='证明'),
        Question(number='2',text='证明有限集合上的恒等关系是等价关系。',pages=[1],topics=['等价关系'],question_type='证明'),
        Question(number='3',text='证明图中所有顶点的度数之和为边数的两倍。',pages=[1],topics=['图论'],question_type='证明')],category='practice')
    with BankRepository(root/'question_bank.sqlite3') as repo:
        repo.save_discovery([{'id':COURSE_ID,'name':'集合与图论','path':'synthetic/course'}],[])
        source=repo.save_source(Source(course_id=COURSE_ID,repository='synthetic/study',path='practice.md',url='https://example.org/practice.md'))
        repo.replace_parsed(source,parsed)
        ids=[q['id'] for q in repo.rows(COURSE_ID)]
    return source,parsed,ids


@pytest.fixture
def learning(tmp_path,monkeypatch):
    root=tmp_path/'bank';source,parsed,ids=seed(root)
    def select(self,query,references,candidates,limit):
        chosen=candidates[:limit]
        return SimilarSelection(selected=[{'id':q['id'],'reason':'符合所选课程和本次要求'} for q in chosen],missing=''),{'status':'ok','provider':'codex_chatgpt','model':'test-chatgpt'}
    monkeypatch.setattr(ChatGPTSimilarity,'select',select)
    class MainModel:
        def structured(self,messages,schema):
            if schema is Decision:
                return Decision(intent='skill',query=messages[-1]['content'],calls=[SkillCall(
                    name='question_search',arguments={'course':COURSE_ID,'query':messages[-1]['content']})])
            return schema(answer='参考解答与方法见下方。')
        def close(self):pass
    monkeypatch.setattr('aitown.graph.create_model',lambda settings:MainModel())
    settings=settings_for_ui(Settings(question_bank_dir=root),tmp_path/'ui',data='study')
    service=UIService(settings,tmp_path/'ui/ui.sqlite3',data='study')
    session=service.call('_create_session',{})['id']
    service.call('_question_scope',{'session':session,'course':COURSE_ID})
    yield service,session,root,source,parsed,ids
    service.close()


def ask(service,session,text):
    return service.call('_chat',{'session':session,'question':text})['reply']


def solution_payload():
    return {'status':'complete','written_answer':r'对任意 $a\in\mathbb{Z}$，有 $3\mid(a-a)$。对称性由取相反数得到；传递性由差相加得到。等价类为 $[0],[1],[2]$。',
        'topics':['等价关系','模同余'], 'methods':[{'name':'整除关系转为模同余','recognition':'关系给出 m 整除两个整数之差',
        'key_idea':'把整除写为差等于整数倍','steps':['证明自反性','证明对称性','证明传递性','按余数划分等价类'],
        'conditions':'整数集，m 为固定正整数','pitfalls':['不要把整除关系 a|b 误作同余关系']}],
        'missing':[],'checks':['三个余数类覆盖整数集'],'diagrams':[]}


def test_matched_subquestion_survives_reflection_history_and_image_route(learning,monkeypatch):
    import pymupdf as fitz
    from aitown.question_bank.models import ImageRegion
    service,session,root,_,_,_=learning
    path=root/'processed/section.pdf';path.parent.mkdir(parents=True,exist_ok=True)
    with fitz.open() as document:
        page=document.new_page()
        for y,text in [(50,'1. Matching'),(100,'2. Planarity'),(150,'3. Partial order'),(200,'4. Symmetry'),(220,'(R union inverse R)+')]:
            page.insert_text((40,y),text)
        document.save(path)
    text='一、判断并说明理由\n1. 匹配\n2. 平面图\n3. 偏序\n4. 对称性和传递性\n(R union inverse R)+'
    with BankRepository(root/'question_bank.sqlite3') as repo:
        source=repo.save_source(Source(course_id=COURSE_ID,repository='synthetic',path='section.pdf',url='https://example.org/section.pdf'))
        repo.conn.execute('UPDATE sources SET local_path=? WHERE id=?',(str(path),source));repo.conn.commit()
        repo.replace_parsed(source,ParsedSource(pages=[Page(ordinal=1,text=text)],questions=[Question(
            number='一',text=text,pages=[1],question_type='判断',topics=['关系','平面图'],images=['placeholder.png'],
            image_regions=[ImageRegion(index=0,page=1,bbox=[0,20,595,240])])],category='practice'))
        qid=repo.conn.execute('SELECT id FROM questions WHERE source_id=?',(source,)).fetchone()[0]
    def select(self,query,references,candidates,limit):
        assert next(q for q in candidates if q['id']==qid)['selection_parts'][-1]['number']=='4'
        return SimilarSelection(selected=[{'id':qid,'reason':'第4小题考查对称性','matched_subquestions':['4']}],missing=''),{'status':'ok','provider':'codex_chatgpt'}
    monkeypatch.setattr(ChatGPTSimilarity,'select',select)
    reply=ask(service,session,'帮我找自反性对称性相关的题')
    assert reply['output_kind']=='question_selected'
    question=reply['questions'][0]
    assert question['display_number']=='一 · 第4小题' and len(question['images'])==1
    assert question['topics']==['关系']
    history=service.call('_history',session)
    assert history['turns'][-1]['reply']['questions'][0]['matched_subquestions']==['4']
    server=make_server(service,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(trust_env=False) as client:
            response=client.get(f'http://127.0.0.1:{server.server_port}/api/question-image',params={'id':qid,'index':0,'parts':'4'})
            assert response.status_code==200 and response.headers['content-type']=='image/png'
            image=fitz.Pixmap(response.content)
            assert image.height<100  # Only item 4 and its formula, not items 1-3.
            assert client.get(f'http://127.0.0.1:{server.server_port}/api/question-image',params={'id':qid,'index':0,'parts':'5'}).status_code==404
    finally:
        server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('state',['unattempted','attempted','correct','incorrect'])
def test_manual_states_persist_across_sessions_and_restart(learning,state):
    service,session,root,_,_,ids=learning
    ask(service,session,'找三道题')
    marked=service.call('_study_mark',{'session':session,'question_id':ids[0],'state':state})
    assert marked['state']==state
    second=service.call('_create_session',{})['id']
    service.call('_question_scope',{'session':second,'course':COURSE_ID})
    assert ask(service,second,'找三道题')['questions'][0]['study']['state']==state
    service.pool.submit(lambda:(service.agent.close(),service.meta.close(),service._start())).result()
    assert service.call('_history',session)['turns'][0]['reply']['questions'][0]['study']['state']==state


def test_filter_before_limit_and_manual_result_does_not_change_on_view(learning):
    service,session,_,_,_,ids=learning
    ask(service,session,'找三道题')
    service.call('_study_mark',{'session':session,'question_id':ids[2],'state':'incorrect'})
    service.call('_study_filter',{'session':session,'state':'incorrect'})
    reply=ask(service,session,'找一道题')
    assert [q['id'] for q in reply['questions']]==[ids[2]]
    service.call('_study_filter',{'session':session,'state':'all'})
    assert [q['id'] for q in ask(service,session,'找做错的题')['questions']]==[ids[2]]
    assert all(q['id']!=ids[2] for q in ask(service,session,'找没做过的题')['questions'])
    service.call('_study_filter',{'session':session,'state':'attempted'})
    assert [q['id'] for q in ask(service,session,'找一道题')['questions']]==[ids[2]]


def test_duplicates_share_state_reparse_preserves_same_problem_but_not_new_one(learning):
    service,session,root,source,parsed,ids=learning
    with BankRepository(root/'question_bank.sqlite3') as repo:
        other=repo.save_source(Source(course_id=COURSE_ID,repository='synthetic/study',path='duplicate.md',url='https://example.org/duplicate.md'))
        repo.replace_parsed(other,ParsedSource(pages=parsed.pages,questions=[parsed.questions[0]],category='practice'))
        duplicate=repo.conn.execute('SELECT id FROM questions WHERE source_id=?',(other,)).fetchone()[0]
        with repo.conn:repo.conn.execute('INSERT INTO question_duplicates VALUES(?,?)',(ids[0],duplicate))
    service.call('_study_mark',{'session':session,'question_id':duplicate,'state':'incorrect'})
    with StudyStore(root/'study.sqlite3',readonly=True) as study:
        with BankRepository(root/'question_bank.sqlite3',readonly=True) as repo:
            assert study.record(repo.get([ids[0]])[0])['state']=='incorrect'
    with BankRepository(root/'question_bank.sqlite3') as repo:
        repo.replace_parsed(source,parsed)
        current=repo.rows(COURSE_ID)[0]
    with StudyStore(root/'study.sqlite3',readonly=True) as study:
        assert study.record(current)['state']=='incorrect'
    changed=parsed.model_copy(deep=True);changed.questions[0].text='这是同题号的另一道完全不同的题。'
    with BankRepository(root/'question_bank.sqlite3') as repo:
        repo.replace_parsed(source,changed)
        replacement=next(q for q in repo.rows(COURSE_ID) if q['source_id']==source and q['number']=='1')
    with StudyStore(root/'study.sqlite3',readonly=True) as study:
        assert study.record(replacement)['state']=='unattempted'
        assert study.library()[0]['text']==parsed.questions[0].text


def test_chatgpt_solution_is_saved_and_does_not_mark_as_attempted(learning,monkeypatch):
    service,session,root,_,_,ids=learning
    received=[]
    def structured(self,prompt,schema,paths=(),**kwargs):
        received.append(prompt)
        assert '全部小问' in prompt and '适用条件' in prompt
        assert '微信' not in prompt and 'source_records' not in prompt
        return schema.model_validate(solution_payload()),{'status':'ok','provider':'codex_chatgpt','model':'test-chatgpt','phase':'question_solution'}
    monkeypatch.setattr(ChatGPTSimilarity,'structured',structured)
    ask(service,session,'找一道等价关系题')
    reply=ask(service,session,'解答第一题并进行方法归纳')
    assert reply['output_kind']=='question_solved'
    question=reply['questions'][0]
    assert question['study']['state']=='unattempted'
    assert question['study']['solution']['methods'][0]['name']=='整除关系转为模同余'
    assert len(received)==1
    assert ask(service,session,'第一题的答案')['output_kind']=='question_solved'
    assert len(received)==1
    assert ask(service,session,'第一题已有来源答案')['debug']['decision']['calls'][0]['name']=='question_get'
    service.call('_solve_question',{'session':session,'question_id':question['id'],'regenerate':True})
    assert len(received)==2
    assert service.call('_study_library')['questions'][0]['study']['solution']['written_answer']


def test_missing_conditions_are_kept_as_missing_and_failures_do_not_write(learning,monkeypatch):
    service,session,root,_,_,ids=learning
    def incomplete(self,prompt,schema,paths=(),**kwargs):
        return schema(status='needs_clarification',written_answer='',topics=[],methods=[],missing=['图中的边标记无法辨认'],checks=[],diagrams=[]),{'status':'ok','model':'test-chatgpt'}
    monkeypatch.setattr(ChatGPTSimilarity,'structured',incomplete)
    service.call('_solve_question',{'session':session,'question_id':ids[0]})
    saved=service.call('_study_library')['questions'][0]['study']
    assert saved['solution']['status']=='needs_clarification' and saved['state']=='unattempted'
    assert service.call('_solve_question',{'session':session,'question_id':ids[0]})['status']=='partial'
    def failed(*args,**kwargs):raise ValueError('ChatGPT 暂时不可用')
    monkeypatch.setattr(ChatGPTSimilarity,'structured',failed)
    with pytest.raises(ValueError,match='ChatGPT'):
        service.call('_solve_question',{'session':session,'question_id':ids[1]})
    assert len(service.call('_study_library')['questions'])==1


def test_later_duplicate_merge_keeps_solution_and_one_library_entry(learning):
    service,session,root,_,_,ids=learning
    from aitown.question_bank.models import GetArgs
    first=service.agent.question_bank.get(GetArgs(question_ids=[ids[0]])).results[0]
    other={**first,'path':'second.md','origins':[{**first['origins'][0],'path':'second.md'}]}
    with StudyStore(root/'study.sqlite3') as store:
        store.save_solution(first,{**solution_payload(),'created':123})
        store.mark(other,'correct')
        merged={**first,'origins':first['origins']+other['origins']}
        store.mark(merged,'incorrect')
        library=store.library(state='incorrect')
        assert len(library)==1 and library[0]['study']['solution']['written_answer']
        assert not store.library(state='correct')


def test_worker_cannot_inherit_disabled_local_models(learning,monkeypatch):
    service,session,root,_,_,ids=learning
    from aitown.question_bank.scheduler import launch
    captured={}
    def spawn(command,**kwargs):
        captured.update(kwargs['env'])
        return type('Process',(),{'pid':12345})()
    monkeypatch.setenv('LOCAL_EMBEDDING_DIR','old-local-embedding')
    monkeypatch.setenv('LOCAL_RERANKER_DIR','old-local-reranker')
    monkeypatch.setattr('aitown.question_bank.scheduler.subprocess.Popen',spawn)
    launch(service.agent.question_bank.config,COURSE_ID)
    assert captured['LOCAL_EMBEDDING_DIR']==captured['LOCAL_RERANKER_DIR']==''


def test_learning_start_does_not_open_personal_data_or_local_models(tmp_path):
    installed=Settings(retrieval_database=tmp_path/'private.sqlite3',style_database=tmp_path/'style.sqlite3',style_profile=tmp_path/'private.json',local_embedding_dir=tmp_path/'missing-model',question_extractor='mineru')
    config=settings_for_ui(installed,tmp_path/'learning',data='study')
    service=UIService(config,tmp_path/'learning/ui.sqlite3',data='study')
    try:
        assert service.agent.model is not None and service.agent.retriever is not None and service.agent.style_repository is None
        assert service.settings.mode=='live' and service.settings.llm_provider=='codex_chatgpt'
        assert service.agent.retrieval_repository.path==tmp_path/'learning/learning.sqlite3'
        assert service.agent.retriever.reranker.name=='online-llm-rerank'
        assert service.agent.question_bank.config.embedding_dir is None
        assert service.agent.question_bank.config.extractor=='basic'
        assert not hasattr(service,'wechat_sync')
        assert service.call('_bootstrap')['scopes']==[]
        assert service.call('_bootstrap')['live_available']
        assert not (tmp_path/'private.sqlite3').exists()
    finally:service.close()


def test_study_http_endpoints_and_origin_protection(learning):
    service,session,_,_,_,ids=learning
    server=make_server(service,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}',trust_env=False) as client:
            payload={'session':session,'question_id':ids[0],'state':'correct'}
            assert client.post('/api/study-mark',json=payload,headers={'Origin':'https://example.org'}).status_code==403
            assert client.post('/api/study-mark',json=payload).json()['state']=='correct'
            assert client.get('/api/study?state=correct').json()['questions'][0]['study']['state']=='correct'
            assert client.post('/api/study-mark',json={**payload,'state':'invented'}).status_code==400
            assert client.get('/vendor/katex.min.js').status_code==200
            assert client.get('/study.js').status_code==200
    finally:server.shutdown();server.server_close();thread.join()


def test_reference_upload_uses_main_graph_and_is_scoped_to_one_turn(learning,monkeypatch):
    from aitown.question_bank.attachments import ReferenceProblem
    service,session,root,_,_,ids=learning
    recognition=[];selections=[]
    def structured(self,prompt,schema,paths=(),**kwargs):
        assert schema is ReferenceProblem
        recognition.append((prompt,paths))
        return schema(status='complete',text='在整数集上，a 与 b 的差被 3 整除，证明为等价关系。',
            search_query='模同余 等价关系 自反 对称 传递',topics=['等价关系'],question_type='证明',missing=[]),{'model':'test','status':'ok'}
    def select(self,query,references,candidates,limit):
        selections.append(references)
        return SimilarSelection(selected=[{'id':candidates[0]['id'],'reason':'同为模同余的等价关系证明'}],missing='仅核对了部分候选'),{'model':'test','status':'ok'}
    monkeypatch.setattr(ChatGPTSimilarity,'structured',structured)
    monkeypatch.setattr(ChatGPTSimilarity,'select',select)
    result=service.call('_search_attachment',{'session':session,'query':'找两道相似题'},
        [{'name':'../参考题.md','content':'证明模 3 同余为等价关系。'.encode('utf-8')}])
    assert len(recognition)==1 and len(selections[0])==1
    assert selections[0][0]['id']==-1 and selections[0][0]['course_id']==COURSE_ID
    assert service.agent.question_bank.uploaded_references==[]
    assert result['reply']['answer']=='找到 1 道题，请查看下方原题。'
    assert result['reply']['search_notes']==['仅核对了部分候选']
    history=service.call('_history',session)
    turn=history['turns'][-1]
    assert turn['question']=='找两道相似题' and turn['attachments'][0]['name']=='参考题.md'
    file=turn['attachments'][0]
    assert service.call('_reference_file',file['upload_id'],session,0)[0].decode()=='证明模 3 同余为等价关系。'
    other=service.call('_create_session',{})['id']
    with pytest.raises(ValueError,match='不存在'):
        service.call('_reference_file',file['upload_id'],other,0)
    ask(service,session,'找一道图论证明题')
    assert selections[-1]==[]
    service.pool.submit(lambda:(service.agent.close(),service.meta.close(),service._start())).result()
    assert service.call('_history',session)['turns'][0]['attachments'][0]['name']=='参考题.md'


def test_reference_image_pdf_limits_and_missing_conditions(learning,tmp_path,monkeypatch):
    import pymupdf
    from aitown.question_bank.attachments import prepare_reference,ReferenceProblem
    document=pymupdf.open();document.new_page().insert_text((40,50),'a ~ b iff 3 divides (a-b). Prove equivalence.')
    png=document[0].get_pixmap().tobytes('png');pdf=document.tobytes();document.close()
    prepared=prepare_reference(tmp_path/'valid',[{'name':'question.png','content':png},{'name':'question.pdf','content':pdf}])
    assert len(prepared['images'])==2
    assert 'Prove equivalence' in prepared['documents'][1]['text']
    too_long=pymupdf.open()
    for _ in range(7):too_long.new_page()
    with pytest.raises(ValueError,match='最多 6'):
        prepare_reference(tmp_path/'long',[{'name':'many.pdf','content':too_long.tobytes()}])
    too_long.close()
    with pytest.raises(ValueError,match='请选择'):
        prepare_reference(tmp_path/'bad',[{'name':'attack.svg','content':b'<svg/>'}])
    with pytest.raises(ValueError):
        prepare_reference(tmp_path/'broken',[{'name':'broken.png','content':b'not an image'}])
    service,session,root,_,_,_=learning
    def unclear(self,prompt,schema,paths=(),**kwargs):
        assert schema is ReferenceProblem and len(paths)==1
        assert all(str(root/'processed') in str(path) for path in paths)
        return schema(status='needs_clarification',text='',search_query='',topics=[],question_type=None,
            missing=['关键边标记模糊，请补充清晰图']),{'model':'test'}
    monkeypatch.setattr(ChatGPTSimilarity,'structured',unclear)
    with pytest.raises(ValueError,match='关键边标记模糊'):
        service.call('_search_attachment',{'session':session},[{'name':'question.png','content':png}])
    assert not service.call('_history',session)['turns']
    assert service.agent.question_bank.uploaded_references==[]


def test_reference_http_upload_is_async_and_protects_origin(learning,monkeypatch):
    from aitown.question_bank.attachments import ReferenceProblem
    service,session,_,_,_,_=learning
    monkeypatch.setattr(ChatGPTSimilarity,'structured',lambda self,prompt,schema,paths=(),**kw:(
        ReferenceProblem(status='complete',text='证明模 3 同余为等价关系。',search_query='模同余 等价关系',
                         topics=['等价关系'],question_type='证明',missing=[]),{'status':'ok','model':'test'}))
    server=make_server(service,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}',trust_env=False) as client:
            fields={'session':session,'query':'找三道相似题'}
            files={'files':('question.txt','证明模 3 同余为等价关系。'.encode(),'text/plain')}
            assert client.post('/api/question-upload',data=fields,files=files,headers={'Origin':'https://example.org'}).status_code==403
            response=client.post('/api/question-upload',data=fields,files=files)
            assert response.status_code==200 and 'job_id' in response.json()
            import time
            for _ in range(100):
                job=client.get('/api/job',params={'id':response.json()['job_id']}).json()
                if job['status']!='running':break
                time.sleep(.01)
            assert job['status']=='complete' and '识别参考题的题设与知识点' in job['steps']
            assert client.get('/reference-upload.js').status_code==200
    finally:server.shutdown();server.server_close();thread.join()


def test_one_main_method_and_safe_diagram_schema():
    from pydantic import ValidationError
    from aitown.question_bank.solve import Solution
    schema=Solution.model_json_schema()
    assert set(schema['required'])==set(schema['properties'])
    assert all(set(item.get('required',[]))==set(item.get('properties',{})) for item in schema['$defs'].values())
    payload=solution_payload()
    payload['methods']*=2
    with pytest.raises(ValidationError):Solution.model_validate(payload)
    payload['methods']=payload['methods'][:1]
    diagram={'title':'等价类示例','purpose':'example','caption':'每个圆对应一个余数类。',
        'points':[{'id':'a','x':25,'y':50,'label':'0, 3, 6'}, {'id':'b','x':75,'y':50,'label':'1, 4, 7'}],
        'edges':[],'circles':[{'x':25,'y':50,'radius':20,'label':'[0]'}]}
    payload['diagrams']=[diagram]
    assert len(Solution.model_validate(payload).diagrams)==1
    for bad in [{**diagram,'points':diagram['points']*2},
                {**diagram,'edges':[{'start':'a','end':'missing','label':'','directed':True,'dashed':False}]},
                {**diagram,'svg':'<script>alert(1)</script>'},
                {**diagram,'points':[{'id':'a','x':float('nan'),'y':50,'label':''}]}]:
        with pytest.raises(ValidationError):Solution.model_validate({**payload,'diagrams':[bad]})
