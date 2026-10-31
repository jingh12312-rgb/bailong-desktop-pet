"""真实 XCB 窗口验收。仅在显式 --gui-test 参数下运行，产物写入指定目录。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


def run(root, output, live_model=None):
    if not output or not os.environ.get('BAILONG_DATA_DIR'):
        raise RuntimeError('界面验收需要 --self-test-output 和隔离的 BAILONG_DATA_DIR。')
    from linux_runtime import acquire_instance
    lock=acquire_instance()
    if lock is None:raise RuntimeError('已有桌宠实例，取消界面验收。')
    from PySide6.QtCore import Qt,QPoint,QTimer
    from PySide6.QtGui import QCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QLabel,QPushButton,QCheckBox,QFileDialog,QInputDialog
    from pet import Pet
    from chat_ui import ChatController
    from chat_backend import HistoryStore
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs,True)
    app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False)
    if app.platformName()!='xcb':raise RuntimeError('本验收要求真实 XCB 窗口，不能使用 offscreen。')
    report={'passed':False,'backend':app.platformName(),'checks':[],
            'input':'Qt QTest 真实 XCB 窗口事件；另含 xdotool 原生点击和拖动',
            'screens':[{'width':s.geometry().width(),'height':s.geometry().height(),'dpr':s.devicePixelRatio()} for s in app.screens()]}
    pet=None;pointer=QCursor.pos();number=0
    def check(name,condition=True,**details):
        if not condition:raise AssertionError(name+' '+str(details))
        report['checks'].append({'name':name,**details});print(name,flush=True)
    def capture(name,widget):
        nonlocal number
        app.processEvents();widget.repaint();QTest.qWait(60)
        number+=1;path=output/f'{number:02d}-{name}.png'
        if not widget.grab().save(str(path)):raise RuntimeError('截图写入失败')
    def menu_action(text):
        errors=[]
        def select():
            try:
                menu=app.activePopupWidget()
                action=next(a for a in menu.actions() if a.text()==text)
                capture('menu',menu)
                QTest.mouseClick(menu,Qt.MouseButton.LeftButton,pos=menu.actionGeometry(action).center())
            except BaseException as error:
                errors.append(error)
                if app.activePopupWidget():app.activePopupWidget().close()
        QTimer.singleShot(180,select)
        QTest.mouseClick(pet,Qt.MouseButton.RightButton,pos=QPoint(pet.width()//2,pet.height()//2))
        if errors:raise errors[0]
        QTest.qWait(120)
    try:
        pet=Pet();pet.settings.setValue('syncCodexTasks',False)
        pet.desktop_sync.reader.home=output/'empty-codex-home'
        pet.move(pet.constrained_position(QPoint(500,300)));pet.show();pet.raise_();QTest.qWait(350)
        capture('startup',pet)
        check('真实桌面启动与托盘可用',pet.isVisible() and pet.tray.isVisible(),tray_available=pet.tray.isSystemTrayAvailable())
        native=app.primaryScreen().grabWindow(int(pet.winId()))
        check('XWayland 原生窗口截图',not native.isNull())
        native.save(str(output/'native-pet.png'))
        image=pet.frames[0].toImage()
        alpha=[image.pixelColor(x,y).alpha() for y in range(0,image.height(),4) for x in range(0,image.width(),4)]
        check('桌宠渲染保留透明通道',min(alpha)==0 and max(alpha)==255)
        # XTest events reach the real window through XWayland, rather than calling handlers.
        rendered=pet.grab().toImage();mask=pet.mask()
        point=next(QPoint(x,y) for y in range(pet.height()//3,pet.height()-5,4)
                   for x in range(pet.width()//3,pet.width()*2//3,4)
                   if (mask.isEmpty() or mask.contains(QPoint(x,y))) and rendered.pixelColor(x,y).alpha()>200)
        global_point=pet.mapToGlobal(point)
        subprocess.run(['xdotool','mousemove',str(global_point.x()),str(global_point.y()),'click','1'],check=True,timeout=5)
        QTest.qWait(450);check('原生单击互动',pet.mode=='variant');capture('native-click',pet.bubble)
        old=pet.pos();subprocess.run(['xdotool','mousemove',str(global_point.x()),str(global_point.y()),'mousedown','1'],check=True,timeout=5)
        QTest.qWait(80)
        subprocess.run(['xdotool','mousemove',str(global_point.x()+70),str(global_point.y()+40)],check=True,timeout=5)
        QTest.qWait(80)
        subprocess.run(['xdotool','mouseup','1'],check=True,timeout=5)
        QTest.qWait(100);check('原生拖动与落地',pet.pos()!=old and pet.mode=='landing');capture('landing',pet)
        QTest.qWait(2050)
        menu_action('桌宠大小…');dialog=pet.size_dialog
        pet.size_slider.setFocus();QTest.keyClick(pet.size_slider,Qt.Key.Key_End)
        check('桌宠放大到200%',pet.size_percent==200);capture('size-200',dialog)
        QTest.keyClick(pet.size_slider,Qt.Key.Key_Home);check('桌宠缩小到50%',pet.size_percent==50)
        QTest.mouseClick(pet.size_reset,Qt.MouseButton.LeftButton);check('桌宠大小恢复默认',pet.size_percent==100)
        dialog.accept()
        menu_action('对话框大小…');dialog=pet.bubble_settings_dialog
        pet.bubble_slider.setFocus();QTest.keyClick(pet.bubble_slider,Qt.Key.Key_End)
        check('气泡放大到150%',pet.bubble_percent==150)
        mute=dialog.findChild(QCheckBox);QTest.mouseClick(mute,Qt.MouseButton.LeftButton)
        check('关闭任务气泡',pet.task_bubbles_disabled)
        QTest.mouseClick(mute,Qt.MouseButton.LeftButton);pet.bubble_slider.setValue(100)
        capture('bubble-settings',dialog);dialog.accept()
        menu_action('禁用音效');check('音效关闭',pet.sound_disabled)
        menu_action('禁用音效');check('音效恢复',not pet.sound_disabled)
        menu_action('隐藏桌宠');check('手动隐藏暂停动画',not pet.isVisible() and not pet.tick.isActive())
        pet.refresh_tray_menu();menu=pet.tray_menu;menu.popup(QPoint(500,250));QTest.qWait(150)
        capture('tray-restore-menu',menu)
        action=next(a for a in menu.actions() if a.text()=='显示桌宠')
        QTest.mouseClick(menu,Qt.MouseButton.LeftButton,pos=menu.actionGeometry(action).center());QTest.qWait(150)
        check('托盘菜单恢复桌宠',pet.isVisible() and pet.tick.isActive())
        from linux_support import fullscreen_capability
        if not fullscreen_capability()[0]:
            menu=pet.context_menu();item=next(a for a in menu.actions() if a.text().startswith('全屏时自动隐藏'))
            check('不支持的全屏功能明确禁用',not item.isEnabled() and '不支持' in item.text());menu.deleteLater()
        for edge in ('left','right'):
            area=app.primaryScreen().availableGeometry();pet.move(area.left() if edge=='left' else area.right()+1-pet.width(),300)
            check(edge+'吸边状态',pet.try_dock() and pet.dock_edge==edge)
            QTest.qWait(350);capture(edge+'-dock',pet)
            pet.begin_undock();QTest.qWait(650);check(edge+'展开',pet.dock_edge is None)
        captions=['短句','今日份喜欢，已经送到主人的桌面啦。','收到啦，主人！让我先把你的嘱咐认真记下来。',
                  '完成啦！给主人悄悄贴一颗小星星！','眷属印记亮起来啦！从今天起，我就是主人的白龙眷属了。']
        for scale in (50,75,100,125,150):
            pet.set_bubble_percent(scale)
            for text in captions:
                pet.say(text);app.processEvents()
                def caption_fits():
                    return all(label.height()>=label.heightForWidth(label.width()) and pet.bubble.rect().contains(label.geometry()) for label in pet.bubble.findChildren(QLabel))
                deadline=time.monotonic()+1
                while not caption_fits() and time.monotonic()<deadline:QTest.qWait(10)
                if not caption_fits():
                    raise AssertionError('气泡窗口未完成换行高度调整：'+text)
                for label in pet.bubble.findChildren(QLabel):
                    if label.height()<label.heightForWidth(label.width()):raise AssertionError('气泡文字高度不足：'+text)
            capture('caption-scale-'+str(scale),pet.bubble)
        check('中文换行气泡25种文本与缩放组合不裁切')
        pet.set_bubble_percent(100)
        pet.move(pet.constrained_position(QPoint(500,300)));pet.dismiss_bubble()
        # All 35 assets are rendered into the real window; these selections are programmatic.
        items=pet.idles+pet.extra_idles+pet.variants+[x for x in pet.work_slots if x]+pet.movement_slots
        items += [pet.manifest[k] for k in ('dragAnimation','landingAnimation','quotaAnimation')]
        for item in items:
            pet.play(item,'variant');capture('animation-'+item['id'],pet)
        check('35段动画在真实窗口渲染',len(items)==35,count=len(items),selection='programmatic')
        pet.play(pet.idles[0],'idle');pet.dismiss_bubble()
        before=pet.pos();pet.start_movement(pet.movement_slots[0],manual=True);QTest.qWait(8500)
        check('移动动作实际运行',pet.pos()!=before);pet.finish_movement()
        menu_action('打开对话模式');controller=pet.chat
        check('对话输入框显示',controller.composer.isVisible());capture('composer',controller.composer)
        if live_model:
            controller.model=live_model;controller.effort='lowest';controller.mode='chat'
            prompt='这是桌宠连接验收。不要使用工具，不要读写文件，只回复：白龙娘对话连接成功。'
            controller.composer.editor.setPlainText(prompt)
            QTest.mouseClick(controller.composer.send_button,Qt.MouseButton.LeftButton)
            check('真实任务进入运行状态',controller.busy)
            deadline=time.monotonic()+120
            while controller.busy and time.monotonic()<deadline:QTest.qWait(100)
            check('Luna真实回复完成',not controller.busy and controller.active['turns'][-1]['status']=='completed')
            check('真实回复内容', '连接成功' in controller.active['turns'][-1].get('result',''))
            report['live_model']=live_model;report['live_effort']=controller.worker.session.effort
            capture('luna-completed',pet.bubble)
        else:
            if getattr(sys,'frozen',False):
                # Verify the bundled client's real Node transport without inference.
                from chat_backend import CodexSession
                from version import VERSION
                probe=CodexSession(output)
                try:
                    probe.start()
                    probe.rpc('initialize',{'clientInfo':{'name':'bailong_pet','version':VERSION}})
                    probe.send({'method':'initialized'})
                    catalog=probe.rpc('model/list',{'includeHidden':False})
                    check('便携包真实Codex握手（未发送模型请求）',isinstance(catalog.get('data'),list) and bool(catalog['data']))
                finally:probe.close()
            conversation=controller.store.new(output/'mock-workspace');controller.active=conversation
            turn={'prompt':'离线界面测试','created':'test','status':'running','output':'','events':[]}
            conversation['turns'].append(turn);controller.running_chat=conversation;controller.running_turn=turn
            controller.receive('output','离线进度');controller.preview_reply();capture('offline-progress',pet.bubble)
            controller.completed({'threadId':'offline-gui','text':'离线长结果\n'*60,'transcript':'离线长结果\n'*60})
            check('离线成功状态与庆祝动画',turn['status']=='completed' and pet.mode=='task-celebration')
            capture('offline-completed',pet.bubble)
        details=next(b for b in pet.bubble.findChildren(QPushButton) if b.text()=='详情')
        QTest.mouseClick(details,Qt.MouseButton.LeftButton);QTest.qWait(150)
        check('详情与历史窗口',controller.window.isVisible() and bool(controller.window.view.toPlainText()))
        capture('history',controller.window)
        check('历史确实写入隔离目录',bool(HistoryStore(controller.store.directory).conversations))
        controller.window.close();check('关闭历史不退出桌宠',pet.isVisible())
        # Exercise the directory chooser without touching a real project.
        folder=output/'selected-workspace';folder.mkdir(exist_ok=True)
        def select_folder():
            dialog=app.activeModalWidget()
            if isinstance(dialog,QFileDialog):
                dialog.setDirectory(str(folder.parent));dialog.selectFile(str(folder))
                from PySide6.QtWidgets import QLineEdit
                field=dialog.findChild(QLineEdit,'fileNameEdit')
                if field:field.setText(str(folder))
                watchdog=QTimer(dialog);watchdog.setSingleShot(True);watchdog.timeout.connect(dialog.reject);watchdog.start(2000)
                capture('folder-dialog',dialog);dialog.accept()
        QTimer.singleShot(200,select_folder)
        QTest.mouseClick(controller.composer.folder_button,Qt.MouseButton.LeftButton)
        check('Qt目录选择器与任务目录切换',Path(controller.active['cwd'])==folder)
        # Approval/input pages use an isolated worker queue and never execute tools.
        import queue,threading
        from types import SimpleNamespace
        real_worker=controller.worker
        fixture=SimpleNamespace(cancel=threading.Event(),responses=queue.Queue())
        controller.worker=fixture
        try:
            def reject_approval():
                dialog=app.activeModalWidget();capture('approval-dialog',dialog)
                button=next(b for b in dialog.findChildren(QPushButton) if b.text()=='拒绝')
                QTest.mouseClick(button,Qt.MouseButton.LeftButton)
            QTimer.singleShot(200,reject_approval)
            controller.request('item/commandExecution/requestApproval',{'reason':'隔离验收：不执行命令','command':'echo fixture'})
            check('操作审批窗口可拒绝',fixture.responses.get_nowait()['decision']=='decline')
            def answer_input():
                dialog=app.activeModalWidget();capture('input-dialog',dialog);dialog.accept()
            QTimer.singleShot(200,answer_input)
            controller.request('item/tool/requestUserInput',{'questions':[{'id':'fixture','header':'界面验收','question':'请选择隔离测试选项','options':[{'label':'测试选项A'},{'label':'测试选项B'}]}]})
            check('澄清问题窗口可回答',fixture.responses.get_nowait()['answers']['fixture']['answers']==['测试选项A'])
        finally:controller.worker=real_worker
        # Failure and interruption are UI fixtures, never additional model requests.
        for cancelled in (False,True):
            turn={'prompt':'隔离失败场景','created':'test','status':'running','output':'','events':[]}
            controller.active['turns'].append(turn);controller.running_chat=controller.active;controller.running_turn=turn
            controller.failed('隔离测试：连接已中断',cancelled)
            check('中断状态' if cancelled else '失败状态',turn['status']==('interrupted' if cancelled else 'failed'))
            capture('interrupted' if cancelled else 'failure',pet.bubble)
        controller.hide();pet.play(pet.idles[0],'idle')
        menu_action('退出桌宠');QTest.qWait(150)
        check('菜单退出关闭窗口和托盘',not pet.isVisible() and not pet.tray.isVisible())
        report['passed']=True
    except BaseException:
        report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        if pet:
            if pet.chat:pet.chat.shutdown()
            pet.desktop_sync.stop();pet.tick.stop();pet.visibility_timer.stop();pet.tray.hide();pet.bubble.hide();pet.hide()
        QCursor.setPos(pointer)
        (output/'gui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        lock.close();app.quit()
    return 0 if report['passed'] else 1
