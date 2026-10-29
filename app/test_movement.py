import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import math
import random
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint
from PySide6.QtCore import QEvent, Qt, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from movement import plan_movement, movement_fraction
from pet import Pet

app=QApplication.instance() or QApplication([])


class RouteTests(unittest.TestCase):
    def test_downward_flight_is_shallower_than_upward(self):
        signs=set()
        for seed in range(200):
            (x,y),_=plan_movement((800,400),(0,0,1664,784),256,random.Random(seed),angle_range=[45,80],downward_angle_range=[45,65])
            angle=math.degrees(math.atan2(abs(y-400),abs(x-800)))
            self.assertGreater(angle,45);self.assertLess(angle,65 if y>400 else 80)
            signs.add(y>400)
        self.assertEqual(signs,{False,True})
    def test_flight_strict_angle_and_edges(self):
        for origin in [(0,0),(0,784),(1664,0),(1664,784),(800,400)]:
            directions=(1,) if origin[0]==0 else ((-1,) if origin[0]==1664 else (-1,1))
            for seed in range(80):
                route=plan_movement(origin,(0,0,1664,784),256,random.Random(seed),allowed_directions=directions,angle_range=[45,80])
                self.assertIsNotNone(route)
                (x,y),_=route;angle=math.degrees(math.atan2(abs(y-origin[1]),abs(x-origin[0])))
                self.assertGreater(angle,45);self.assertLess(angle,80)
                self.assertTrue(0<=x<=1664 and 0<=y<=784)

    def test_direction_distance_and_boundaries(self):
        # All corners, sides, center, and a monitor with negative coordinates.
        for bounds in [(0,0,1664,784),(-1920,-200,-256,584)]:
            l,t,r,b=bounds
            for origin in [(l,t),(r,t),(l,b),(r,b),((l+r)/2,(t+b)/2)]:
                for seed in range(80):
                    result=plan_movement(origin,bounds,256,random.Random(seed))
                    self.assertIsNotNone(result)
                    (x,y),mirrored=result;dx=x-origin[0];dy=y-origin[1]
                    self.assertLessEqual(abs(dy),abs(dx)+1e-7)
                    self.assertEqual(mirrored,dx<0)
                    self.assertTrue(l<=x<=r and t<=y<=b)
                    self.assertLessEqual(math.hypot(dx,dy),320.00001)
        self.assertIsNone(plan_movement((0,0),(0,0,0,0),256,random.Random(1)))

    def test_stationary_before_run_and_after_brake(self):
        self.assertEqual(movement_fraction(2999,3000,5583),0)
        self.assertEqual(movement_fraction(3000,3000,5583),0)
        self.assertAlmostEqual(movement_fraction(4291.5,3000,5583),.5)
        self.assertEqual(movement_fraction(5583,3000,5583),1)
        self.assertEqual(movement_fraction(9000,3000,5583),1)

    def test_near_edges_moves_inward(self):
        for seed in range(80):
            for origin in [(10,10),(1654,10),(10,774),(1654,774)]:
                (x,y),_=plan_movement(origin,(0,0,1664,784),256,random.Random(seed))
                self.assertGreater(x,origin[0]) if origin[0]<100 else self.assertLess(x,origin[0])
                self.assertGreater(y,origin[1]) if origin[1]<100 else self.assertLess(y,origin[1])

    def test_right_only_asset_cannot_run_left(self):
        self.assertIsNone(plan_movement((1654,400),(0,0,1664,784),256,allowed_directions=(1,)))
        for seed in range(20):
            (x,y),_=plan_movement((500,400),(0,0,1664,784),256,random.Random(seed),allowed_directions=(1,))
            self.assertGreater(x,500)

    def test_distance_matches_run_duration(self):
        origin=(800,400);bounds=(0,0,2200,1200)
        a,_=plan_movement(origin,bounds,256,random.Random(9),allowed_directions=(-1,),distance_scale=1)
        b,_=plan_movement(origin,bounds,256,random.Random(9),allowed_directions=(-1,),distance_scale=3333/2583)
        self.assertAlmostEqual(math.dist(origin,b)/math.dist(origin,a),3333/2583)


class MovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pet=Pet();cls.pet.tick.stop()

    @classmethod
    def tearDownClass(cls):
        cls.pet.close()

    def setUp(self):
        p=self.pet;p.undock();p.finish_movement();p.task_active=False;p.manual_hidden=False
        p.fullscreen_hidden=False;p.dragging=False;p.pointer_down=False;p.quota_inflight=False
        p.movement_ready_at=0;p.last_interaction=time.monotonic();p.click_timer.stop()
        p.next_leisure_at=time.monotonic()+15;p.next_leisure_group="idle"
        p.auto_movement_disabled=False
        p.play(p.idles[0],'idle');p.move(200,200);p.bubble.hide()

    def test_manual_edge_docking_and_recovery(self):
        p=self.pet;area=QApplication.primaryScreen().availableGeometry()
        for edge,point in [('left',QPoint(area.left(),area.top()+100)),('right',QPoint(area.right()+1-p.width(),area.top()+100))]:
            p.move(point);self.assertTrue(p.try_dock());self.assertEqual(p.dock_edge,edge)
            p.last_interaction=time.monotonic()-30;self.assertFalse(p.movement_allowed())
            self.assertLess(p.dock_rect().width(),p.width())
            p.grab();p.ensure_on_screen();self.assertEqual(p.dock_edge,edge)
            p.undock();self.assertIsNone(p.dock_edge)
        for y in (area.top(),area.bottom()+1-p.height()):
            p.move(area.center().x()-p.width()//2,y);self.assertFalse(p.try_dock())
        p.move(area.center()-QPoint(p.width()//2,p.height()//2))
        self.assertFalse(p.try_dock())

    def test_docked_idle_weights_and_pause_other_variants(self):
        p=self.pet;p.dock_edge='left';p.dock_started=time.monotonic()-1
        p.task_active=True
        with patch('pet.random.choices',return_value=[p.idles[0]]) as choose:
            p.idle();self.assertEqual(choose.call_args.kwargs['weights'],[7,3])
        current=p.current;p.play(p.movement_slots[0],'movement')
        self.assertIs(p.current,current);self.assertEqual(p.mode,'idle')
        p.grab();p.undock();p.task_active=False
        with patch('pet.random.choices',return_value=[p.idles[0]]) as choose:
            p.idle();self.assertEqual(choose.call_args.kwargs['weights'],[4,1])

    def test_docked_click_only_reverses_pose(self):
        from types import SimpleNamespace
        p=self.pet;p.dock_edge='left';p.dock_started=time.monotonic()-1
        click=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton)
        with patch.object(p,'single_click') as interact,patch.object(p,'quota') as quota,patch.object(p,'play_click_sound') as sound:
            p.mousePressEvent(click);self.assertFalse(getattr(p,'dock_exit',None))
            p.mouseReleaseEvent(click);self.assertFalse(p.click_timer.isActive());self.assertIsNone(p.last_click)
            self.assertTrue(p.dock_click_timer.isActive());p.dock_click_timer.timeout.emit()
            p.grab();start=p.dock_exit[0]
            with patch('pet.time.monotonic',return_value=start+.31):p.animate()
            self.assertIsNone(p.dock_edge);self.assertIsNone(p.dock_exit)
            interact.assert_not_called();quota.assert_not_called();sound.assert_not_called()

    def test_docked_double_click_queries_without_exiting(self):
        from types import SimpleNamespace
        p=self.pet;p.dock_edge='right';p.dock_started=time.monotonic()-1
        click=SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton)
        with patch.object(p,'quota') as quota,patch.object(p,'begin_undock') as leave:
            p.mousePressEvent(click);p.mouseReleaseEvent(click)
            self.assertTrue(p.dock_click_timer.isActive())
            p.mouseDoubleClickEvent(click);p.mouseReleaseEvent(click)
            quota.assert_called_once();leave.assert_not_called()
            self.assertEqual(p.dock_edge,'right');self.assertFalse(p.dock_click_timer.isActive())
            self.assertFalse(p.click_timer.isActive())

    def test_docked_quota_keeps_idle_animation(self):
        p=self.pet;p.dock_edge='left';p.dock_started=time.monotonic()-1;current=p.current
        old_worker=p.worker
        try:
            with patch('pet.QuotaWorker'),patch.object(p,'play') as play,patch.object(p,'play_click_sound'):
                p.quota();play.assert_not_called();self.assertIs(p.current,current)
                self.assertEqual(p.dock_edge,'left');self.assertTrue(p.bubble.isVisible())
                p.quota_ready([{'remaining':70,'name':'5小时','resetsAt':None}])
                self.assertEqual(p.dock_edge,'left');self.assertEqual(p.mode,'idle')
        finally:p.worker=old_worker;p.quota_inflight=False

    def test_preload_and_menu(self):
        p=self.pet;item=p.movement_slots[0]
        self.assertEqual(item['id'],'move02')
        self.assertEqual(len(p.pinned_frames[str(p.asset_path(item))]),264)
        menu=p.context_menu();sub=next(a.menu() for a in menu.actions() if a.text()=='移动差分')
        self.assertEqual(sub.actions()[0].text(),'02 · 跑步（向右）');menu.deleteLater()

    def test_manual_movement_during_work_resumes_work_afterwards(self):
        p=self.pet;p.task_active=True;item=p.movement_slots[0]
        self.assertFalse(p.movement_allowed())
        self.assertFalse(p.start_movement(item))
        with patch('pet.plan_movement',return_value=((320,200),False)):
            self.assertTrue(p.start_movement(item,manual=True))
        self.assertEqual(p.mode,'movement');self.assertTrue(p.task_active)
        work=p.regular_work_animations()
        with patch('pet.time.monotonic',return_value=p.started+item['durationMs']/1000+.01),patch('pet.random.choices',return_value=[('working',work)]),patch('pet.random.choice',return_value=work[0]):p.animate()
        self.assertEqual(p.mode,'working');self.assertTrue(p.task_active)

    def test_size_slider_live_bounds_and_saved_value(self):
        p=self.pet;previous=p.size_percent;menu=p.context_menu();action=next(a for a in menu.actions() if a.text()=='桌宠大小…');action.trigger();slider=p.size_slider
        self.assertEqual((slider.minimum(),slider.maximum()),(50,200))
        frames=p.frames;dialog_position=QPoint(p.size_dialog.pos())
        try:
            with patch.object(p.settings,'setValue') as save:
                slider.setValue(50);self.assertEqual((p.width(),p.height()),(128,128))
                slider.setValue(200);self.assertEqual((p.width(),p.height()),(512,512))
                self.assertEqual(p.size_dialog.pos(),dialog_position)
                self.assertFalse(p.size_dialog.frameGeometry().intersects(p.frameGeometry()))
                self.assertIs(p.frames,frames)
                self.assertEqual(p.pos(),p.constrained_position(p.pos()))
                save.assert_called_with('sizePercent',200)
                p.size_reset.click()
                self.assertEqual(p.size_dialog.pos(),dialog_position)
                self.assertEqual(slider.value(),100)
                self.assertEqual((p.width(),p.height()),(256,256))
                self.assertFalse(p.size_dialog.frameGeometry().intersects(p.frameGeometry()))
                save.assert_called_with('sizePercent',100)
                p.set_size_percent(previous)
        finally:p.size_dialog.hide();menu.deleteLater()

    def test_left_flight_waits_for_second_flap(self):
        p=self.pet;left=next(v for v in p.movement_slots if v['id']=='move03left');origin=QPoint(p.pos())
        with patch('pet.plan_movement',return_value=((320,150),True)):
            p.start_movement(left,manual=True)
        p.advance_movement(3.124);self.assertEqual(p.pos(),origin)
        p.advance_movement(4);self.assertNotEqual(p.pos(),origin)

    def test_flight_assets_and_direction_parameters(self):
        p=self.pet;self.assertEqual(len(p.movement_slots),6)
        flights=[v for v in p.movement_slots if v['number']=='03']
        self.assertEqual(len(flights),2)
        for item in flights:
            self.assertEqual(item['durationMs'],9100)
            self.assertEqual(len(p.pinned_frames[str(p.asset_path(item))]),273)
            with patch('pet.plan_movement',return_value=((320,200),False)) as planner:
                self.assertTrue(p.start_movement(item,manual=True))
                self.assertEqual(planner.call_args.kwargs['angle_range'],[45,80])
                self.assertEqual(planner.call_args.kwargs['allowed_directions'],(-1,) if item['sourceFacing']=='left' else (1,))
            self.assertFalse(p.movement_mirrored)

    def test_disable_switch_and_manual_preview(self):
        p=self.pet;p.last_interaction=time.monotonic()-30
        with patch.object(p.settings,'setValue') as save:
            p.set_auto_movement_disabled(True)
            save.assert_called_once_with('autoMovementDisabled',True)
        p.last_interaction=time.monotonic()-30
        self.assertFalse(p.movement_allowed())
        menu=p.context_menu()
        toggle=next(a for a in menu.actions() if a.text()=='禁用自移动')
        self.assertTrue(toggle.isCheckable());self.assertTrue(toggle.isChecked())
        with patch('pet.plan_movement',return_value=((320,200),False)):
            self.assertTrue(p.start_movement(p.movement_slots[0],manual=True))
        with patch.object(p.settings,'setValue'):
            p.set_auto_movement_disabled(False)
        self.assertIsNone(p.movement_plan)
        menu.deleteLater()

    def test_look_around_finishes_before_due_automatic_action(self):
        p=self.pet;p.play(p.idles[1],'idle')
        current=p.current;started=p.started;duration=current['durationMs']/1000
        p.last_interaction=started-30;p.next_leisure_at=0
        for group in ('idle','movement'):
            p.next_leisure_group=group
            with patch('pet.time.monotonic',return_value=started+duration-.05),patch.object(p,'try_leisure') as schedule:
                p.animate();schedule.assert_not_called();self.assertIs(p.current,current)
        with patch('pet.time.monotonic',return_value=started+duration+.01),patch.object(p,'try_leisure',return_value=True) as schedule:
            p.animate();schedule.assert_called_once()

    def test_leisure_alternates_and_disabled_movement_keeps_idles(self):
        p=self.pet;now=time.monotonic();p.last_interaction=now-16
        p.next_leisure_at=now+1;p.next_leisure_group='idle'
        self.assertFalse(p.try_leisure())
        p.next_leisure_at=0
        with patch('pet.random.choice',return_value=p.extra_idles[0]) as choose:
            self.assertTrue(p.try_leisure());choose.assert_called_once_with(p.extra_idles)
        self.assertEqual(p.mode,'leisure');self.assertEqual(p.next_leisure_group,'movement')
        p.next_leisure_at=0
        with patch.object(p,'start_movement',return_value=True) as start:
            self.assertTrue(p.try_leisure());start.assert_called_once()
        self.assertEqual(p.next_leisure_group,'idle')
        p.auto_movement_disabled=True;p.next_leisure_at=0;p.next_leisure_group='movement'
        with patch.object(p,'start_movement') as start:
            self.assertTrue(p.try_leisure());start.assert_not_called()
        self.assertEqual(p.mode,'leisure');self.assertEqual(p.next_leisure_group,'idle')
        p.note_interaction();self.assertFalse(p.try_leisure())
        p.next_leisure_at=0;p.last_interaction=now-16;p.dock_edge='left'
        self.assertFalse(p.try_leisure());p.dock_edge=None
        p.task_active=True;self.assertFalse(p.try_leisure());p.task_active=False

    def test_timed_translation_brake_and_cooldown(self):
        p=self.pet;origin=QPoint(p.pos());target=origin+QPoint(120,-40)
        with patch('pet.plan_movement',return_value=((target.x(),target.y()),False)):
            self.assertTrue(p.start_movement(dict(p.movement_slots[0],moveStartMs=3000,moveStopMs=5583,durationMs=9042)))
        p.advance_movement(2.9);self.assertEqual(p.pos(),origin)
        p.advance_movement(4.2915);self.assertEqual(p.pos(),origin+QPoint(60,-20))
        p.advance_movement(5.583);self.assertEqual(p.pos(),target)
        p.advance_movement(8.8);self.assertEqual(p.pos(),target)
        with patch('pet.time.monotonic',return_value=p.started+9.05):
            p.animate();self.assertEqual(p.mode,'idle')
            self.assertFalse(p.movement_allowed(p.movement_ready_at-.01))
            p.last_interaction=p.movement_ready_at-30
            self.assertTrue(p.movement_allowed(p.movement_ready_at))
            self.assertTrue(p.start_movement(p.movement_slots[0],manual=True))

    def test_left_facing_and_interruption_no_teleport(self):
        p=self.pet;origin=QPoint(p.pos());target=origin-QPoint(100,20)
        with patch('pet.plan_movement',return_value=((target.x(),target.y()),True)):
            p.start_movement(p.movement_slots[0])
        self.assertFalse(p.movement_mirrored)
        p.advance_movement(4.2);position=QPoint(p.pos())
        p.note_interaction()
        self.assertEqual(p.pos(),position);self.assertEqual(p.mode,'idle')
        self.assertFalse(p.movement_mirrored);self.assertIsNone(p.movement_plan)
        self.assertGreater(p.movement_ready_at,time.monotonic()+9)

    def test_hidden_pause_has_no_jump(self):
        p=self.pet
        with patch('pet.plan_movement',return_value=((320,200),False)):
            p.start_movement(p.movement_slots[0])
        start=p.started
        with patch('pet.time.monotonic',return_value=start+4):
            p.advance_movement(4);before=QPoint(p.pos())
            p.fullscreen_hidden=True;p.apply_visibility()
        with patch('pet.time.monotonic',return_value=start+24):
            p.fullscreen_hidden=False;p.apply_visibility();p.tick.stop();p.animate()
            self.assertEqual(p.pos(),before)
            self.assertAlmostEqual(p.started,start+20)

    def test_left_clip_and_edge_fallback(self):
        p=self.pet;left=next(v for v in p.movement_slots if v['sourceFacing']=='left')
        origin=QPoint(p.pos());target=origin-QPoint(100,0)
        with patch('pet.plan_movement',return_value=((target.x(),target.y()),True)) as planner:
            self.assertTrue(p.start_movement(left,manual=True))
            self.assertEqual(planner.call_args.kwargs['allowed_directions'],(-1,))
            self.assertAlmostEqual(planner.call_args.kwargs['distance_scale'],3333/2583)
        self.assertFalse(p.movement_mirrored)
        p.advance_movement(1.9);self.assertEqual(p.pos(),origin)
        p.advance_movement(5.25);self.assertEqual(p.pos(),target)
        p.finish_movement();p.movement_ready_at=0;p.last_interaction=time.monotonic()-30
        p.next_leisure_group='movement';p.next_leisure_at=0
        with patch.object(p,'start_movement',side_effect=[False,True]) as start:
            p.idle();self.assertEqual(start.call_count,2)

    def test_passive_mouse_events_do_not_interrupt_manual_run(self):
        p=self.pet
        with patch('pet.plan_movement',return_value=((320,200),False)):
            self.assertTrue(p.start_movement(p.movement_slots[0],manual=True))
        started=p.started;item=p.current;plan=p.movement_plan
        for kind in (QEvent.Type.MouseMove,QEvent.Type.MouseButtonRelease):
            event=QMouseEvent(kind,QPointF(20,20),QPointF(220,220),Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
            p.eventFilter(p,event)
            self.assertEqual(p.mode,'movement');self.assertIs(p.current,item)
            self.assertEqual(p.started,started);self.assertEqual(p.movement_plan,plan)
        p.refresh_tray_menu();self.assertEqual(p.mode,'movement')
        from types import SimpleNamespace
        p.mouseReleaseEvent(SimpleNamespace(button=lambda:Qt.MouseButton.LeftButton))
        self.assertEqual(p.mode,'movement')
        p.note_interaction();self.assertEqual(p.mode,'idle')


if __name__=='__main__':unittest.main()
