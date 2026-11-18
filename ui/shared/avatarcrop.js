function avatarCropEditor(find, canEdit) {
  const area=find('#avatar-crop'),canvas=find('#avatar-canvas'),preview=find('#avatar-preview');
  const zoom=find('#avatar-zoom'),horizontal=find('#avatar-x'),vertical=find('#avatar-y');
  let bitmap=null,cx=0,cy=0,generation=0,drag=null;
  const side=()=>Math.min(bitmap.width,bitmap.height)/Number(zoom.value);
  function paint(){
    if(!bitmap)return;
    const size=side();cx=Math.max(size/2,Math.min(bitmap.width-size/2,cx));cy=Math.max(size/2,Math.min(bitmap.height-size/2,cy));
    const draw=target=>{const ctx=target.getContext('2d');ctx.clearRect(0,0,target.width,target.height);ctx.fillStyle='#ffffff';ctx.fillRect(0,0,target.width,target.height);ctx.drawImage(bitmap,cx-size/2,cy-size/2,size,size,0,0,target.width,target.height);};
    draw(canvas);draw(preview);
    horizontal.value=bitmap.width===size?50:Math.round((cx-size/2)/(bitmap.width-size)*100);
    vertical.value=bitmap.height===size?50:Math.round((cy-size/2)/(bitmap.height-size)*100);
    find('#avatar-zoom-value').textContent=Number(zoom.value).toFixed(2).replace(/0$/, '')+'×';
  }
  function clear(){
    generation++;bitmap?.close();bitmap=null;drag=null;area.hidden=true;
    canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);
    preview.getContext('2d').clearRect(0,0,preview.width,preview.height);
  }
  async function load(file){
    clear();const version=generation;
    const image=await createImageBitmap(file);
    if(version!==generation){image.close();return false;}
    if(image.width<32||image.height<32||image.width>4096||image.height>4096){image.close();throw new Error('图片尺寸应为32–4096像素');}
    bitmap=image;cx=image.width/2;cy=image.height/2;zoom.value=1;area.hidden=false;paint();return true;
  }
  zoom.addEventListener('input',()=>{if(canEdit())paint();});
  horizontal.addEventListener('input',()=>{if(bitmap&&canEdit()){cx=side()/2+(bitmap.width-side())*Number(horizontal.value)/100;paint();}});
  vertical.addEventListener('input',()=>{if(bitmap&&canEdit()){cy=side()/2+(bitmap.height-side())*Number(vertical.value)/100;paint();}});
  find('#avatar-reset').addEventListener('click',()=>{if(bitmap&&canEdit()){zoom.value=1;cx=bitmap.width/2;cy=bitmap.height/2;paint();}});
  canvas.addEventListener('pointerdown',event=>{if(!bitmap||!canEdit())return;drag={id:event.pointerId,x:event.clientX,y:event.clientY};canvas.setPointerCapture(event.pointerId);});
  canvas.addEventListener('pointermove',event=>{
    if(!drag||drag.id!==event.pointerId||!bitmap||!canEdit())return;
    const rect=canvas.getBoundingClientRect(),size=side();
    cx-=(event.clientX-drag.x)/rect.width*size;cy-=(event.clientY-drag.y)/rect.height*size;
    drag.x=event.clientX;drag.y=event.clientY;paint();
  });
  for(const kind of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(kind,()=>{drag=null;});
  async function blob(){
    if(!bitmap)throw new Error('请先选择并裁剪图片');
    const size=Number(find('#avatar-size').value);
    if(![128,256,512].includes(size))throw new Error('请选择有效的头像尺寸');
    const output=document.createElement('canvas');output.width=output.height=size;
    const length=side(),ctx=output.getContext('2d');ctx.fillStyle='#ffffff';ctx.fillRect(0,0,size,size);ctx.imageSmoothingQuality='high';ctx.drawImage(bitmap,cx-length/2,cy-length/2,length,length,0,0,size,size);
    const data=await new Promise(resolve=>output.toBlob(resolve,'image/png'));
    if(!data)throw new Error('裁剪图片生成失败，请重新选择');
    return {data,size};
  }
  return {load,clear,blob};
}
