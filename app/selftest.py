"""Offline smoke check executed by the shipped EXE, without a Python install."""
import os,json,time,traceback
from pathlib import Path

def run(root, output=None, model=None):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from platform_support import state_root
    output=Path(output) if output else state_root()/'selftest'
    output.mkdir(parents=True,exist_ok=True)
    report={'passed':False,'checks':[],'frozen':False}
    try:
        import sys
        from version import VERSION
        report.update(version=VERSION,frozen=bool(getattr(sys,'frozen',False)))
        if '--chat-only' in sys.argv:
            from chat_backend import CodexSession
            if not model:raise RuntimeError('真实对话自检必须通过 --test-model 显式指定模型。')
            folder=output/'对话自检任务';folder.mkdir(exist_ok=True)
            session=CodexSession(folder,mode='chat',model=model,effort='lowest')
            try:result=session.run('这是桌宠对话连接验收。不要使用工具，不要读写文件，只回复：白龙娘对话连接成功。')
            finally:session.close()
            assert '连接成功' in result['text'],result['text']
            report['checks'].append('EXE通过Codex后台任务收到真实回复；不记录账号、任务ID或额度数值')
            report['passed']=True
            report.update(model=model,effort=session.effort)
            (output/'对话接口检查报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            return 0
        if '--quota-only' in sys.argv:
            from quota import read_quota,quota_windows
            windows=quota_windows(read_quota(attempts=1,log_path=output/'quota-attempt.jsonl'))
            report['checks'].append(f'EXE只读额度接口成功，返回{len(windows)}个窗口；不记录账号或额度数值')
            report['passed']=True
            (output/'额度接口检查报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            return 0
        from pet import Pet,clamp_position
        from quota import quota_windows
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QPoint,QRect,QSize,QPointF
        from types import SimpleNamespace
        report.update(version=VERSION,frozen=bool(getattr(sys,'frozen',False)))
        app=QApplication([]);pet=Pet();pet.tick.stop()
        # Offline checks must not inherit a user's muted notification preferences.
        # Change instance fields only; do not overwrite their saved settings.
        pet.task_bubbles_disabled=False;pet.sound_disabled=True
        items=[pet.manifest['idle']]+pet.manifest.get('additionalIdleAnimations',[])+pet.variants+[pet.manifest[k] for k in ('dragAnimation','landingAnimation','quotaAnimation')]+[v for v in pet.work_slots if v]+pet.movement_slots
        for item in items:
            frames=pet.load(item);assert abs(len(frames)-round(item['durationMs']*item.get('fps',30 if item.get('number')=='03' and item.get('movementAngleRange') else 24)/1000))<=1
            assert frames[0].width()==pet.frame_size
        assert len(pet.variants)==15 and len(items)==24+len(pet.manifest.get('additionalIdleAnimations',[]))+len(pet.movement_slots);report['checks'].append(f'{len(items)}段动画可解码，含移动差分')
        assert (root/'app/sounds/click.wav').is_file()
        assert next(v for v in pet.variants if v['id']=='14') in items
        for item in items:
            assert 'renderScale' in item and 'renderOffset' in item
        report['checks'].append('全部动作尺寸校准字段齐全')
        pet.play(pet.manifest['quotaAnimation'],'quota');pet.started=time.monotonic()-4.1;pet.animate();assert pet.mode=='idle'
        report['checks'].append('查询动作只播一次')
        press=SimpleNamespace(button=lambda:__import__('PySide6.QtCore',fromlist=['Qt']).Qt.MouseButton.LeftButton,globalPosition=lambda:QPointF(200,200))
        move=SimpleNamespace(buttons=press.button,globalPosition=lambda:QPointF(240,230))
        pet.mousePressEvent(press);pet.mouseMoveEvent(move);assert pet.mode=='drag'
        pet.mouseReleaseEvent(press);assert pet.mode=='landing' and pet.current['durationMs']==2000
        report['checks'].append('拖拽与2秒落地切换正常')
        for position in [QPoint(-999,-999),QPoint(5000,5000)]:
            area=QRect(0,0,1920,1040);assert area.contains(QRect(clamp_position(position,QSize(256,256),area),QSize(256,256)))
        report['checks'].append('屏幕边界限制正常')
        assert quota_windows({'rateLimits':{'primary':{'usedPercent':25,'windowDurationMins':300}}})[0]['remaining']==75
        report['checks'].append('额度解析正常；未使用或捆绑任何账号')
        from chat_ui import ChatController
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            chat=ChatController(pet,folder);pet.chat=chat
            chat.toggle();app.processEvents()
            assert chat.composer.y()==pet.y()+pet.height()+8
            menu=pet.context_menu()
            assert [a.text() for a in menu.actions() if a.menu()]==['互动差分动画','工作差分动画','待机差分动画','移动差分']
            conversation=chat.store.new(folder)
            turn={'prompt':'离线界面检查','created':'selftest','status':'running','output':'','events':[]}
            conversation['turns'].append(turn);chat.active=conversation;chat.running_chat=conversation;chat.running_turn=turn
            chat.completed({'threadId':'offline-test','text':'检查结果\n'*30,'transcript':'检查结果\n'*30})
            assert any(b.text()=='详情' for b in pet.bubble.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton))
            assert chat.composer.size()==QSize(280,152)
            assert pet.mode=='task-celebration' and pet.current['id']=='18'
            assert len(pet.interaction_animations())==20
            chat.toggle() if not chat.enabled else None
            pet.play(pet.work_slots[1],'working');assert chat.composer.isVisible()
            pet.say('自动工作不显示台词');assert not pet.bubble.isVisible()
            pet.task_progress('主人，我正在理清思路…','公开进度摘要',lambda:None)
            assert pet.bubble.isVisible() and pet.bubble.is_task_progress
            report['checks'].append('成功庆祝一次、可滚动结果和详情、20项手动互动、工作时保留输入框与公开进度气泡正常')
            chat.shutdown();pet.chat=None
        report['checks'].append('对话开关、下方输入框、三类动画菜单、历史保存与长结果详情正常（离线检查）')
        menu=pet.context_menu();actions={a.text():a for a in menu.actions()}
        assert '隐藏桌宠' in actions and actions['全屏时自动隐藏'].isCheckable()
        pet.fullscreen_hidden=True;pet.apply_visibility()
        assert not pet.tick.isActive() and not pet.isVisible()
        pet.fullscreen_hidden=False;pet.apply_visibility();assert pet.isVisible()
        report['checks'].append('托盘菜单、全屏隐藏暂停与恢复正常（离线状态模拟）')
        pet.play(pet.idles[0],'idle');pet.grab().save(str(output/'检查预览.png'));pet.close()
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    name='对话接口检查报告.json' if '--chat-only' in __import__('sys').argv else ('额度接口检查报告.json' if '--quota-only' in __import__('sys').argv else '检查报告.json')
    (output/name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
