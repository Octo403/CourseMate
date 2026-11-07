// Actual study UI handlers with a small DOM fixture; this is not a browser layout test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const controls=new Map(),nodes=[];
function descendants(n){return n.children.flatMap(c=>[c,...descendants(c)]);}
function matches(n,selector){return selector.startsWith('.')?n.className.split(' ').includes(selector.slice(1)):n.tagName===selector;}
function node(tag,text=''){
 let own=text;
 const n={tagName:tag,children:[],attrs:{},dataset:{},className:'',hidden:false,
  get textContent(){return own+this.children.map(c=>c.textContent).join('');},set textContent(v){own=v;this.children=[];},
  append(...children){this.children.push(...children);},prepend(...children){this.children.unshift(...children);},
  replaceChildren(...children){own='';this.children=[...children];},setAttribute(k,v){this.attrs[k]=v;},focus(){},
  addEventListener(event,handler){this['on'+event]=handler;},
  querySelectorAll(selector){return descendants(this).filter(c=>selector.split(',').some(s=>matches(c,s)));},
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;},
  get childElementCount(){return this.children.length;}};
 n.classList={contains:c=>n.className.split(' ').includes(c),add(c){if(!this.contains(c))n.className+=' '+c;},toggle(c,on){if(on)this.add(c);else n.className=n.className.split(' ').filter(x=>x!==c).join(' ');}};
 nodes.push(n);return n;
}
for(const match of fs.readFileSync('src/aitown/ui/static/index.html','utf8').matchAll(/id="([^"]+)"/g))controls.set(match[1],node('div'));
const composer=node('div');composer.className='composer';
const document={getElementById:id=>controls.get(id),createElement:node,createElementNS:(ns,tag)=>node(tag),createTextNode:text=>node('#text',text),
 querySelector:selector=>nodes.find(n=>matches(n,selector)),
 body:node('body'),querySelectorAll:selector=>nodes.filter(n=>selector.split(',').some(s=>matches(n,s)))};
class FixtureFormData{constructor(){this.entries=[];}append(...values){this.entries.push(values);}}
const sandbox={document,console,FormData:FixtureFormData,URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL(){}},URLSearchParams,location:{search:''}};vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('src/aitown/ui/static/question_text.js','utf8'),sandbox);
vm.runInContext(fs.readFileSync('src/aitown/ui/static/app.js','utf8').replace(/^boot\(\);$/m,''),sandbox);
vm.runInContext(fs.readFileSync('src/aitown/ui/static/study.js','utf8'),sandbox);
vm.runInContext(fs.readFileSync('src/aitown/ui/static/reference_upload.js','utf8'),sandbox);
const actualRunJob=sandbox.runJob,actualApi=sandbox.api;
const calls=[],mathCalls=[];let history=0;
sandbox.fakeApi=async(path,payload)=>{calls.push({path,payload});return {questions:[]};};
sandbox.fakeHistory=async()=>history++;
sandbox.fakeJob=async(path,payload)=>{calls.push({path,payload});return true;};
sandbox.katex={render(math,target,options){mathCalls.push({math,options});if(math==='bad')throw Error('unsupported');target.textContent='rendered:'+math;}};
vm.runInContext("api=fakeApi;refreshHistory=fakeHistory;runJob=fakeJob;state.session='learning-session';",sandbox);
const solution={status:'complete',model:'test-model',created:1,written_answer:'得 $966$。',topics:['等价关系'],
 methods:[{name:'标号与容斥',recognition:'无标号划分',key_idea:'先标号再消重',conditions:'非空等价类',steps:['数满射','除以排列数'],pitfalls:['遗漏非空条件']}],checks:[],missing:[]};
function card(q){const c=node('section');c.className='question-card';sandbox.appendStudyControls(c,q);return c;}
async function main(){
 const checks={};
 const c=card({id:7,study:{state:'unattempted'}});
 const buttons=c.querySelectorAll('.study-mark');assert.equal(buttons.length,4);
 assert.equal(buttons[0].attrs['aria-pressed'],'true');
 for(let i=0;i<buttons.length;i++)await buttons[i].onclick();
 assert.deepEqual(calls.slice(0,4).map(c=>c.payload.state),['unattempted','attempted','correct','incorrect']);
 assert(calls.every(c=>c.payload.question_id===7&&c.payload.session==='learning-session'));assert.equal(history,4);
 checks.four_manual_states_use_current_question_and_refresh_history=true;
 const before=calls.length;
 const saved=card({id:8,study:{state:'incorrect',solution}});
 assert.equal(calls.length,before);assert.equal(saved.querySelector('.study-solution').open,undefined);
 saved.querySelector('.primary').onclick();
 assert(saved.querySelector('.study-solution').open&&saved.querySelector('.study-method-list').open);
 assert.equal(calls.length,before);assert(saved.textContent.includes('适用条件')&&saved.textContent.includes('易错点'));
 checks.reading_cached_solution_opens_answer_and_method_without_call_or_mark=true;
 await sandbox.solveStudyQuestion(8,true);
 assert.equal(calls.at(-1).path,'/api/question-solve');assert.equal(calls.at(-1).payload.regenerate,true);
 assert(saved.querySelector('.study-solution').open);
 checks.regeneration_calls_solver_and_opens_refreshed_solution=true;
 const archived=card({id:99,study_snapshot:true,study:{item_id:15,state:'attempted',solution}});
 assert.equal(archived.querySelectorAll('.study-actions').length,0);
 await archived.querySelectorAll('.study-mark')[3].onclick();
 assert.equal(calls.at(-1).payload.item_id,15);assert.equal(calls.at(-1).payload.question_id,undefined);
 checks.saved_snapshot_marks_by_personal_id_and_never_solves_stale_bank_id=true;
 const rendered=sandbox.renderStudyContent('内联 \\(x^2\\) 和 $y$。\n\\[a+b\\]\n$$c+d$$\n\n$bad$');
 assert(mathCalls.some(c=>c.math==='x^2')&&mathCalls.some(c=>c.math==='a+b')&&mathCalls.some(c=>c.math==='c+d'));
 assert(mathCalls.every(c=>c.options.output==='mathml'&&c.options.trust===false));assert(rendered.textContent.includes('$bad$'));
 assert(!descendants(sandbox.renderStudyContent('<script>alert(1)</script> ![track](https://example.org/image.png)')).some(n=>['script','img'].includes(n.tagName)));
 checks.local_mathml_handles_delimiters_keeps_failed_formula_and_blocks_source_html_media=true;
 const missing=card({id:10,study:{state:'unattempted',solution:{...solution,status:'needs_clarification',written_answer:'',methods:[],missing:['无法辨认边标记']}}});
 assert(missing.textContent.includes('需要补充：无法辨认边标记'));
 checks.incomplete_question_shows_specific_missing_information=true;
 const old=card({id:11,study:{state:'unattempted',solution:{...solution,methods:[...solution.methods,{...solution.methods[0],name:'零散的第二点'}]}}});
 assert.equal(old.querySelectorAll('.method-card').length,1);assert(!old.textContent.includes('零散的第二点'));
 checks.one_primary_method_shown_for_new_and_historical_answers=true;
 const diagram={title:'三角形',purpose:'problem',caption:'连接三个顶点。',points:[{id:'a',x:20,y:80,label:'<script>bad</script>'},{id:'b',x:80,y:80,label:'B'},{id:'c',x:50,y:20,label:'C'}],edges:[{start:'a',end:'b',label:'底边',directed:false,dashed:false}],circles:[]};
 const figure=sandbox.renderSolutionDiagram(diagram);
 assert.equal(figure.querySelectorAll('svg').length,1);assert.equal(figure.querySelectorAll('line').length,1);
 assert.equal(figure.querySelectorAll('script').length,0);assert(figure.textContent.includes('<script>bad</script>'));
 checks.diagram_uses_local_svg_shapes_and_literal_labels_without_executable_markup=true;
 const focused=sandbox.questionCards([{id:284,number:'一',display_number:'一 · 第4小题',matched_subquestions:['4'],
  topics:['关系'],category:'practice',images:['original.png'],image_previews:[{index:0,page:2,kind:'crop',location_kind:'page'}],
  missing:[],path:'exam.pdf',url:'',study:{state:'unattempted'},match_instruction:'判断并说明理由'}]);
 assert.equal(focused.querySelector('img').src,'/api/question-image?id=284&index=0&parts=4');
 assert(focused.textContent.includes('第4小题')&&focused.textContent.includes('判断并说明理由'));
 checks.matched_subquestion_card_requests_scoped_crop_and_keeps_instructions=true;
 vm.runInContext("state.history={session:{question_course:'fdu-set-graph-theory'}};state.bootstrap={data:'study'};",sandbox);
 controls.get('message').value='找两道相似题';
 sandbox.selectReferenceFiles([{name:'question.png',size:100}]);
 await controls.get('send').onclick();
 assert.equal(calls.at(-1).path,'/api/question-upload');
 assert(calls.at(-1).payload.entries.some(row=>row[0]==='files'&&row[1].name==='question.png'));
 assert.equal(controls.get('reference-selection').children.length,0);
 checks.send_button_submits_multipart_reference_and_clears_only_after_success=true;
 let submitted;
 sandbox.fetch=async(path,options)=>{submitted=options;return {ok:true,json:async()=>({job_id:'multipart-job'})};};
 const form=new FixtureFormData();form.append('files',{name:'q.png'},'q.png');await actualApi('/api/question-upload',form);
 assert.equal(submitted.body,form);assert.equal(submitted.headers,undefined);
 checks.multipart_upload_keeps_native_form_boundary_instead_of_json_header=true;
 controls.get('mineru-sample-source').options=[];let polls=0;
 sandbox.fakeProgressApi=async path=>{
  if(path==='/api/question-upload')return {job_id:'progress-job'};
  if(polls++===0)return {status:'running',phase:'识别参考题',steps:['读取附件','识别参考题']};
  assert.equal(controls.get('progress').hidden,false);assert.equal(controls.get('progress-steps').children.length,2);
  return {status:'complete',phase:'完成',steps:['读取附件','识别参考题','筛选相似题'],result:{}};
 };
 sandbox.fakeBootstrap=async()=>{};sandbox.setTimeout=callback=>{callback();return 0;};
 vm.runInContext('api=fakeProgressApi;refreshBootstrap=fakeBootstrap;state.panel=false;',sandbox);
 assert.equal(await actualRunJob('/api/question-upload',form),true);
 assert.equal(controls.get('progress').hidden,true);assert.equal(controls.get('send').disabled,false);
 checks.progress_shows_stages_while_running_and_hides_after_final_result=true;
 console.log(JSON.stringify({checks,passed:true,note:'真实 study.js / Markdown / card 事件与 DOM fixture；未进行浏览器视觉验收。'},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
