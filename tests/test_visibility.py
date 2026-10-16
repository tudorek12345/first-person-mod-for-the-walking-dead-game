from pathlib import Path
import unittest

from lupa import lua51

ROOT=Path(__file__).resolve().parents[1]


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.lua=lua51.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((ROOT/'tests/fake_engine.lua').read_text())
        self.lua.execute('''
          Callback_CameraChanged=Fake.callback()
          function EasyContainer(value)
            return {getn=function() return value and #value or 0 end}
          end
          FP_Log={try=function(label,fn) return pcall(fn) end,
            write=function(level,event,fields)
              Fake.logs[#Fake.logs+1]={event=event,fields=fields}
            end}
          local hide=AgentHide
          Fake.hideCalls={}
          AgentHide=function(a,b,...)
            if Fake.failHide then error("native hide failed") end
            Fake.hideCalls[#Fake.hideCalls+1]={agent=a,hidden=b,n=select("#",...),...}
            return hide(a,b)
          end
          actor=Fake.new_agent("Kenny",{},Vector(1,0,4)); actor.hasHead=true
        ''')
        self.lua.execute((ROOT/'src/fp_visibility.lua').read_text())
        self.lua.execute('''
          function cameraHide(a,hidden)
            FP_Visibility.scoped(function() AgentHide(a,hidden) end)
          end
        ''')

    def test_camera_hide_before_attachment_is_compensated_then_restored(self):
        self.lua.execute('''
          cameraHide(actor,true); assert(actor.hidden)
          FP_Visibility.update(true,Fake.scene,Fake.player)
          assert(not actor.hidden and FP_Visibility.stats().overridden==1)
          FP_Visibility.restore()
          assert(actor.hidden and FP_Visibility.stats().overridden==0)
        ''')

    def test_optional_native_arguments_preserve_nil_positions_and_count(self):
        self.lua.execute('''
          AgentHide(actor,true,nil,"sentinel",nil)
          local call=Fake.hideCalls[#Fake.hideCalls]
          assert(call.hidden and call.n==3 and call[1]==nil and call[2]=="sentinel" and call[3]==nil)
          AgentHide(actor,false)
          assert(Fake.hideCalls[#Fake.hideCalls].n==0)
        ''')

    def test_scoped_override_and_restore_preserve_recursive_argument(self):
        self.lua.execute('''
          FP_Visibility.update(true,Fake.scene,Fake.player)
          FP_Visibility.camera_call(function() AgentHide(actor,true,true) end)
          local override=Fake.hideCalls[#Fake.hideCalls]
          assert(not override.hidden and override.n==1 and override[1]==true)
          FP_Visibility.restore()
          local restored=Fake.hideCalls[#Fake.hideCalls]
          assert(restored.hidden and restored.n==1 and restored[1]==true)
        ''')

    def test_delayed_override_and_restore_preserve_explicit_false_recursive_argument(self):
        self.lua.execute('''
          FP_Visibility.camera_call(function() AgentHide(actor,true,false) end)
          FP_Visibility.update(true,Fake.scene,Fake.player)
          local override=Fake.hideCalls[#Fake.hideCalls]
          assert(not override.hidden and override.n==1 and override[1]==false)
          FP_Visibility.restore()
          local restored=Fake.hideCalls[#Fake.hideCalls]
          assert(restored.hidden and restored.n==1 and restored[1]==false)
        ''')

    def test_failed_scoped_native_hide_preserves_previous_restoration_ownership(self):
        self.lua.execute('''
          FP_Visibility.update(true,Fake.scene,Fake.player)
          FP_Visibility.camera_call(function() AgentHide(actor,true,true) end)
          Fake.failHide=true
          local ok=pcall(function()
            FP_Visibility.camera_call(function() AgentHide(actor,false,false) end)
          end)
          assert(not ok and FP_Visibility.stats().overridden==1)
          Fake.failHide=false; FP_Visibility.restore()
          local restored=Fake.hideCalls[#Fake.hideCalls]
          assert(actor.hidden and restored.hidden and restored.n==1 and restored[1]==true)
        ''')

    def test_camera_hide_after_attachment_is_suppressed(self):
        self.lua.execute('''
          FP_Visibility.update(true,Fake.scene,Fake.player)
          cameraHide(actor,true); assert(not actor.hidden)
          cameraHide(actor,false); FP_Visibility.restore(); assert(not actor.hidden)
        ''')

    def test_story_hide_after_override_always_wins(self):
        self.lua.execute('''
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          AgentHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          assert(actor.hidden and not FP_Visibility.camera_hidden(actor))
          FP_Visibility.restore(); assert(actor.hidden)
        ''')

    def test_story_show_revokes_later_camera_restore(self):
        self.lua.execute('''
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          AgentHide(actor,false); FP_Visibility.restore(); assert(not actor.hidden)
        ''')

    def test_player_body_stays_hidden_but_reports_camera_only_reason(self):
        self.lua.execute('''
          FP_Visibility.update(true,Fake.scene,Fake.player)
          cameraHide(Fake.player,true)
          assert(Fake.player.hidden and FP_Visibility.camera_hidden(Fake.player))
          AgentHide(Fake.player,true)
          assert(not FP_Visibility.camera_hidden(Fake.player))
        ''')

    def test_exclusive_variants_remain_hidden(self):
        self.lua.execute('''
          actor.base["Visibility - Show Only in Cameras"]={"shot_variant"}
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          assert(actor.hidden and not FP_Visibility.camera_hidden(actor))
        ''')

    def test_chore_visibility_proxy_prevents_override_and_restoration(self):
        self.lua.execute('''
          actor.runtime["Transient Visibility Proxy"]=0
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          assert(actor.hidden)
          actor.runtime["Transient Visibility Proxy"]=-1
          cameraHide(actor,true); assert(not actor.hidden)
          actor.runtime["Transient Visibility Proxy"]=0
          actor.hidden=true
          FP_Visibility.update(true,Fake.scene,Fake.player)
          FP_Visibility.restore(); assert(actor.hidden)
        ''')

    def test_native_visibility_change_revokes_override(self):
        self.lua.execute('''
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          actor.runtime["Runtime: Visible"]=false; actor.hidden=true
          FP_Visibility.update(true,Fake.scene,Fake.player)
          assert(actor.hidden and FP_Visibility.stats().overridden==0)
        ''')

    def test_scope_failure_does_not_capture_following_story_call(self):
        self.lua.execute('''
          local ok=pcall(function() FP_Visibility.scoped(function() error("callback") end) end)
          assert(not ok)
          AgentHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          assert(actor.hidden and FP_Visibility.stats().tracked==0)
        ''')

    def test_loader_restores_callback_add_after_failure(self):
        self.lua.execute('''
          local add=Callback_CameraChanged.Add
          local ok=pcall(function() FP_Visibility.load_original(function() error("load failed") end) end)
          assert(not ok and Callback_CameraChanged.Add==add)
        ''')

    def test_only_original_module_callback_gets_camera_scope(self):
        self.lua.execute('''
          local other=Fake.new_agent("Carley",{},Vector())
          FP_Visibility.load_original(function()
            Callback_CameraChanged:Add(function() AgentHide(actor,true) end)
          end)
          Callback_CameraChanged:Add(function() AgentHide(other,true) end)
          FP_Visibility.update(true,Fake.scene,Fake.player)
          Callback_CameraChanged:Run()
          assert(not actor.hidden and other.hidden)
        ''')

    def test_scene_change_restores_old_overrides_and_prunes_old_records(self):
        self.lua.execute('''
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          FP_Visibility.update(true,{name="other_scene"},nil)
          assert(actor.hidden and FP_Visibility.stats().tracked==0)
        ''')

    def test_failed_restore_retains_ownership_and_retries_without_new_camera_work(self):
        self.lua.execute('''
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          Fake.failHide=true; FP_Visibility.restore()
          assert(FP_Visibility.stats().pending==1 and not actor.hidden)
          Fake.failHide=false
          for i=1,3 do FP_Visibility.tick(.1) end
          assert(actor.hidden and FP_Visibility.stats().pending==0)
        ''')

    def test_destroyed_agent_does_not_retain_visibility_state(self):
        self.lua.execute('''
          cameraHide(actor,true); FP_Visibility.update(true,Fake.scene,Fake.player)
          AgentDestroy(actor); FP_Visibility.tick(.1)
          assert(FP_Visibility.stats().tracked==0)
        ''')

    def test_sampling_only_emits_changes_and_has_bounded_batch(self):
        self.lua.execute('''
          for i=1,100 do local a=Fake.new_agent("extra_"..i,{},Vector()); a.hasHead=true end
          FP_Visibility.sample(Fake.scene,Fake.player)
          local states=0
          for _,r in ipairs(Fake.logs) do if r.event=="visibility_state" then states=states+1 end end
          assert(states==64)
          FP_Visibility.sample(Fake.scene,Fake.player)
          local nextStates=0
          for _,r in ipairs(Fake.logs) do if r.event=="visibility_state" then nextStates=nextStates+1 end end
          assert(nextStates==102)
          FP_Visibility.sample(Fake.scene,Fake.player)
          local finalStates=0
          for _,r in ipairs(Fake.logs) do if r.event=="visibility_state" then finalStates=finalStates+1 end end
          assert(finalStates==nextStates)
        ''')


if __name__=='__main__': unittest.main(verbosity=2)
