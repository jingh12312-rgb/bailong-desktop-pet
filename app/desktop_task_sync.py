"""Read-only observer of public Codex desktop task records. No model requests."""
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from PySide6.QtCore import QObject,QTimer

UUID=re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
ACTIVE={'inProgress','running','pending','waitingForApproval','waitingForInput'}
PUBLIC_TYPES=('agentMessage','commandExecution','fileChange','mcpToolCall','webSearch','imageGeneration','imageView')

def problem_summary(detail,exit_code=None):
    raw=str(detail or '')
    try:
        parsed=json.loads(raw)
        if isinstance(parsed,dict):raw=str(parsed.get('message') or parsed.get('error') or '')
    except (ValueError,TypeError):pass
    lines=[s.strip() for s in raw.splitlines() if s.strip() and not re.search(r'authorization|api.?key|password|token|secret',s,re.I)]
    matches=[s for s in lines if re.search(r'error|exception|failed|timeout|timed out|denied|no such|错误|失败|不存在|无法|拒绝',s,re.I)]
    excerpt='\n'.join(matches[-2:])[:500]
    low=excerpt.lower()
    if re.search(r'timeout|timed out|超时',low):reason='请求超时'
    elif re.search(r'connect|network|failed to fetch|name_not_resolved|网络',low):reason='网络连接异常'
    elif re.search(r'no such file|filenotfound|cannot find|不存在',low):reason='文件或路径不存在'
    elif re.search(r'no module named|modulenotfound',low):reason='缺少需要的程序模块'
    elif re.search(r'permission|access.*denied|权限|拒绝',low):reason='权限不足或访问被拒绝'
    elif re.search(r'assertion|failed \(|test.*fail|检查.*未通过',low):reason='执行检查未通过'
    else:reason='工具执行异常'+(f'（返回码 {exit_code}）' if exit_code is not None else '')
    return '主人，这一步没有成功。\n原因：'+reason+('\n错误摘要：'+excerpt if excerpt else '\n暂时没有更详细的错误信息。')+'\n任务是否完成会另外通知你。'

def readonly(path):
    connection=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=.15)
    connection.execute('PRAGMA query_only=ON')
    return connection

class DesktopTaskReader:
    def __init__(self,home=None):
        self.home=Path(home or os.environ.get('CODEX_HOME') or Path.home()/'.codex')
    def snapshots(self,excluded=()):
        paths=(self.home/'state_5.sqlite',self.home/'thread_history_1.sqlite')
        if not all(p.is_file() for p in paths):return []
        state=readonly(paths[0]);history=readonly(paths[1]);result=[]
        try:
            threads=state.execute("SELECT id,rollout_path,title,cwd FROM threads WHERE archived=0 AND updated_at>=? AND (thread_source='user' OR thread_source IS NULL) AND source NOT LIKE '%subagent%' ORDER BY updated_at DESC LIMIT 40",(int(time.time())-86400,)).fetchall()
            for logical,path,title,cwd in threads:
                ids=UUID.findall(str(path));actual=ids[-1] if ids else logical
                if logical in excluded or actual in excluded:continue
                rows=history.execute('SELECT turn_id,status,error_json,started_at,completed_at FROM thread_turns WHERE thread_id=? ORDER BY started_at DESC LIMIT 3',(actual,)).fetchall()
                for turn,status,error,started,completed in rows:
                    # Project only public messages and tool status, never reasoning,
                    # tool arguments, successful command output or encrypted content.
                    items=history.execute("SELECT item_id,item_type,json_extract(item_json,'$.phase'),json_extract(item_json,'$.text'),json_extract(item_json,'$.status'),json_extract(item_json,'$.exitCode'),json_extract(item_json,'$.error'),json_extract(item_json,'$.questions'),CASE WHEN json_extract(item_json,'$.status')='failed' OR json_extract(item_json,'$.exitCode') NOT IN (0) THEN substr(json_extract(item_json,'$.aggregatedOutput'),-2500) ELSE NULL END FROM thread_items WHERE thread_id=? AND turn_id=? AND item_type IN ('agentMessage','commandExecution','fileChange','mcpToolCall','webSearch','imageGeneration','imageView') ORDER BY rollout_ordinal DESC LIMIT 200",(actual,turn)).fetchall()[::-1]
                    messages=[];final='';alerts=[];steps=[]
                    for item_id,typ,phase,text,item_status,exit_code,item_error,questions,failed_output in items:
                        if typ=='agentMessage' and phase in ('commentary','final_answer','final',None):
                            if text:
                                if phase in ('final_answer','final'):final=str(text)
                                else:messages.append(str(text));alerts=[]
                            if questions and questions not in ('[]','null'):alerts.append((item_id,'主人，这一步需要你回答或确认，请到 Codex 查看。'))
                        elif typ!='agentMessage':
                            if item_status in ('waitingForApproval','waitingForInput','requiresApproval'):
                                alerts.append((item_id,'主人，这一步需要你确认权限或补充信息，请到 Codex 查看。'))
                            elif item_status=='failed' or item_error or (exit_code not in (None,0)):
                                alerts.append((item_id,problem_summary(item_error or failed_output,exit_code)))
                            elif item_status in ('inProgress','running'):
                                steps.append({'commandExecution':'正在执行操作','fileChange':'正在修改文件','mcpToolCall':'正在调用工具','webSearch':'正在查阅资料','imageGeneration':'正在生成图片','imageView':'正在查看图片'}.get(typ,'正在处理'))
                    result.append(dict(key=actual+':'+turn,thread=logical,actual=actual,turn=turn,title=title,cwd=cwd,status=status,error=error,started=started or 0,completed=completed,messages=messages,final=final,alerts=alerts,step=steps[-1] if steps else ''))
        finally:state.close();history.close()
        return sorted(result,key=lambda r:r['started'])

class DesktopTaskSync(QObject):
    def __init__(self,pet,reader=None,clock=time.time):
        super().__init__(pet);self.pet=pet;self.reader=reader or DesktopTaskReader();self.clock=clock
        self.born=clock();self.known={};self.running=set();self.bootstrap=True;self.errors=0
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.poll)
    def start(self):self.timer.start();self.poll()
    def stop(self):self.timer.stop()
    def excluded(self):
        controller=self.pet.chat
        if controller:return {c.get('threadId') for c in controller.store.conversations if not c.get('desktopSync')}
        from chat_backend import data_directory
        try:
            chats=json.loads((data_directory()/'conversations.json').read_text(encoding='utf-8'))
            return {c.get('threadId') for c in chats if not c.get('desktopSync')}
        except (OSError,ValueError):return set()
    def details(self,key):
        record=self.known.get(key,{});cid=record.get('chat_id')
        controller=self.pet.chat_controller()
        if controller:controller.open_history(cid)
    def _progress(self,key,title,text,details,repeat=False):
        record=self.known.get(key)
        if record is None:return False
        signature=(str(title).strip(),str(text).strip())
        seen=record.setdefault('seen',set())
        times=record.setdefault('repeat_times',{})
        serial=json.dumps(signature,ensure_ascii=False)
        if signature in seen:
            if not repeat:return False
            if self.clock()-times.get(serial,record['started_notice'])<300:return False
        seen.add(signature)
        if repeat:times[serial]=self.clock()
        turn=record.get('turn')
        if turn is not None:
            turn['syncNotices']=[list(s) for s in seen]
            turn['syncRepeatTimes']=times
            if self.pet.chat:self.pet.chat.store.save()
        self.pet.task_progress(title,text,details)
        return True
    def history(self,snapshot,record):
        controller=self.pet.chat_controller()
        if not controller:return
        if not record.get('chat_id'):
            chat=next((c for c in controller.store.conversations if c.get('desktopTurnKey')==snapshot['key']),None)
            if chat is None:chat=controller.store.new(snapshot['cwd'])
            chat['desktopSync']=True;chat['desktopTurnKey']=snapshot['key']
            chat['threadId']=snapshot['thread'];chat['title']='Codex同步 · '+str(snapshot['title'])[:45]
            if not chat['turns']:chat['turns'].append({'prompt':'来自 Codex：'+str(snapshot['title']),'created':controller.store.now(),'status':'running','output':'','events':[]})
            record.update(chat_id=chat['id'],chat=chat,turn=chat['turns'][-1])
            record['seen']={tuple(s) for s in record['turn'].get('syncNotices',[])}
            record['repeat_times']=record['turn'].get('syncRepeatTimes',{})
        turn=record['turn'];turn['events']=snapshot['messages'][-100:]+[text for _,text in snapshot['alerts']]
        turn['output']=snapshot['final'];turn['result']=snapshot['final']
        turn['status']='running' if snapshot['status'] in ACTIVE else snapshot['status']
        if snapshot['error']:turn['error']=str(snapshot['error'])
        controller.store.save();controller.refresh_list()
        if controller.active and controller.active['id']==record['chat_id']:controller.render()
    def poll(self):
        try:self._poll()
        except (OSError,ValueError,RuntimeError,sqlite3.Error):
            # Qt callbacks must not leak an exception into the paint/event loop.
            # A persistence problem must never be reported as task success.
            if self.running:self._progress(next(iter(self.running)),'主人，同步记录暂时没保存好。','任务还没有确认完成，请到 Codex 查看最新状态。',lambda k=next(iter(self.running)):self.details(k),repeat=True)
    def _poll(self):
        if not self.pet.settings.value('syncCodexTasks',True,type=bool):return
        try:rows=self.reader.snapshots(self.excluded());self.errors=0
        except (OSError,sqlite3.Error,ValueError):
            self.errors+=1
            if self.errors>=10 and self.running:self._progress(next(iter(self.running)),'主人，同步暂时遇到一点问题。','暂时读不到 Codex 的最新状态，我不会把它当作任务完成。请到 Codex 确认。',lambda k=next(iter(self.running)):self.details(k),repeat=True)
            return
        for snapshot in rows:
            key=snapshot['key'];active=snapshot['status'] in ACTIVE
            if key not in self.known:
                if not active and (self.bootstrap or snapshot['started']<self.born):continue
                if active and snapshot['started']<self.born-86400:continue
                record=self.known[key]={'thread':snapshot['thread'],'started_notice':self.clock(),'fingerprint':None,'alerts':set(),'finished':False,'last_notice':self.clock(),'last_change':self.clock(),'last_alert':0}
                self.history(snapshot,record)
                if active:
                    for old_key,old in self.known.items():
                        if old_key!=key and old.get('thread')==snapshot['thread']:old.pop('warning',None)
                    was_running=bool(self.running);self.running.add(key)
                    if not was_running and not (self.pet.chat and self.pet.chat.running_turn):self.pet.task_started()
                    self._progress(key,'主人，我收到啦！','这就认真帮你处理 Codex 里的任务。',lambda k=key:self.details(k))
            record=self.known[key]
            fingerprint=(snapshot['status'],tuple(snapshot['messages']),snapshot['final'],str(snapshot['error']),tuple(snapshot['alerts']),snapshot['step'])
            if fingerprint==record['fingerprint']:
                warning=record.get('warning')
                if warning:self._progress(key,warning[0],warning[1],lambda k=key:self.details(k),repeat=True)
                if active and self.clock()-record['last_notice']>=300:
                    quiet=self.clock()-record['last_change']>=90
                    if not warning:self._progress(key,'主人，我还在留意进展…',('已经有一会儿没有新进度了；任务还没有报告完成，你可以到 Codex 看看是否需要处理。' if quiet else (snapshot['messages'][-1] if snapshot['messages'] else (snapshot['step'] or 'Codex 尚未报告完成，我会继续留意最新进展。'))),lambda k=key:self.details(k),repeat=True)
                    record['last_notice']=self.clock()
                continue
            record['fingerprint']=fingerprint;record['last_change']=self.clock();self.history(snapshot,record)
            latest=snapshot['messages'][-1] if snapshot['messages'] else ''
            if latest!=record.get('warning_progress','') or snapshot['status']=='completed':record.pop('warning',None)
            for aid,text in snapshot['alerts']:
                if aid not in record['alerts']:
                    record['alerts'].add(aid);record['warning']=('主人，有个情况要告诉你。',text);record['warning_progress']=latest
                    self._progress(key,'主人，有个情况要告诉你。',text,lambda k=key:self.details(k),repeat=True);record['last_notice']=self.clock();record['last_alert']=self.clock()
            if active:
                if not record.get('warning') and self.clock()-record['started_notice']>=3.5 and self.clock()-record['last_alert']>=8:
                    text=snapshot['messages'][-1] if snapshot['messages'] else snapshot['step']
                    if text:self._progress(key,'主人，我忙到这一步啦…',text,lambda k=key:self.details(k));record['last_notice']=self.clock()
            elif not record['finished']:
                record['finished']=True;self.running.discard(key)
                own_running=bool(self.pet.chat and self.pet.chat.running_turn)
                if not self.running and not own_running:self.pet.task_finished()
                details=lambda k=key:self.details(k)
                if snapshot['status']=='completed':self.pet.task_completed(snapshot['final'] or 'Codex 已报告本轮任务完成，点击详情查看记录。',details)
                else:
                    text=('任务已中断。' if snapshot['status']=='interrupted' else '这次处理遇到了异常。')+('\n'+str(snapshot['error']) if snapshot['error'] else '\n请到 Codex 查看并处理。')
                    record['warning']=('主人，任务还没有完成。',text);record['warning_progress']=latest
                    self._progress(key,'主人，任务还没有完成。',text,details,repeat=True)
        self.bootstrap=False
