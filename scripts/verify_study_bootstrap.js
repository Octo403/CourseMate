// Exercise startup with study.js arriving after the main script, without a browser.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const controls=new Map(),selectors=new Map(),listeners=new Map();
function node(tag='div',text=''){
 let own=text;
 const n={tagName:tag,children:[],dataset:{},hidden:false,disabled:false,value:'',
  get textContent(){return own+this.children.map(child=>child.textContent).join('');},
  set textContent(value){own=value;this.children=[];},
  append(...children){for(const child of children){child.parentElement=this;this.children.push(child);}},
  replaceChildren(...children){own='';this.children=[];this.append(...children);},
  setAttribute(){},addEventListener(){},querySelectorAll(){return [];}};
 return n;
}
const html=fs.readFileSync('src/aitown/ui/static/index.html','utf8');
for(const match of html.matchAll(/id="([^"]+)"/g))controls.set(match[1],node());
controls.get('question-model-mode').options=['none','api','codex_chatgpt'].map(value=>Object.assign(node('option'),{value}));
controls.get('codex-model-images').parentElement={lastChild:node('#text')};
const document={body:node('body'),getElementById:id=>controls.get(id),createElement:node,
 querySelectorAll:()=>[],querySelector(selector){if(!selectors.has(selector))selectors.set(selector,node());return selectors.get(selector);},
 addEventListener(event,handler){if(!listeners.has(event))listeners.set(event,[]);listeners.get(event).push(handler);}};
const bootstrap={data:'study',hosted:true,mode:'demo',default_scope:'',sessions:[{id:'session'}]};
let requests=0;
const sandbox={document,URLSearchParams,location:{search:''},localStorage:{getItem:()=>null},
 fetch:async()=>{requests++;return {ok:true,json:async()=>bootstrap};}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('src/aitown/ui/static/app.js','utf8'),sandbox);
async function main(){
 // Let an immediately resolved bootstrap finish if app.js incorrectly starts early.
 for(let i=0;i<10;i++)await Promise.resolve();
 assert.equal(requests,0,'The first request must wait until all deferred extensions have loaded.');
 // Keep the base renderer out of this focused fixture; exercise the real study extension.
 vm.runInContext('renderBootstrap=()=>{};chooseSession=async()=>{};',sandbox);
 vm.runInContext(fs.readFileSync('src/aitown/ui/static/study.js','utf8'),sandbox);
 for(const handler of listeners.get('DOMContentLoaded')||[])handler();
 for(let i=0;i<20;i++)await Promise.resolve();
 assert.equal(requests,1);
 assert.equal(document.body.dataset.experience,'study');
 assert.equal(controls.get('open-materials').textContent,'我的学习');
 assert.equal(controls.get('open-materials').onclick,sandbox.openStudyLibrary);
 assert(document.querySelector('#first-run-setup ol').textContent.includes('模型 API'));
 assert(!document.querySelector('#first-run-setup ol').textContent.includes('Codex'));
 const codex=controls.get('question-model-mode').options.find(option=>option.value==='codex_chatgpt');
 assert(codex.hidden&&codex.disabled);
 vm.runInContext('renderBootstrap();',sandbox);
 assert(codex.hidden&&codex.disabled,'Refreshing bootstrap must not enable server CLI login.');
 bootstrap.hosted=false;
 vm.runInContext('renderBootstrap();',sandbox);
 assert(!codex.hidden&&!codex.disabled);
 assert(document.querySelector('#first-run-setup ol').textContent.includes('Codex'));
 bootstrap.data='synthetic';
 vm.runInContext('renderBootstrap();',sandbox);
 assert.equal(document.body.dataset.experience,'legacy');
 assert.equal(controls.get('open-materials').textContent,'个人资料');
 assert(html.includes('<body data-experience="study">'));
 assert(/id="open-materials"[^>]*>我的学习</.test(html));
 console.log(JSON.stringify({passed:true,checks:['deferred startup order','hosted learning entry','hosted API setup','hosted CLI stays disabled on refresh','local ChatGPT entry','explicit legacy mode','learning HTML before bootstrap'],scope:'Real app.js and study.js with a DOM fixture; no browser visual acceptance.'},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
