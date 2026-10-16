import json
import tempfile
import unittest
from pathlib import Path
from lupa import lua51

ROOT=Path(__file__).resolve().parents[1]

def logger(directory):
    lua=lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.globals().FP_Generated=lua.table_from({"log_dir":str(directory).replace("\\","/"),
        "log_path":str(directory/"aggregate.log").replace("\\","/"),"build":"test","episode":"test"})
    lua.execute((ROOT/"src/fp_log.lua").read_text())
    return lua

class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def records(self):
        return [json.loads(line) for p in self.path.glob("*.jsonl") for line in p.read_text().splitlines()]
    def test_error_contains_message_and_trace(self):
        lua=logger(self.path)
        lua.execute('FP_Log.try("test_error",function() error("deliberate failure") end)')
        record=self.records()[-1]
        self.assertEqual(record['level'],'error')
        self.assertIn('deliberate failure',record['message'])
        self.assertIn('stack traceback',record['message'])
    def test_retail_empty_traceback_keeps_original_error(self):
        lua=logger(self.path)
        lua.execute('debug.traceback=function() return "" end; FP_Log.try("error",function() error("retain me") end)')
        self.assertIn('retain me',self.records()[-1]['message'])
    def test_sessions_do_not_overwrite_each_other(self):
        logger(self.path);logger(self.path)
        self.assertEqual(len(list(self.path.glob('*.jsonl'))),2)
    def test_json_control_characters_roundtrip(self):
        lua=logger(self.path)
        value='Quote " slash \\ newline\n tab\t nul\0'
        lua.globals().value=value
        lua.execute('FP_Log.write("info","escaped",{message=value})')
        self.assertEqual(self.records()[-1]['message'],value)
    def test_repeated_errors_are_counted_without_spam(self):
        lua=logger(self.path)
        lua.execute('for i=1,101 do FP_Log.error("same","failure") end')
        errors=[r for r in self.records() if r['level']=='error']
        self.assertEqual(len(errors),4)
        self.assertEqual(errors[-1]['occurrences'],100)
    def test_rotation_preserves_previous_records(self):
        lua=logger(self.path)
        lua.execute('FP_Log.bytes=2*1024*1024; FP_Log.write("info","rotated")')
        self.assertEqual(len(list(self.path.glob('*.jsonl'))),2)
