from pathlib import Path
import unittest

from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((ROOT / "src/fp_cleanup.lua").read_text())
        self.lua.execute('''
          logs={}
          logger={try=function(label,fn) return pcall(fn) end,
            write=function(level,event,fields)
              logs[#logs+1]={event=event,fields=fields,level=level}
            end}
          queue=FP_Cleanup.new(logger)
        ''')

    def test_success_executes_immediately_without_retaining_task(self):
        self.lua.execute('''
          local ok,value=queue:run("one",function() return 42 end)
          assert(ok and value==42 and queue:pending()==0 and queue:blocked()==0)
        ''')

    def test_transient_error_retries_after_delay_and_releases_ownership(self):
        self.lua.execute('''
          local calls=0
          queue:run("restore",function() calls=calls+1; if calls==1 then error("busy") end end)
          assert(queue:pending()==1 and calls==1)
          queue:tick(.24); assert(calls==1)
          queue:tick(.01); assert(calls==2 and queue:pending()==0)
          assert(logs[1].event=="cleanup_queued" and logs[#logs].event=="cleanup_completed")
        ''')

    def test_persistent_error_has_bounded_backoff_and_retains_task(self):
        self.lua.execute('''
          local calls=0
          queue:run("restore",function() calls=calls+1; error("busy") end)
          queue:tick(.25); assert(calls==2)
          queue:tick(.99); assert(calls==2)
          queue:tick(.01); assert(calls==3)
          queue:tick(3); assert(calls==4)
          queue:tick(1000); assert(calls==4)
          assert(queue:pending()==1 and queue:blocked()==1)
          assert(logs[#logs].event=="cleanup_blocked")
        ''')

    def test_reset_rearms_blocked_work_without_dropping_closure(self):
        self.lua.execute('''
          local failed=true; local value=0
          queue:run("restore",function() if failed then error("busy") end; value=71 end)
          for i=1,4 do queue:tick(10) end
          assert(queue:blocked()==1)
          failed=false; queue:reset()
          assert(queue:pending()==1 and queue:blocked()==0)
          queue:tick(0)
          assert(value==71 and queue:pending()==0)
        ''')

    def test_independent_failures_retry_fifo_without_blocking_successful_work(self):
        self.lua.execute('''
          local calls={}; local failed=true
          queue:run("first",function() calls[#calls+1]="first"; if failed then error("busy") end end)
          queue:run("second",function() calls[#calls+1]="second"; if failed then error("busy") end end)
          queue:run("third",function() calls[#calls+1]="third" end)
          assert(table.concat(calls,",")=="first,second,third")
          failed=false; queue:tick(.25)
          assert(table.concat(calls,",")=="first,second,third,first,second")
          assert(queue:pending()==0)
          assert(logs[1].fields.cleanup_id<logs[2].fields.cleanup_id)
        ''')

    def test_reset_never_discards_waiting_tasks(self):
        self.lua.execute('''
          local failed=true
          queue:run("restore",function() if failed then error("busy") end end)
          queue:reset(); assert(queue:pending()==1)
          failed=false; queue:tick(.25); assert(queue:pending()==0)
        ''')

    def test_logging_failure_does_not_abort_other_cleanup_tasks(self):
        self.lua.execute('''
          logger.write=function() error("broken logger") end
          local calls=0
          queue:run("fail",function() error("busy") end)
          queue:run("success",function() calls=calls+1 end)
          queue:tick(.25)
          assert(calls==1 and queue:pending()==1)
        ''')

    def test_nested_enqueue_survives_compaction_without_reentrant_retry(self):
        self.lua.execute('''
          local initial=true; local calls=0
          queue:run("outer",function()
            if initial then initial=false; error("busy") end
            queue:run("inner",function() calls=calls+1; error("inner busy") end)
          end)
          queue:tick(.25)
          assert(calls==1 and queue:pending()==1)
          queue:tick(.25); assert(calls==2 and queue:pending()==1)
        ''')

    def test_invalid_or_negative_time_cannot_skip_backoff(self):
        self.lua.execute('''
          local calls=0
          queue:run("restore",function() calls=calls+1; error("busy") end)
          queue:tick(-20); queue:tick(0/0); queue:tick(math.huge); queue:tick("bad")
          assert(calls==1)
          queue:tick(.25); assert(calls==2)
        ''')


if __name__ == "__main__":
    unittest.main(verbosity=2)
