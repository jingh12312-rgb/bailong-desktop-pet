"""默认待机底部残影修复的边界，避免把局部处理变成全图阈值。"""
import os
import unittest
from unittest.mock import patch
from video_frames import clean_idle_footer,alpha_cleanup_tag


class IdleAlphaTests(unittest.TestCase):
    def test_only_the_confirmed_idle_clip_is_selected(self):
        with patch('sys.platform','linux'),patch.dict(os.environ,{'BAILONG_CLEAN_IDLE_SHADOW':'1'}):
            self.assertIsNotNone(alpha_cleanup_tag('/assets/idle.webm'))
            for filename in ('idle02.webm','18.webm','work01.webm','idle.webp'):
                self.assertIsNone(alpha_cleanup_tag(filename))
    def test_original_rendering_can_be_selected(self):
        with patch('sys.platform','linux'),patch.dict(os.environ,{'BAILONG_CLEAN_IDLE_SHADOW':'0'}):
            self.assertIsNone(alpha_cleanup_tag('idle.webm'))
    def test_solid_body_and_top_remain_unchanged(self):
        size=20;raw=bytearray(size*size*4)
        for i in range(0,len(raw),4):raw[i:i+4]=bytes((70,40,100,30))
        for y in range(16,18):raw[(y*size+8)*4:(y*size+8)*4+4]=bytes((75,45,110,255))
        result=clean_idle_footer(bytes(raw),size)
        self.assertEqual(result[:16*size*4],raw[:16*size*4])
        for i in range(0,len(raw),4):
            self.assertEqual(result[i:i+3],raw[i:i+3])
            if raw[i+3]>=224:self.assertEqual(result[i+3],raw[i+3])
        self.assertEqual(result[(19*size+8)*4+3],0)
        self.assertEqual(result[(18*size+8)*4+3],30)
    def test_cleanup_is_idempotent(self):
        size=20;raw=bytes((0,0,0,77))*(size*size)
        once=clean_idle_footer(raw,size);self.assertEqual(once,clean_idle_footer(once,size))
    def test_incomplete_frame_is_rejected(self):
        with self.assertRaises(ValueError):clean_idle_footer(b'bad',20)

if __name__=='__main__':unittest.main()
