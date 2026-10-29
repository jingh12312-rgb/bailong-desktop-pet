import unittest
from types import SimpleNamespace
from chat_backend import CodexSession


class FakeSession(CodexSession):
    def __init__(self,mode='work'):
        super().__init__('.',mode=mode)
        self.calls=[];self.starts=0
    def start(self):
        self.starts+=1;self.process=SimpleNamespace(poll=lambda:None)
    def send(self,value):pass
    def rpc(self,method,params,timeout=45):
        self.calls.append((method,params))
        if method.startswith('thread/'):
            return {'thread':{'id':'test-thread'}}
        if method=='turn/start':
            self.items={'reply':{'text':'回答','phase':'final_answer'}};self.order=['reply']
            self.finished_turn={'status':'completed'}
            return {'turn':{'id':'turn'}}
        return {}


class Tests(unittest.TestCase):
    def test_reuses_connection_and_resets_reply(self):
        s=FakeSession();self.assertEqual(s.run('一')['text'],'回答')
        self.assertEqual(s.run('二')['text'],'回答')
        self.assertEqual(s.starts,1)
        self.assertEqual([m for m,p in s.calls].count('initialize'),1)
        self.assertEqual([m for m,p in s.calls].count('thread/start'),1)
        self.assertEqual([m for m,p in s.calls].count('turn/start'),2)
    def test_chat_is_readonly_with_chat_instruction(self):
        s=FakeSession('chat');s.run('你好')
        thread=next(p for m,p in s.calls if m=='thread/start')
        turn=next(p for m,p in s.calls if m=='turn/start')
        self.assertEqual(thread['sandbox'],'read-only')
        self.assertEqual(turn['sandboxPolicy'],{'type':'readOnly'})
        self.assertIn('聊天模式',thread['developerInstructions'])

if __name__=='__main__':unittest.main()
