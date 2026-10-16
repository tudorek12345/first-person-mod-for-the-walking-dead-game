"""Regression cases from live logs and failure injection; not native-engine proof."""
import unittest

from test_mod import runtime


class RuntimeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime(True)
        self.lua.execute("Fake.tick(2); assert(TWD_FP.camera_ready)")

    def test_visibility_cleanup_fault_does_not_block_camera_head_and_cursor_restore(self):
        self.lua.execute('''
          FP_Visibility.restore=function() error("visibility cleanup fault") end
          TWD_FP.toggle()
          assert(not TWD_FP.state.enabled and not TWD_FP.camera_ready and not Fake.confined)
          assert(VectorDistance(Fake.scene.camera.pos,Vector(5,4,6))<0.001)
          assert(Fake.scene.camera.mProps["Field of View"]==55)
          assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"])
        ''')

    def test_bottom_scene_without_extension_matches_scene_resource(self):
        self.lua.execute('''
          Fake.scene.name="adv_savannahstreets.scene"
          SceneGetBottomScene=function() return "adv_savannahstreets" end
          Fake.tick(3)
          assert(TWD_FP.camera_ready, "extensionless bottom scene lost the avatar")
          assert(Fake.confined)
        ''')

    def test_scene_resource_path_case_and_extension_are_canonical(self):
        self.lua.execute(r'''
          Fake.scene.name="Scenes/ADV_SavannahStreets.scene"
          SceneGetBottomScene=function() return "scenes\\adv_savannahstreets" end
          Fake.tick(3)
          assert(TWD_FP.camera_ready, "scene path casing/extension lost the avatar")
        ''')

    def test_new_dialogue_choice_is_not_swallowed_before_next_frame(self):
        self.lua.execute('''
          Fake.press(71)
          assert(TWD_FP.state.context=="explore" and TWD_FP.state.drawn)
          mode_DialogChoice.active=true
          mode_Reticle:OnMouseDown({})
          mode_Reticle:OnChoice({})
          assert(Fake.nativeClicks==1, "first dialogue click was swallowed")
          assert(Fake.nativeChoices==1, "first dialogue choice was swallowed")
        ''')

    def test_navigation_deactivation_releases_native_input_before_next_frame(self):
        self.lua.execute('''
          Fake.press(71)
          Fake.navigate=false
          Navigate_OnMouseL({})
          assert(Fake.nativeClicks==1, "stale explore context swallowed scripted input")
        ''')

    def test_pause_reticle_update_uses_live_mode_before_next_frame(self):
        self.lua.execute('''
          Fake.press(71)
          mode_Main.active=false
          Fake.reticleOriginal=false
          ReticleController_Update()
          assert(Fake.reticleOriginal, "stale explore context suppressed native pause input")
        ''')

    def test_flash_cleanup_failure_does_not_prevent_gun_cleanup(self):
        self.lua.execute('''
          Fake.press(71)
          local gun=Fake.agents.twd_fp_weapon
          local flash=Fake.agents.twd_fp_flash
          assert(gun.valid and flash.valid)
          local destroy=AgentDestroy
          local failed=false
          AgentDestroy=function(a)
            if a==flash and not failed then failed=true; error("transient flash teardown") end
            return destroy(a)
          end
          TWD_FP.toggle()
          assert(not gun.valid, "failed flash teardown prevented independent gun cleanup")
          Fake.tick(120)
          assert(not flash.valid, "failed flash teardown lost ownership instead of retrying")
        ''')

    def test_persistent_old_flash_failure_restores_active_adapter_before_waiting(self):
        self.lua.execute('''
          Fake.press(71); local flash=Fake.agents.twd_fp_flash
          local destroy=AgentDestroy
          AgentDestroy=function(a) if a==flash then error("persistent old flash") end; return destroy(a) end
          Fake.press(50); Fake.tick(400)
          assert(TWD_FP.recovery.status=="blocked" and not TWD_FP.camera_ready)
          assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"])
          assert(Fake.scene.camera.mProps["Field of View"]==55)
          assert(VectorDistance(Fake.scene.camera.pos,Vector(5,4,6))<0.001)
          assert(flash.hidden and Fake.agents.twd_fp_weapon.hidden)
        ''')

    def test_camera_restore_failure_is_retried_while_mod_disabled(self):
        self.lua.execute('''
          local camera=Fake.scene.camera
          local set=AgentSetWorldPos
          local failed=false
          AgentSetWorldPos=function(a,p)
            if a==camera and not failed then failed=true; error("transient camera restore") end
            return set(a,p)
          end
          TWD_FP.toggle()
          Fake.tick(120)
          assert(not TWD_FP.state.enabled)
          assert(VectorDistance(camera.pos,Vector(5,4,6))<0.001,
            "failed camera restore was abandoned")
          assert(camera.mProps["Field of View"]==55)
          assert(not Fake.confined)
        ''')

    def test_failed_head_restore_retains_property_ownership_for_retry(self):
        self.lua.execute('''
          local remove=PropertyRemove
          local failed=false
          PropertyRemove=function(props,key)
            if props==Fake.player.runtime and not failed then
              failed=true; error("transient head property restoration")
            end
            return remove(props,key)
          end
          TWD_FP.toggle()
          Fake.tick(120)
          assert(not TWD_FP.state.enabled)
          assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"],
            "failed head restore discarded restoration records")
          assert(rawget(Fake.player.runtime,"Mesh sk54_lee_head - Visible")==nil)
        ''')

    def test_parent_translation_is_not_mistaken_for_authored_camera_cut(self):
        self.lua.execute('''
          TWD_FP.toggle()
          local parent=Fake.new_agent("moving_camera_rig",{},Vector(10,0,0))
          local camera=Fake.new_agent("rig_camera",{["Field of View"]=50},Vector(5,4,6))
          camera.parent=parent
          Fake.scene.camera=camera
          -- Model the native distinction that the deliberately small fixture
          -- otherwise omits: world setters invert the parent's translation.
          AgentGetPos=function(a) return Vector(a.pos) end
          AgentGetRot=function(a) return Vector(a.rot) end
          AgentSetWorldPos=function(a,p)
            local base=a.parent and AgentGetWorldPos(a.parent) or Vector()
            a.pos=Vector(p.x-base.x,p.y-base.y,p.z-base.z)
          end
          AgentSetWorldRot=function(a,r)
            local base=a.parent and AgentGetWorldRot(a.parent) or Vector()
            a.rot=Vector(r.x-base.x,r.y-base.y,r.z-base.z)
          end
          TWD_FP.toggle(); Fake.tick(2)
          parent.pos.x=13
          Fake.tick(2)
          TWD_FP.toggle()
          assert(VectorDistance(AgentGetWorldPos(camera),Vector(18,4,6))<0.001,
            "moving parent contaminated the saved authored camera transform")
        ''')

    def test_ui_scene_open_does_not_reattach_closing_game_scene(self):
        self.lua.execute('''
          Callback_OnGameSceneClose:Run("next_game_script.lua")
          Callback_SceneOpenFinished:Run({name="ui_loading_overlay.scene"})
          Fake.tick(3)
          assert(not TWD_FP.camera_ready,
            "unrelated UI scene-open callback reattached the closing game avatar")
          assert(not Fake.confined)
        ''')


if __name__ == "__main__":
    unittest.main(verbosity=2)
