"""Local conversation persistence and Codex stdio transport for the pet UI."""
import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

from quota import find_codex
from version import VERSION

PERSONA = ('你是GPT白龙娘桌宠中的白龙娘，是一位温柔、聪明、认真负责的白龙少女。'
           '用自然、轻柔、可爱的中文和用户交流，适度称呼用户为“主人”，偶尔有一点小得意或小傲娇。'
           '不要每句话都重复称呼，不滥用撒娇、拟声词、表情或夸张承诺。'
           '执行任务时保持严谨，先解决问题，保留代码、文件名、数据和技术解释的准确性。'
           '进度、困难和待确认的问题也用白龙娘的口吻说清楚，不编造过程，不把失败或中断说成完成。'
           '最终结果直接给出正文，客户端会单独显示“主人，完成啦！”，不必重复这句开场。'
           '角色口吻不改变用户的任务范围、访问权限或审批要求。')


class TaskCancelled(RuntimeError):
    pass


def data_directory():
    from platform_support import user_data
    return user_data()


class HistoryStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.path = self.directory / 'conversations.json'
        self.conversations = []
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data, list):
                    raise ValueError('invalid conversation list')
                self.conversations = data
            except (ValueError, OSError):
                raise RuntimeError('历史对话文件无法读取，请先备份本机 conversations.json；为避免覆盖，暂未写入新记录。')
        # A stopped process must never leave a task permanently displayed as running.
        for chat in self.conversations:
            for turn in chat.get('turns', []):
                if turn.get('status') == 'running':
                    turn['status'] = 'interrupted'
                    turn['error'] = '上次程序退出，任务未确认完成。'

    def new(self, cwd, mode='work'):
        chat = {'id': uuid.uuid4().hex, 'title': '新的对话', 'created': self.now(),
                'cwd': str(Path(cwd).resolve()), 'threadId': None, 'turns': [], 'mode':mode}
        self.conversations.append(chat)
        self.save()
        return chat

    @staticmethod
    def now():
        return datetime.now().isoformat(timespec='seconds')

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.conversations, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, self.path)


class CodexSession:
    """One worker owns the process; callbacks deliver only public protocol events."""
    def __init__(self, cwd, thread_id=None, cancel=None, emit=None, ask=None, mode='work'):
        self.cwd = str(Path(cwd).resolve())
        self.thread_id = thread_id
        self.cancel = cancel or threading.Event()
        self.emit = emit or (lambda kind, value: None)
        self.ask = ask or (lambda method, params: None)
        self.process = None
        self.messages = queue.Queue()
        self.sequence = 0
        self.turn_id = None
        self.active = False
        self.items = {}
        self.order = []
        self.summary_parts={}
        self.mode=mode
        self.initialized=False

    def send(self, value):
        self.process.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def start(self):
        frozen_windows = sys.platform == 'win32' and getattr(sys, 'frozen', False)
        if frozen_windows:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            self.process = subprocess.Popen([find_codex(), 'app-server'], cwd=self.cwd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        finally:
            if frozen_windows:
                ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
        process,messages=self.process,self.messages
        def read():
            try:
                for line in process.stdout:
                    try:
                        messages.put(json.loads(line))
                    except ValueError:
                        continue
            finally:
                messages.put(None)
        threading.Thread(target=read, daemon=True).start()

    def next(self, deadline):
        while time.monotonic() < deadline:
            if self.cancel.is_set():
                if self.thread_id and self.turn_id:
                    try:
                        self.send({'id': 'stop', 'method': 'turn/interrupt',
                                   'params': {'threadId': self.thread_id, 'turnId': self.turn_id}})
                    except (OSError, ValueError):
                        pass
                raise TaskCancelled('任务已停止，已完成的文件更改仍会保留。')
            try:
                message = self.messages.get(timeout=.1)
            except queue.Empty:
                continue
            if message is None:
                raise RuntimeError('Codex连接已结束，任务未确认完成。可以在历史对话中查看已有输出。')
            if 'method' in message and 'id' in message:
                self.answer_request(message)
                continue
            return message
        raise RuntimeError('Codex长时间未响应。任务未确认完成，请查看历史或稍后重试。')

    def answer_request(self, message):
        method, params = message['method'], message.get('params') or {}
        response = self.ask(method, params)
        if response is None:
            # Unknown tools are rejected rather than being silently approved.
            self.send({'id': message['id'], 'error': {'code': -32601, 'message': '此客户端暂不支持该交互；请改用已支持的工具。'}})
        else:
            self.send({'id': message['id'], 'result': response})

    def rpc(self, method, params, timeout=45):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while True:
            message = self.next(deadline)
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(message['error'].get('message', 'Codex请求失败'))
                return message.get('result') or {}
            self.event(message)

    def event(self, message):
        method, p = message.get('method', ''), message.get('params') or {}
        if self.thread_id and p.get('threadId') and p['threadId'] != self.thread_id:
            return
        if method == 'turn/started':
            self.turn_id = p.get('turn', {}).get('id')
        elif method == 'item/agentMessage/delta':
            item_id = p.get('itemId', 'message')
            if item_id not in self.order:
                self.order.append(item_id)
            self.items.setdefault(item_id, {'text': '', 'phase': None})['text'] += p.get('delta', '')
            self.emit('output', self.transcript())
        elif method in ('item/started', 'item/completed'):
            item = p.get('item') or {}
            kind = item.get('type')
            if kind == 'agentMessage':
                item_id = item.get('id', 'message')
                if item_id not in self.order:
                    self.order.append(item_id)
                self.items[item_id] = {'text': item.get('text', ''), 'phase': item.get('phase')}
                self.emit('output', self.transcript())
            elif kind == 'commandExecution':
                text = ('正在执行：' if method.endswith('started') else '执行结束：') + item.get('command', '')
                output = item.get('aggregatedOutput')
                if output:
                    text += '\n' + output[-12000:]
                self.emit('progress', text)
            elif kind == 'fileChange':
                paths = [c.get('path', '') for c in item.get('changes', [])]
                self.emit('progress', '文件更改：' + '、'.join(paths))
            elif kind == 'reasoning' and method=='item/completed':
                # Only the publicly supplied summary; never read raw content.
                summary=item.get('summary') or []
                if isinstance(summary,str):summary=[summary]
                for index,part in enumerate(summary):
                    text=part if isinstance(part,str) else part.get('text','')
                    self.summary_parts[(item.get('id','reasoning'),index)]=text
                self.emit('summary_update','\n\n'.join(self.summary_parts.values()))
        elif method == 'item/reasoning/summaryTextDelta':
            key=(p.get('itemId','reasoning'),p.get('summaryIndex',0))
            self.summary_parts[key]=self.summary_parts.get(key,'')+p.get('delta','')
            self.emit('summary_update','\n\n'.join(self.summary_parts.values()))
        elif method == 'turn/plan/updated':
            steps=[step.get('step','') for step in p.get('plan',[]) if step.get('step')]
            if steps:self.emit('progress','当前安排：'+'；'.join(steps))
        elif method == 'turn/completed':
            self.finished_turn = p.get('turn') or {}
        elif method == 'error' and not p.get('willRetry', False):
            self.last_error = (p.get('error') or {}).get('message', 'Codex任务失败')

    def transcript(self):
        return '\n\n'.join(self.items[i]['text'] for i in self.order if self.items[i]['text'])

    def final_text(self):
        final = [self.items[i]['text'] for i in self.order if self.items[i].get('phase') == 'final_answer']
        return '\n\n'.join(final) if final else (self.items[self.order[-1]]['text'] if self.order else '')

    def run(self, prompt):
        self.finished_turn = None
        self.last_error = None
        self.items={};self.order=[];self.summary_parts={};self.turn_id=None
        if self.process and self.process.poll() is not None:self.close()
        if not self.process:self.start()
        try:
            if not self.initialized:
                self.rpc('initialize', {'clientInfo': {'name': 'bailong_pet', 'title': 'GPT白龙娘动态桌宠', 'version': VERSION}})
                self.send({'method': 'initialized'})
                instruction=PERSONA+('当前为聊天模式：只根据对话直接交流，回答简短自然；不要查看或更改文件，不调用工具、不运行命令。如需实际操作，提醒主人切换工作模式。' if self.mode=='chat' else '')
                params = {'cwd': self.cwd, 'sandbox': 'read-only' if self.mode=='chat' else 'workspace-write', 'approvalPolicy': 'on-request',
                          'approvalsReviewer': 'user', 'developerInstructions': instruction}
                if self.thread_id:
                    params['threadId'] = self.thread_id
                    result = self.rpc('thread/resume', params)
                else:
                    result = self.rpc('thread/start', params)
                self.thread_id = result['thread']['id']
                self.initialized=True
                self.emit('thread', self.thread_id)
            else:
                # Discard notifications left over from the already completed turn.
                while not self.messages.empty():self.messages.get_nowait()
            result = self.rpc('turn/start', {'threadId': self.thread_id,
                'input': [{'type': 'text', 'text': prompt}], 'cwd': self.cwd,
                'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
                'summary':'concise',
                'sandboxPolicy': {'type':'readOnly'} if self.mode=='chat' else {'type': 'workspaceWrite', 'writableRoots': [self.cwd], 'networkAccess': False}})
            self.turn_id = result.get('turn', {}).get('id') or self.turn_id
            while self.finished_turn is None:
                self.event(self.next(time.monotonic() + 900))
            turn = self.finished_turn
            if turn.get('status') == 'interrupted':
                raise TaskCancelled('任务已停止，已有输出保存在历史对话中。')
            if turn.get('status') != 'completed':
                raise RuntimeError((turn.get('error') or {}).get('message') or self.last_error or '任务没有成功完成。')
            return {'threadId': self.thread_id, 'text': self.final_text() or '任务已完成，未返回文字结果。',
                    'transcript': self.transcript()}
        except Exception:
            self.close()
            raise

    def close(self):
        process = self.process
        if not process:
            return
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()
        self.process=None;self.initialized=False;self.messages=queue.Queue()
