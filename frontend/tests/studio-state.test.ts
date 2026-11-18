import assert from 'node:assert/strict';
import {test} from 'node:test';
import {initialState, parsePracticeEvent, PendingAnswer, PracticeEvent, reduceStudio, validPending} from '../studio/state';

const turn = '1'.repeat(32), another = '2'.repeat(32);
const question = (turn_id = turn, seq = 1) => ({type: 'question' as const, id: 'index', turn_id, theme: 'MySQL', content: '请解释联合索引', seq, version: 1});
const pending: PendingAnswer = {type: 'answer', message_id: 'message-1', turn_id: turn, version: 1, text: '这是回答，不是题目'};
const snapshot = (extra = {}): PracticeEvent => ({type:'snapshot', version:1, state:'questioning', finished:false, current_question:question(), events:[question()], ...extra});
const event = (state: ReturnType<typeof initialState>, data: PracticeEvent) => reduceStudio(state, {type:'event',event:data});

test('a replay restores the authoritative question and an answer cannot become a follow-up question', () => {
  const state = event(initialState(), snapshot({events:[question(), {type:'answer_ack', turn_id:turn, message_id:'old', answer_text:'用户自己的答案', seq:2}]}));
  assert.equal(state.question?.content, '请解释联合索引');
  assert.equal(state.turns[0].answer, '用户自己的答案');
});
test('only a matching acknowledgement clears the pending submission and draft', () => {
  let state = event(initialState(), snapshot());
  state = reduceStudio({...state,text:pending.text}, {type:'submit',pending});
  state = event(state, {type:'answer_ack',turn_id:turn,message_id:'someone-else',answer_text:'别的提交',seq:2});
  assert.equal(state.pending?.message_id, pending.message_id);
  state = event(state, {type:'answer_ack',turn_id:turn,message_id:pending.message_id,answer_text:pending.text,seq:3});
  assert.equal(state.pending,null); assert.equal(state.text,''); assert.equal(state.phase,'waiting');
});
test('snapshot recovery reuses the exact message id only for the same turn and version', () => {
  const before = reduceStudio(event(initialState(), snapshot()), {type:'submit',pending});
  const resumed = event(before, snapshot());
  assert.deepEqual(resumed.pending,pending);
  const stale = event(before,snapshot({version:2,current_question:question(another)}));
  assert.equal(stale.pending,null); assert.equal(stale.question?.turn_id,another); assert.match(stale.recovery,/这是回答/);
});
test('a committed snapshot clears a lost acknowledgement without resubmission', () => {
  const before = reduceStudio(event(initialState(), snapshot()), {type:'submit',pending});
  const state = event(before,snapshot({version:2,events:[question(),{type:'answer_ack',turn_id:turn,message_id:pending.message_id,answer_text:pending.text,seq:2}]}));
  assert.equal(state.pending,null); assert.equal(state.turns[0].answer,pending.text);
});
test('late duplicate events do not roll the question or score back', () => {
  let state = event(initialState(),question(another,4));
  state = event(state,question(turn,1));
  assert.equal(state.question?.turn_id,another); assert.equal(state.sequence,4);
});
test('an unsent draft is retained separately when the authoritative question changes', () => {
  const before = {...event(initialState(),snapshot()),text:'旧草稿',code:'print(1)'};
  const state = event(before,question(another,2));
  assert.equal(state.text,''); assert.match(state.recovery,/旧草稿/); assert.equal(state.question?.turn_id,another);
});
test('cancelled and completed snapshots remain distinct terminal outcomes', () => {
  assert.equal(event(initialState(),snapshot({cancelled:true,state:'cancelled',current_question:null})).phase,'cancelled');
  assert.equal(event(initialState(),snapshot({finished:true,current_question:null})).phase,'finished');
});
test('identity changes remove all previously visible answers and drafts', () => {
  const before = {...event(initialState(),snapshot()),text:'私密草稿',recovery:'旧答案',pending};
  const state = reduceStudio(before,{type:'identity'});
  assert.equal(state.denied,true); assert.equal(state.turns.length,0); assert.equal(state.question,null);
  assert.equal(state.recovery,''); assert.equal(state.text,''); assert.equal(state.pending,null);
});
test('nested snapshots and invalid score payloads never enter the practice state', () => {
  assert.throws(() => parsePracticeEvent(snapshot({events:[snapshot()]})));
  assert.throws(() => parsePracticeEvent({type:'score',turn_id:turn,score:Infinity}));
  assert.throws(() => parsePracticeEvent({...question(),turn_id:'bad-id'}));
  assert.throws(() => parsePracticeEvent({...question(),seq:-1}));
  assert.equal(parsePracticeEvent(question()).type,'question');
});
test('browser pending data has bounded UTF-8 code, valid version and message id', () => {
  assert.ok(validPending(pending));
  assert.equal(validPending({...pending,version:true}),false);
  assert.equal(validPending({...pending,message_id:'../unsafe'}),false);
  assert.equal(validPending({...pending,code:'中'.repeat(6000)}),false);
  assert.equal(validPending({...pending,text:'a'.repeat(20001)}),false);
});
