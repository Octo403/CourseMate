// Reference uploads are scoped to one send, independent of course ingestion.
let referenceFiles=[];
const referenceURLs=new Map();
function clearReferenceFiles(){
 for(const url of referenceURLs.values())URL.revokeObjectURL(url);
 referenceURLs.clear();referenceFiles=[];$('reference-files').value='';renderReferenceFiles();
}
function selectReferenceFiles(files){
 const selected=[...referenceFiles,...files];
 if(selected.length>3){notice('每次最多选择 3 个附件，作为同一道参考题。',true);return;}
 if(selected.reduce((sum,file)=>sum+file.size,0)>20*1024*1024){notice('附件合计不能超过 20 MiB。',true);return;}
 if(selected.some(file=>! /\.(png|jpe?g|webp|pdf|docx?|txt|md)$/i.test(file.name))){notice('请选择图片、PDF、Word、TXT 或 MD。',true);return;}
 referenceFiles=selected;notice('');renderReferenceFiles();
}
function renderReferenceFiles(){
 const box=$('reference-selection');box.replaceChildren();
 for(const file of referenceFiles){
  const item=el('div',undefined,'reference-file');
  if(/\.(png|jpe?g|webp)$/i.test(file.name)){
   if(!referenceURLs.has(file))referenceURLs.set(file,URL.createObjectURL(file));
   const image=el('img');image.src=referenceURLs.get(file);image.alt='参考题预览：'+file.name;item.append(image);
  }
  item.append(el('span',file.name));const remove=el('button','×','quiet');remove.type='button';remove.disabled=state.busy;remove.setAttribute('aria-label','移除 '+file.name);
  remove.onclick=()=>{if(state.busy)return;if(referenceURLs.has(file))URL.revokeObjectURL(referenceURLs.get(file));referenceURLs.delete(file);referenceFiles=referenceFiles.filter(value=>value!==file);renderReferenceFiles();};item.append(remove);box.append(item);
 }
}
$('attach-reference').onclick=()=>{if(!state.busy)$('reference-files').click();};
$('reference-files').onchange=()=>{selectReferenceFiles([...$('reference-files').files]);$('reference-files').value='';};
$('message').addEventListener('paste',event=>{
 if(state.busy||state.bootstrap?.data!=='study')return;
 const files=[...(event.clipboardData?.files||[])];
 if(files.length){event.preventDefault();selectReferenceFiles(files);}
});
const composer=document.querySelector('.composer');
composer.addEventListener('dragover',event=>{if(state.bootstrap?.data==='study')event.preventDefault();});
composer.addEventListener('drop',event=>{if(state.busy||state.bootstrap?.data!=='study')return;event.preventDefault();selectReferenceFiles([...event.dataTransfer.files]);});
const sendWithoutReference=send;
send=async function(){
 if(!referenceFiles.length)return sendWithoutReference();
 if(state.busy)return;
 if(!state.history?.session.question_course){notice('请先点击“@ 题库”选择课程，再上传参考题找相似题。',true);showQuestionMentions();return;}
 const query=$('message').value.trim();const form=new FormData();form.append('session',state.session);form.append('query',query||'找三道与上传参考题相似的题');
 for(const file of referenceFiles)form.append('files',file,file.name);
 const success=await runJob('/api/question-upload',form);
 if(success){$('message').value='';clearReferenceFiles();}
};
$('send').onclick=()=>send();
const busyWithoutReference=setBusy;
setBusy=function(value){busyWithoutReference(value);document.querySelectorAll('.reference-upload button,.reference-upload input,.reference-selection button').forEach(node=>node.disabled=value);};
const chooseWithoutReference=chooseSession;
chooseSession=async function(id){if(state.busy)return;if(id!==state.session)clearReferenceFiles();return chooseWithoutReference(id);};
