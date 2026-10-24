import json
from pathlib import Path
import tempfile
import threading
import unittest
from app.jsonl_writer import JsonlWriter


class BlockingSink:
    def __init__(self):self.entered=threading.Event();self.release=threading.Event();self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def write(self,text):
        self.entered.set()
        if not self.release.wait(2):raise TimeoutError('Test sink was not released')
        self.rows.append(text)
    def flush(self):pass


class JsonlWriterTests(unittest.TestCase):
    def test_disk_stall_does_not_block_control_producer(self):
        sink=BlockingSink();writer=JsonlWriter('unused',opener=lambda *a:sink)
        done=threading.Event()
        def control():
            for i in range(20):writer.write({'command':i})
            done.set()
        producer=threading.Thread(target=control);producer.start()
        try:
            self.assertTrue(sink.entered.wait(1))
            self.assertTrue(done.wait(.5),'Control producer blocked behind diagnostic disk I/O')
            self.assertFalse(sink.release.is_set())
        finally:sink.release.set();producer.join();writer.close()
        self.assertEqual([json.loads(r)['command'] for r in sink.rows],list(range(20)))

    def test_bounded_queue_reports_overflow_without_losing_accepted_records(self):
        sink=BlockingSink();writer=JsonlWriter('unused',max_pending=2,opener=lambda *a:sink)
        try:
            writer.write({'sequence':0});self.assertTrue(sink.entered.wait(1))
            writer.write({'sequence':1});writer.write({'sequence':2})
            with self.assertRaisesRegex(RuntimeError,'full'):writer.write({'sequence':3})
        finally:sink.release.set();writer.close()
        self.assertEqual([json.loads(r)['sequence'] for r in sink.rows],[0,1,2])

    def test_real_file_is_complete_and_ordered_when_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'record.jsonl';writer=JsonlWriter(path)
            for i in range(100):writer.write({'sequence':i,'payload':[1,2,3]})
            writer.close();writer.close()
            self.assertEqual([json.loads(l)['sequence'] for l in path.read_text().splitlines()],list(range(100)))
            with self.assertRaisesRegex(RuntimeError,'closed'):writer.write({})

    def test_writer_errors_are_explicit(self):
        def broken(*args):raise OSError('Disk unavailable')
        writer=JsonlWriter('unused',opener=broken);writer.thread.join(timeout=1)
        with self.assertRaisesRegex(RuntimeError,'Disk unavailable'):writer.write({})
        with self.assertRaisesRegex(RuntimeError,'Disk unavailable'):writer.close()
