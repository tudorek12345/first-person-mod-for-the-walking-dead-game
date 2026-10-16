"""Adapter regressions for animated eyes, native cuts and bounded fallback."""
import unittest

from test_mod import runtime


class CameraContinuityTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime(True)
        self.lua.execute('''
          Fake.headHeight=1.65
          local originalPosition=AgentGetWorldPos
          AgentGetWorldPos=function(agent,node)
            if agent==Fake.player and node=="head" then
              return VectorAdd(Fake.player.pos,Vector(0,Fake.headHeight,0))
            end
            return originalPosition(agent,node)
          end
          Fake.events={}
          local originalLog=FP_Log.write
          FP_Log.write=function(level,event,fields)
            local row={level=level,event=event}
            for key,value in pairs(fields or {}) do row[key]=value end
            Fake.events[#Fake.events+1]=row
            return originalLog(level,event,fields)
          end
          function Fake.hasMotion(kind)
            for _,row in ipairs(Fake.events) do
              if row.event=="camera_motion" and row.kind==kind then return true end
            end
            return false
          end
          Fake.tick(2)
        ''')

    def test_single_frame_native_camera_cut_preserves_user_look_and_heading(self):
        self.lua.execute('''
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.tick(2)
          TWD_FP.state.yaw=18; TWD_FP.state.pitch=-4
          Fake.tick()
          local before=AgentGetWorldRot(Fake.scene.camera)
          local originalCamera=Fake.scene.camera
          local cut=Fake.new_agent("native_one_frame_cut",{["Field of View"]=42},
            Vector(30,10,-25),Vector(-35,160,0))
          Fake.scene.camera=cut; Fake.tick()
          assert(math.abs(TWD_FP.state.yaw-18)<0.00001,"Cut reset manual yaw")
          assert(math.abs(TWD_FP.state.pitch+4)<0.00001,"Cut reset manual pitch")
          local cutRotation=AgentGetWorldRot(cut)
          assert(math.abs(FP_Core.wrap(cutRotation.y-before.y))<5,
                 "Single-frame native camera cut changed first-person yaw")
          assert(math.abs(cutRotation.x-before.x)<5,
                 "Single-frame native camera cut changed first-person pitch")
          Fake.scene.camera=originalCamera; Fake.tick()
          local restored=AgentGetWorldRot(originalCamera)
          assert(math.abs(FP_Core.wrap(restored.y-before.y))<5,
                 "Camera return retained the transient shot heading")
          assert(TWD_FP.camera_policy=="player_eye")
        ''')

    def test_head_height_changes_smooth_once_per_frame_and_converges(self):
        self.lua.execute('''
          local before=Fake.scene.camera.pos.y
          Fake.headHeight=1.55
          local target=1.55+FP_View.eye_lift(1.55,FP_Config)
          Fake.tick()
          local after=Fake.scene.camera.pos.y
          assert(after<before and after>target,"Head-height change snapped or failed to move")
          local expected=before+(target-before)*(1-math.exp(-GetFrameTime()*FP_Config.motion_smoothing_rate))
          assert(math.abs(after-expected)<0.000001,"Filter advanced more than once in the frame")
          assert(math.abs(after-target)<=FP_Config.motion_max_lag+0.000001)
          Fake.tick(90)
          assert(math.abs(Fake.scene.camera.pos.y-target)<0.00001,"Camera never settled to eye height")
        ''')

    def test_transient_player_root_jump_is_held_then_rejected(self):
        self.lua.execute('''
          local previous=AgentGetWorldPos(Fake.scene.camera)
          local root=Vector(Fake.player.pos)
          Fake.player.pos.x=root.x+16; Fake.tick()
          assert(TWD_FP.motion_state=="holding","One-frame jump was not held")
          assert(VectorDistance(Fake.scene.camera.pos,previous)<0.000001,
                 "One-frame skeleton/root glitch moved the camera")
          Fake.player.pos=Vector(root); Fake.tick()
          assert(TWD_FP.motion_state=="tracking")
          assert(TWD_FP.camera_policy=="player_eye")
          assert(VectorDistance(Fake.scene.camera.pos,previous)<0.000001)
          assert(Fake.hasMotion("jump_held") and Fake.hasMotion("jump_rejected"))
        ''')

    def test_persistent_root_jump_stays_in_first_person_without_authored_excursion(self):
        self.lua.execute('''
          local oldX=Fake.scene.camera.pos.x
          Fake.player.pos.x=Fake.player.pos.x+16
          local newX=oldX+16
          local held,settled=false,false
          for i=1,40 do
            Fake.tick()
            held=held or TWD_FP.motion_state=="holding"
            settled=settled or TWD_FP.motion_state=="tracking"
            assert(TWD_FP.camera_policy=="player_eye","Actor relocation entered authored fallback")
            local x=Fake.scene.camera.pos.x
            assert(math.abs(x-oldX)<0.000001 or math.abs(x-newX)<0.000001,
                   "Actor relocation visited a third camera position")
            assert(Fake.scene.camera.mProps["Field of View"]==100,"Actor relocation restored authored FOV")
            assert(not Fake.player.mProps["Mesh sk54_lee_head - Visible"],
                   "Actor relocation restored third-person head visibility")
          end
          assert(held and settled,"Actor relocation did not hold then settle")
          assert(Fake.hasMotion("jump_settled"))
          assert(math.abs(Fake.scene.camera.pos.x-Fake.player.pos.x)<0.001)
          assert(math.abs(Fake.scene.camera.pos.y-Fake.player.pos.y-1.79)<0.001)
          assert(TWD_FP.motion_state=="tracking")
          for _,row in ipairs(Fake.events) do
            assert(not (row.event=="camera_fallback" and row.reason=="actor_discontinuity"),
                   "Actor relocation logged an authored fallback")
          end
        ''')

    def test_station_displacement_is_exact_without_smoothing(self):
        self.lua.execute('''
          local station=Fake.new_agent("Station01",{["Field of View"]=43},
            Vector(1.6965,3.5297,-12.0338),Vector(5,170,0))
          station.resource="cam_station.prop"; Fake.station=station; Fake.scene.camera=station
          Fake.tick()
          assert(TWD_FP.camera_policy=="authored")
          assert(VectorDistance(station.pos,Vector(1.6965,3.5297,-12.0338))<0.000001)
          station.pos=Vector(-25,8,40); Fake.tick()
          assert(VectorDistance(station.pos,Vector(-25,8,40))<0.000001,
                 "Authored station movement was filtered")
          assert(station.mProps["Field of View"]==43)
        ''')

    def test_f6_cleanup_drops_old_filter_and_pending_jump(self):
        self.lua.execute('''
          Fake.player.pos.x=Fake.player.pos.x+16; Fake.tick()
          assert(TWD_FP.motion_state=="holding")
          Fake.press(FP_Config.toggle_key)
          assert(not TWD_FP.state.enabled)
          Fake.player.pos=Vector(50,0,3); Fake.headHeight=1.0
          Fake.press(FP_Config.toggle_key)
          assert(TWD_FP.state.enabled and TWD_FP.camera_ready)
          assert(TWD_FP.camera_policy=="player_eye")
          assert(math.abs(Fake.scene.camera.pos.x-50)<0.000001)
          assert(math.abs(Fake.scene.camera.pos.y-1.035)<0.000001,
                 "Reattachment retained the previous avatar eye filter")
        ''')

    def test_free_weapon_cannot_fire_during_invalid_head_fallback(self):
        self.lua.execute('''
          Fake.press(FP_Config.draw_key)
          Fake.headHeight=50; Fake.tick(2)
          assert(TWD_FP.camera_policy=="authored_fallback")
          local shots=TWD_FP.state.shots
          Fake.keys[1]=true; Fake.tick(3)
          assert(TWD_FP.state.shots==shots,"Invalid-head fallback camera fired free weapon")
          Fake.keys[1]=false; Fake.tick()
        ''')

    def test_weapon_trigger_is_latched_while_discontinuity_is_unconfirmed(self):
        self.lua.execute('''
          Fake.press(FP_Config.draw_key)
          local root=Vector(Fake.player.pos)
          local shots=TWD_FP.state.shots
          Fake.player.pos.x=root.x+16; Fake.keys[1]=true; Fake.tick()
          assert(TWD_FP.motion_state=="holding")
          assert(TWD_FP.state.shots==shots,"Unconfirmed camera position fired a shot")
          Fake.player.pos=Vector(root); Fake.tick(3)
          assert(TWD_FP.motion_state=="tracking")
          assert(TWD_FP.state.shots==shots,"Held trigger fired unexpectedly after recovery")
          Fake.keys[1]=false; Fake.tick()
        ''')

    def test_actor_relocation_preserves_yaw_pitch_and_100_fov_without_excursion(self):
        self.lua.execute('''
          TWD_FP.state.yaw=80; TWD_FP.state.pitch=7; Fake.tick()
          local oldX=Fake.scene.camera.pos.x
          Fake.player.pos.x=Fake.player.pos.x+16
          for i=1,40 do
            Fake.tick()
            assert(TWD_FP.camera_policy=="player_eye")
            assert(math.abs(Fake.scene.camera.rot.y-80)<0.000001,"Relocation changed view yaw")
            assert(math.abs(Fake.scene.camera.rot.x-7)<0.000001,"Relocation changed view pitch")
            assert(math.abs(TWD_FP.state.yaw-80)<0.000001,"Relocation discarded manual yaw")
            assert(math.abs(TWD_FP.state.pitch-7)<0.000001,"Relocation discarded manual pitch")
            assert(Fake.scene.camera.mProps["Field of View"]==100)
            local x=Fake.scene.camera.pos.x
            assert(math.abs(x-oldX)<0.000001 or math.abs(x-oldX-16)<0.000001,
                   "Relocation briefly visited authored camera position")
            assert(not Fake.player.mProps["Mesh sk54_lee_head - Visible"])
          end
        ''')

    def test_cinematic_far_camera_cut_at_confirmed_jump_preserves_eye_positions_and_user_offset(self):
        self.lua.execute('''
          FP_Config.head_forward=0
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.tick(2)
          TWD_FP.state.yaw=18; TWD_FP.state.pitch=-4; Fake.tick()
          local oldX=Fake.scene.camera.pos.x
          Fake.player.pos.x=Fake.player.pos.x+16
          local cut=Fake.new_agent("far_authored_cut",{["Field of View"]=42},
            Vector(-15,10,6),Vector(-35,160,0))
          local confirmFrame=math.ceil(FP_Config.motion_confirm_time/GetFrameTime())
          for i=1,40 do
            if i==confirmFrame then Fake.scene.camera=cut end
            Fake.tick()
            assert(TWD_FP.camera_policy=="player_eye","Cinematic relocation switched to authored view")
            local x=Fake.scene.camera.pos.x
            assert(math.abs(x-oldX)<0.000001 or math.abs(x-oldX-16)<0.000001,
                   "Cinematic relocation visited far authored camera position")
            assert(math.abs(TWD_FP.state.yaw-18)<0.000001,"Cinematic cut reset user yaw offset")
            assert(math.abs(TWD_FP.state.pitch+4)<0.000001,"Cinematic cut reset user pitch offset")
            assert(Fake.scene.camera.mProps["Field of View"]==100)
            assert(not Fake.player.mProps["Mesh sk54_lee_head - Visible"])
          end
          assert(Fake.hasMotion("jump_held") and Fake.hasMotion("jump_settled"))
          for _,row in ipairs(Fake.events) do
            assert(not (row.event=="camera_fallback" and row.reason=="actor_discontinuity"))
          end
        ''')

    def test_invalid_head_logs_onset_and_recovery_instead_of_every_frame(self):
        self.lua.execute('''
          local count=function(name)
            local total=0
            for _,row in ipairs(Fake.events) do if row.event==name then total=total+1 end end
            return total
          end
          Fake.headHeight=50; Fake.tick(30)
          assert(TWD_FP.camera_policy=="authored_fallback")
          assert(count("head_position_invalid")==1,"Invalid head flooded the log")
          assert(count("head_position_recovered")==0)
          Fake.headHeight=1.65; Fake.tick(30)
          assert(TWD_FP.camera_policy=="player_eye")
          assert(count("head_position_recovered")==1,"Recovery was missing or repeated")
          Fake.headHeight=50; Fake.tick(15)
          assert(count("head_position_invalid")==2,"A new failure episode was not logged")
        ''')

    def test_camera_only_hidden_avatar_keeps_eye_view_and_story_hide_restores_authored(self):
        self.lua.execute('''
          FP_Visibility.camera_call(function() AgentHide(Fake.player,true) end)
          assert(AgentIsHidden(Fake.player),"Fixture did not apply native camera hide")
          assert(FP_Visibility.camera_hidden(Fake.player))
          Fake.tick(3)
          assert(TWD_FP.camera_policy=="player_eye",
                 "Camera-only avatar visibility incorrectly disabled first person")
          assert(TWD_FP.state.context=="explore")
          assert(math.abs(Fake.scene.camera.pos.y-Fake.player.pos.y-1.79)<0.000001)
          AgentHide(Fake.player,true)
          assert(not FP_Visibility.camera_hidden(Fake.player),"Story hide retained camera ownership")
          Fake.tick()
          assert(TWD_FP.camera_policy=="authored","Story-hidden avatar did not restore authored shot")
          assert(VectorDistance(Fake.scene.camera.pos,Vector(5,4,6))<0.000001)
          assert(AgentIsHidden(Fake.player),"Adapter undid a story visibility change")
          AgentHide(Fake.player,false); Fake.tick()
          assert(TWD_FP.camera_policy=="player_eye")
        ''')


if __name__ == '__main__':
    unittest.main()
