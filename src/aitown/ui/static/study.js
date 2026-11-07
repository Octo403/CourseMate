const studyLabels={unattempted:'未做过',attempted:'做过',correct:'做对',incorrect:'做错'};

function renderStudyContent(text){
 const normalized=(text||'').replace(/\\\[([\s\S]*?)\\\]/g,(_,math)=>'\n$$\n'+math.trim()+'\n$$\n')
  .replace(/\$\$([^\n]+?)\$\$/g,(_,math)=>'\n$$\n'+math+'\n$$\n');
 const body=renderQuestionText(normalized,'markdown');
 for(const node of body.querySelectorAll('.question-inline-math,.question-math')){
  if(typeof katex==='undefined')continue;
  const block=node.classList.contains('question-math');
  const original=node.textContent;
  const math=block?original:original.startsWith('$')?original.slice(1,-1):original.slice(2,-2);
  try{katex.render(math,node,{output:'mathml',displayMode:block,throwOnError:true,trust:false,maxExpand:300,maxSize:10});node.classList.add('rendered-math');}
  catch{node.textContent=original;node.title='此公式暂未排版，保留 LaTeX 原文';}
 }
 return body;
}

let solutionDiagramNumber=0;
function renderSolutionDiagram(diagram){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('viewBox','-12 -12 124 124');svg.setAttribute('role','img');svg.setAttribute('aria-label',diagram.title);svg.classList.add('solution-svg');
 const draw=(tag,attrs,text)=>{const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));if(text!==undefined)node.textContent=text;return node;};
 const arrow='solution-arrow-'+(++solutionDiagramNumber);const defs=draw('defs',{});const marker=draw('marker',{id:arrow,viewBox:'0 0 10 10',refX:8,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});marker.append(draw('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'currentColor'}));defs.append(marker);svg.append(defs);
 const label=(x,y,text)=>{if(!text)return;const node=draw('text',{x,y,'text-anchor':'middle',class:'diagram-label'});const letters=Array.from(text);for(let i=0;i<letters.length;i+=14)node.append(draw('tspan',{x,dy:i?4.5:0},letters.slice(i,i+14).join('')));svg.append(node);};
 for(const circle of diagram.circles||[]){svg.append(draw('circle',{cx:circle.x,cy:circle.y,r:circle.radius,class:'diagram-region'}));label(circle.x,circle.y-circle.radius+5,circle.label);}
 const points=new Map(diagram.points.map(point=>[point.id,point]));
 for(const edge of diagram.edges){
  const start=points.get(edge.start),end=points.get(edge.end);if(!start||!end)continue;
  const attrs={class:'diagram-edge'};if(edge.directed)attrs['marker-end']='url(#'+arrow+')';if(edge.dashed)attrs['stroke-dasharray']='2 2';
  if(start===end)svg.append(draw('path',{...attrs,d:`M ${start.x-1} ${start.y-1} C ${start.x-12} ${start.y-15}, ${start.x+12} ${start.y-15}, ${start.x+1} ${start.y-1}`}));
  else svg.append(draw('line',{...attrs,x1:start.x,y1:start.y,x2:end.x,y2:end.y}));
  label((start.x+end.x)/2,(start.y+end.y)/2-3,edge.label);
 }
 for(const point of diagram.points){svg.append(draw('circle',{cx:point.x,cy:point.y,r:1.3,class:'diagram-point'}));label(point.x,point.y+5,point.label);}
 const figure=el('figure',undefined,'solution-diagram');figure.append(svg,el('figcaption',(diagram.purpose==='example'?'方法示例':'题设示意')+' · '+diagram.title),el('p',diagram.caption,'muted'));
 const expand=el('button','放大示意图','quiet');expand.type='button';expand.onclick=()=>{
  const dialog=el('dialog',undefined,'image-viewer');dialog.setAttribute('aria-label',diagram.title);const close=el('button','关闭','quiet');close.onclick=()=>dialog.close();
  const content=el('div',undefined,'diagram-enlarged');content.append(renderSolutionDiagram({...diagram,title:diagram.title}));content.querySelector('button').remove();
  dialog.append(close,content);dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
 };figure.append(expand);return figure;
}

function appendSolution(card,solution){
 if(!solution)return;
 const [answer,body]=detail('书面参考解答 · '+(solution.provider==='codex_chatgpt'?'ChatGPT':'在线模型'));answer.classList.add('study-solution');
 body.append(el('p',`${solution.model} · ${date(solution.created)} · 模型生成，请核对题设与论证`,'muted'));
 if(solution.status==='needs_clarification')body.append(el('p','需要补充：'+solution.missing.join('；'),'warning'));
 if(solution.written_answer)body.append(renderStudyContent(solution.written_answer));
 for(const diagram of solution.diagrams||[])body.append(renderSolutionDiagram(diagram));
 if(solution.checks?.length){const [checks,list]=detail('解答中的核对说明');for(const item of solution.checks)list.append(renderStudyContent(item));body.append(checks);}
 card.append(answer);
 if(!solution.methods.length)return;
 const [methods,list]=detail('主要方法 · '+solution.methods[0].name);methods.classList.add('study-method-list');
 for(const method of solution.methods.slice(0,1)){
  const entry=el('section',undefined,'method-card');entry.append(renderStudyContent(method.key_idea));
  const [more,extra]=detail('适用条件、步骤与易错点');
  for(const [label,text] of [['识别线索',method.recognition],['适用条件',method.conditions]]){
   extra.append(el('strong',label),renderStudyContent(text));
  }
  extra.append(el('strong','通用步骤'));const steps=el('ol');for(const step of method.steps){const item=el('li');item.append(renderStudyContent(step));steps.append(item);}extra.append(steps);
  if(method.pitfalls.length){extra.append(el('strong','易错点'));for(const pitfall of method.pitfalls)extra.append(renderStudyContent(pitfall));}
  entry.append(more);list.append(entry);
 }
 if(solution.topics.length)list.prepend(el('p','知识点：'+solution.topics.slice(0,4).join(' / '),'muted'));
 card.append(methods);
}

function appendStudyControls(card,question){
 card.dataset.questionId=String(question.id);
 const record=question.study||{state:'unattempted'};
 const controls=el('div',undefined,'study-controls');controls.setAttribute('role','group');controls.setAttribute('aria-label','我的做题标记');
 controls.append(el('span','我的标记：'));
 for(const [value,label] of Object.entries(studyLabels)){
  const button=el('button',label,record.state===value?'study-mark selected':'study-mark');button.type='button';
  button.setAttribute('aria-pressed',String(record.state===value));button.disabled=state.busy;
  button.onclick=async()=>{
   if(state.busy)return;
   const payload={session:state.session,state:value,...(question.study_snapshot?{item_id:record.item_id}:{question_id:question.id})};
   controls.querySelectorAll('button').forEach(node=>node.disabled=true);
   try{await api('/api/study-mark',payload);notice('已标记为“'+label+'”。');await refreshHistory();if(state.panel==='study')await refreshStudyLibrary();}
   catch(error){notice(error.message,true);controls.querySelectorAll('button').forEach(node=>node.disabled=state.busy);}
  };controls.append(button);
 }
 card.append(controls);
 if(record.state==='attempted')card.append(el('small','已尝试，尚未评价对错。','muted'));
 if(!question.study_snapshot){
  const actions=el('div',undefined,'study-actions');
  const solve=el('button',record.solution?'查看已存解答与方法':'解答与方法','primary');solve.disabled=state.busy;
  solve.onclick=()=>{if(record.solution){card.querySelectorAll('.study-solution,.study-method-list').forEach(node=>node.open=true);}
   else solveStudyQuestion(question.id);};actions.append(solve);
  if(record.solution){const again=el('button',record.solution.methods.length>1?'合并方法并重新求解':'重新求解','quiet');again.disabled=state.busy;again.onclick=()=>solveStudyQuestion(question.id,true);actions.append(again);}
  card.append(actions);
 }
 appendSolution(card,record.solution||question.solution);
}

async function solveStudyQuestion(questionId,regenerate=false){
 if(await runJob('/api/question-solve',{session:state.session,question_id:questionId,regenerate})){
  for(const card of document.querySelectorAll('.question-card'))if(card.dataset.questionId===String(questionId)){
   card.querySelectorAll('.study-solution,.study-method-list').forEach(node=>node.open=true);
  }
 }
}

async function refreshStudyLibrary(){
 const selected=$('study-library-filter').value;
 const data=await api('/api/study?state='+encodeURIComponent(selected));
 $('study-library-status').textContent=`${data.questions.length} 道已保存题目 · 包含标记与已生成解答`;
 $('study-questions').replaceChildren(data.questions.length?questionCards(data.questions):el('p','先检索一道题，填写标记或生成解答，它就会保存在这里。','empty'));
 const methods=new Map();
 for(const q of data.questions)for(const method of (q.study?.solution?.methods||[]).slice(0,1)){
  const key=method.name;const entry=methods.get(key)||{name:key,count:0};entry.count++;methods.set(key,entry);
 }
 $('study-methods').replaceChildren();
 if(methods.size){$('study-methods').append(el('h3','已积累的方法'));for(const method of methods.values())$('study-methods').append(el('p',`${method.name} · ${method.count} 道例题`,'method-summary'));}
}

async function openStudyLibrary(){
 state.panel='study';$('settings').hidden=true;$('materials').hidden=true;$('study-library').hidden=false;
 try{await refreshStudyLibrary();}catch(error){notice(error.message,true);}
}

const originalStudyBootstrap=renderBootstrap;
renderBootstrap=function(){
  originalStudyBootstrap();const learning=state.bootstrap.data==='study';document.body.dataset.experience=learning?'study':'legacy';
  if(!learning){$('open-materials').textContent='个人资料';$('open-materials').onclick=()=>openMaterials('personal');return;}
  const hosted=Boolean(state.bootstrap.hosted);
 $('open-materials').textContent='我的学习';$('open-materials').onclick=openStudyLibrary;
 $('new-session').textContent='＋ 新的学习会话';document.querySelector('.brand small').textContent='让题目成为自己的方法';
 document.querySelector('.topbar .eyebrow').textContent='课程题库与学习积累';
 $('welcome-title').textContent='从一道题，积累一种方法';
 $('welcome-description').textContent='可以直接聊天、解释知识，也可以选择课程找题，积累解答与方法。';
  $('welcome-note').textContent=hosted?'知识资料、题目和学习记录保存在服务器的当前浏览器独立空间。在线模型接收当前问题、相关会话与检索片段。':'知识资料、题目和学习记录保存在本机。在线模型接收当前问题、相关会话与检索片段；无需下载本地大模型。';
 $('suggestions').hidden=false;$('suggestions').replaceChildren();
 for(const [label,action] of [['选择课程题库',()=>showQuestionMentions()],['收集课程资料',()=>openMaterials('course')],['查看我的积累',openStudyLibrary]]){
  const button=el('button',label);button.onclick=action;$('suggestions').append(button);
 }
 $('composer-note').textContent='可粘贴或上传参考题图片、拖入文件找相似题。Enter 发送 · Shift + Enter 换行';
 $('mode-badge').textContent=state.bootstrap.mode==='live'?'在线 Agent':'本地筛选';
  for(const option of $('question-model-mode').options){option.hidden=hosted&&option.value==='codex_chatgpt';option.disabled=option.hidden;}
 document.querySelector('#question-model-settings h3').textContent='对话与课程模型';
  document.querySelector('#question-model-settings > p').textContent=hosted?'你填写的模型 API 用于意图理解、对话、检索重排、自省及题库。学习资料与做题标记仅用于当前浏览器的独立空间。':'所选连接用于意图理解、对话、检索重排、自省及题库。微信资料不加载，做题标记仅保存在本机。';
 document.querySelector('label[for="question-model-mode"]').textContent='模型连接';
 const knowledge=$('knowledge-library-section');
 const settingsBody=document.querySelector('#settings .panel-scroll');
 if(knowledge.parentElement!==settingsBody)settingsBody.append(knowledge);
 $('knowledge-library-note').textContent='独立学习知识库：导入 TXT / MD 后可直接提问，无需选择课程。检索到的片段交给所选在线模型重排与回答，请只导入允许发送的学习资料。';
 document.querySelector('label[for="codex-model-id"]').textContent='ChatGPT 模型型号';
 $('codex-model-images').parentElement.lastChild.textContent='检索和解题使用原题截图';
  document.querySelector('#first-run-setup ol').replaceChildren(...(hosted?
   [el('li','填写你自己的模型 API 地址、Key 和型号。'),el('li','点击“测试并完成”保存本次连接。')]:
   [el('li','在当前 Windows 账户安装 Codex CLI，并运行 codex login 登录 ChatGPT。'),el('li','在下方刷新型号、选择并保存。')]),el('li','打开课程资料，收集课程或上传文件，然后选择 @ 课程找题。'));
  document.querySelector('#first-run-setup > p').textContent=hosted?'使用你自己的模型 API，无需在本机安装程序。Key 仅保留在服务器运行内存，重启或闲置回收后需重新填写。':'可使用已登录的 Codex CLI，或填写兼容模型 API。对话、检索重排与自省均使用所选在线连接，无需本地大模型或 GPU。';
 $('skip-setup').textContent='稍后设置，先收集资料';
 if(!$('study-filter')){
  const wrapper=el('label',undefined,'study-search-filter');wrapper.append(el('span','下次找题：'));
  const select=el('select');select.id='study-filter';select.setAttribute('aria-label','按做题状态找题');
  for(const [value,label] of [['all','全部'],['unattempted','未做过'],['attempted','做过（含对错）'],['correct','做对'],['incorrect','做错']]){const option=el('option',label);option.value=value;select.append(option);}
  select.onchange=async()=>{try{const entry=await api('/api/study-filter',{session:state.session,state:select.value});if(state.history)state.history.session=entry;notice('筛选已保存，下次找题生效。');}catch(error){notice(error.message,true);}};
  wrapper.append(select);document.querySelector('.question-scope-tools').append(wrapper);
 }
};

const originalStudyHistory=refreshHistory;
refreshHistory=async function(){await originalStudyHistory();if($('study-filter'))$('study-filter').value=state.history?.session.study_filter||'all';};
const originalStudyMaintenance=refreshMaintenance;
refreshMaintenance=async function(){if(state.panel==='study')return refreshStudyLibrary();return originalStudyMaintenance();};
const originalStudySettings=toggleSettings;
toggleSettings=async function(open){$('study-library').hidden=true;return originalStudySettings(open);};
const originalStudyMaterials=openMaterials;
openMaterials=async function(view='course'){$('study-library').hidden=true;return originalStudyMaterials(view);};
const originalStudyTurns=renderTurns;
renderTurns=function(){
 originalStudyTurns();if(state.bootstrap?.data!=='study')return;
 document.querySelectorAll('.reply-tools,.saved-feedback').forEach(node=>node.hidden=true);
 document.querySelectorAll('#turns .turn').forEach((section,i)=>{
  const turn=state.history.turns[i],reply=turn.reply;
  if(reply?.output_kind==='question_solved')section.querySelector('.reply-note').textContent='模型生成的参考解答 · 做题标记由你填写';
  for(const node of section.querySelectorAll('details'))if(node.classList.contains('debug')||node.querySelector('summary')?.textContent.startsWith('技能结果'))node.hidden=true;
  if(reply?.search_notes?.length){const [notes,body]=detail('检索说明');for(const text of reply.search_notes)body.append(el('p',text));section.append(notes);}
  if(turn.attachments?.length){
   const files=el('div',undefined,'history-attachments');
   for(const file of turn.attachments){
    const url=`/api/reference-file?id=${encodeURIComponent(file.upload_id)}&session=${encodeURIComponent(state.session)}&index=${file.index}`;
    const link=el('a',file.name);link.href=url;link.target='_blank';link.rel='noopener noreferrer';
    if(file.image){const image=el('img');image.src=url;image.alt='参考题：'+file.name;image.loading='lazy';link.prepend(image);}files.append(link);
   }
   section.insertBefore(files,section.querySelector('.assistant-label'));
   const [recognized,body]=detail('已识别的参考题');body.append(renderStudyContent(turn.reference.text));section.append(recognized);
  }
 });
};
$('close-study-library').onclick=()=>{$('study-library').hidden=true;state.panel=false;};
$('study-library-filter').onchange=()=>refreshStudyLibrary().catch(error=>notice(error.message,true));
