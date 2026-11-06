const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
function ui() {
  const nodes = new Map();
  const make = () => ({hidden:false,disabled:false,value:'pushup',textContent:'',files:[],children:[],classList:{toggle(){}},append(n){this.children.push(n)},replaceChildren(){this.children=[]}});
  const document = {getElementById(id){if(!nodes.has(id))nodes.set(id,make());return nodes.get(id)},createElement:make};
  return {document,nodes};
}
test('live stop requests final report and does not queue another frame', async()=>{
  const {document,nodes}=ui();
  let socket, stopped=0, shown;
  class WS {
    static OPEN=1;
    constructor(){socket=this;this.readyState=1;this.sent=[];}
    send(value){this.sent.push(value)} close(){this.readyState=3}
  }
  Object.assign(document.getElementById('camera'),{videoWidth:640,videoHeight:480,play:async()=>{}});
  Object.assign(document.getElementById('canvas'),{getContext:()=>({drawImage(){}}),toBlob:cb=>cb('jpeg-frame')});
  const context = vm.createContext({document,WebSocket:WS,location:{protocol:'http:',host:'localhost:8000'},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){stopped++}}]})}},window:{addEventListener(){}},setInterval:()=>1,clearInterval(){},setTimeout:()=>1,clearTimeout(){},resetReport(){},showReport:r=>{shown=r}});
  vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8'),context);
  document.getElementById('liveTab').onclick();
  await document.getElementById('start').onclick();
  socket.onopen();
  await socket.onmessage({data:JSON.stringify({type:'ready'})});
  assert.equal(socket.sent[1],'jpeg-frame');
  document.getElementById('stop').onclick();
  assert.equal(JSON.parse(socket.sent.at(-1)).type,'stop');
  const count=socket.sent.length;
  await socket.onmessage({data:JSON.stringify({type:'result',analysis:{reps:1,angle:170,stage:'up',feedback:'Good form',person_detected:true},image:'jpeg'})});
  assert.equal(socket.sent.length,count);
  const report={outcome:'stopped',statistics:{counted_reps:1}};
  await socket.onmessage({data:JSON.stringify({type:'complete',report})});
  assert.equal(shown.statistics.counted_reps,1);
  assert.equal(nodes.get('start').disabled,false);
  assert.ok(stopped>0);
});
test('report rendering and text export include evidence and recommendations',()=>{
  const {document,nodes}=ui();
  const context=vm.createContext({document,window:{print(){}},URL:{},Blob,setTimeout});
  vm.runInContext(fs.readFileSync(path.join(root,'web/report.js'),'utf8'),context);
  context.report={exercise:'pushup',mode:'upload',outcome:'completed',created_at:'2026-11-06T12:00:00Z',summary:'Review your lowering phase.',statistics:{counted_reps:3,compared_reps:2,tracked_frames:90,frames:100,tracking_percent:90,mean_elbow_difference_deg:12,mean_bottom_difference_deg:15,mean_top_difference_deg:-2},observations:[{title:'Less elbow bend',observation:'2 of 2 reps flagged',suggestion:'Use a controlled comfortable range.'}],limitations:['Elbow comparison only.']};
  vm.runInContext('showReport(report)',context);
  assert.equal(nodes.get('reportPanel').hidden,false);
  assert.match(nodes.get('reportStats').textContent,/90\/100/);
  assert.equal(nodes.get('reportIssues').children[0].children[2].textContent,'What to change: Use a controlled comfortable range.');
  const text=vm.runInContext('reportText(report)',context);
  assert.match(text,/2 of 2 reps flagged/);
  assert.match(text,/Elbow comparison only/);
  vm.runInContext('resetReport()',context);
  assert.equal(nodes.get('reportPanel').hidden,true);
});
test('detailed report exports phase differences and renders rep rows',()=>{
  const {document,nodes}=ui();
  const context=vm.createContext({document,window:{print(){}},URL:{},Blob,setTimeout});
  vm.runInContext(fs.readFileSync(path.join(root,'web/report.js'),'utf8'),context);
  context.report={exercise:'pushup',mode:'upload',outcome:'completed',created_at:'2026-11-06T12:00:00Z',summary:'Summary',statistics:{counted_reps:1,compared_reps:1,tracked_frames:30,frames:30,tracking_percent:100,mean_elbow_difference_deg:2.7},observations:[],limitations:[],insights:['All compared reps stayed within checked thresholds.'],next_set_focus:['Maintain your comfortable range.'],reference:{source:'demo.mp4',bottom_angle:50,top_angle:170,cycles:5},repetitions:[{rep:1,end_frame:30,mean_difference_deg:2.7,lowering_difference_deg:2,rising_difference_deg:3,bottom_angle_deg:52,top_angle_deg:169,bottom_difference_deg:2,top_difference_deg:-1,range_note:'Within endpoint thresholds'}]};
  vm.runInContext('showReport(report)',context);
  assert.equal(nodes.get('reportRepTable').children[0].children[2].children.length,1);
  assert.equal(nodes.get('reportFocus').children[0].textContent,'Maintain your comfortable range.');
  assert.match(nodes.get('reportReference').textContent,/demo.mp4/);
  const text=vm.runInContext('reportText(report)',context);
  assert.match(text,/Lowering 2°/);
  assert.match(text,/Bottom 52° \(\+2°\)/);
});
