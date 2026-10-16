from pathlib import Path
import unittest
from lupa import lua51

ROOT=Path(__file__).resolve().parents[1]


def runtime(adapter=False):
    lua=lua51.LuaRuntime(unpack_returned_tuples=True)
    if adapter:
        lua.execute((ROOT/"tests/fake_engine.lua").read_text())
        def require(name):
            if name=="fp_generated.lua":
                lua.execute('FP_Generated={}'); return
            lua.execute((ROOT/"src"/name).read_text())
        lua.globals().require=require
        lua.execute((ROOT/"src/fp_main.lua").read_text())
    else:
        lua.execute((ROOT/"src/fp_config.lua").read_text())
        lua.execute((ROOT/"src/fp_core.lua").read_text())
        lua.execute('s=FP_Core.new(FP_Config); s.drawn=true; FP_Core.set_context(s,"explore"); s.trigger=false')
    return lua


class CoreTests(unittest.TestCase):
    def setUp(self): self.lua=runtime()
    def test_semiautomatic_hold_only_fires_once(self):
        self.lua.execute('for i=1,300 do FP_Core.update(s,1/60,{fire=true,weapon_ready=true},FP_Config) end; assert(s.shots==1 and s.magazines[1]==14)')
    def test_cooldown_blocks_fast_reclick(self):
        self.lua.execute('FP_Core.update(s,0,{fire=true,weapon_ready=true},FP_Config); FP_Core.update(s,0.01,{},FP_Config); FP_Core.update(s,0.01,{fire=true,weapon_ready=true},FP_Config); assert(s.shots==1)')
    def test_reload_conserves_finite_ammunition(self):
        self.lua.execute('FP_Config.infinite_reserve=false; s.magazines[1]=12; s.reserves[1]=2; assert(FP_Core.reload(s,FP_Config)); for i=1,120 do FP_Core.update(s,1/60,{},FP_Config) end; assert(s.magazines[1]==14 and s.reserves[1]==0)')
    def test_no_shot_during_reload(self):
        self.lua.execute('s.magazines[1]=3; FP_Core.reload(s,FP_Config); FP_Core.update(s,0.1,{fire=true,weapon_ready=true},FP_Config); assert(s.shots==0 and s.magazines[1]==3)')
    def test_switch_cancels_reload_without_refill(self):
        self.lua.execute('s.magazines[1]=2; FP_Core.reload(s,FP_Config); FP_Core.select(s,2,FP_Config); for i=1,300 do FP_Core.update(s,1/60,{},FP_Config) end; assert(s.magazines[1]==2 and s.magazines[2]==2 and s.reload_left==0)')
    def test_held_choice_click_cannot_fire_after_dialogue(self):
        self.lua.execute('FP_Core.set_context(s,"dialogue"); FP_Core.update(s,0.1,{fire=true,weapon_ready=true},FP_Config); FP_Core.set_context(s,"explore"); FP_Core.update(s,0.1,{fire=true,weapon_ready=true},FP_Config); assert(s.shots==0)')
    def test_all_script_modes_block_free_fire(self):
        self.lua.execute('for _,mode in ipairs({"dialogue","cinematic","scripted","combat","paused","inactive"}) do FP_Core.set_context(s,mode); s.trigger=false; FP_Core.update(s,0.1,{fire=true,weapon_ready=true},FP_Config); end; assert(s.shots==0)')
    def test_cursor_and_missing_model_block_fire(self):
        self.lua.execute('FP_Core.update(s,0.1,{fire=true,weapon_ready=false},FP_Config); s.trigger=false; FP_Core.update(s,0.1,{fire=true,weapon_ready=true,cursor=true},FP_Config); assert(s.shots==0)')
    def test_mouse_is_not_scaled_by_framerate(self):
        self.lua.execute('t=FP_Core.new(FP_Config); FP_Core.set_context(t,"explore"); FP_Core.update(s,1/30,{look=true,dx=0.05,dy=0.02},FP_Config); FP_Core.update(t,1/144,{look=true,dx=0.05,dy=0.02},FP_Config); assert(s.yaw==t.yaw and s.pitch==t.pitch)')
    def test_pitch_clamp_and_yaw_wrap(self):
        self.lua.execute('FP_Core.update(s,0.1,{look=true,dx=999,dy=999},FP_Config); assert(s.pitch==80 and s.yaw>=-180 and s.yaw<180)')
    def test_pause_freezes_reload_and_recoil(self):
        self.lua.execute('s.context="paused"; s.reload_left=1; s.recoil=2; FP_Core.update(s,0.1,{},FP_Config); assert(s.reload_left==1 and s.recoil==2)')
    def test_health_never_negative(self):
        self.lua.execute('assert(FP_Core.health_after(100,1000,false)==0); assert(FP_Core.health_after(100,20,true)==40)')
    def test_pause_resume_preserves_reload(self):
        self.lua.execute('s.reload_left=1; FP_Core.set_context(s,"paused"); assert(s.reload_left==1); FP_Core.set_context(s,"explore"); assert(s.reload_left==1 and s.trigger)')
    def test_alt_does_not_zoom_while_using_native_cursor(self):
        self.lua.execute('FP_Core.update(s,0.1,{aim=true,cursor=true},FP_Config); assert(s.aim==0)')
    def test_recoil_is_deferred_until_after_hit_query(self):
        self.lua.execute('local e=FP_Core.update(s,0,{fire=true,weapon_ready=true},FP_Config); assert(e.fired and e.recoil>0 and s.recoil==0)')


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.lua=runtime(True)
        self.lua.execute(r'Fake.tick(2); assert(TWD_FP.state.enabled, table.concat(Fake.logs,"\n"))')
    def test_head_only_and_camera_at_player(self):
        self.lua.execute('assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"]==false); assert(Fake.player.mProps["Mesh sk54_lee_armL - Visible"]==true); assert(Fake.scene.camera.pos.y>1.6 and Fake.scene.camera.pos.y<1.8)')
    def test_toggle_restores_original_camera_and_inherited_visibility(self):
        self.lua.execute('TWD_FP.toggle(); assert(Fake.scene.camera.pos.x==5 and Fake.scene.camera.pos.y==4 and Fake.scene.camera.pos.z==6); assert(Fake.scene.camera.mProps["Field of View"]==55); assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"]==true); assert(rawget(Fake.player.runtime,"Mesh sk54_lee_head - Visible")==nil); assert(not Fake.confined)')
    def test_original_local_false_visibility_preserved(self):
        self.lua.execute('TWD_FP.toggle(); Fake.player.runtime["Mesh sk54_lee_head - Visible"]=false; TWD_FP.toggle(); Fake.tick(); TWD_FP.toggle(); assert(rawget(Fake.player.runtime,"Mesh sk54_lee_head - Visible")==false)')
    def test_dialogue_keeps_first_person_and_releases_cursor(self):
        self.lua.execute('mode_DialogChoice.active=true; Fake.tick(); assert(TWD_FP.state.context=="dialogue" and not Fake.confined); assert(Fake.scene.camera.pos.y>1.6); mode_Reticle:OnMouseDown({}); assert(Fake.nativeClicks==1)')
    def test_scripted_shooting_uses_original_events(self):
        self.lua.execute('Fake.press(71); mode_shotgun.active=true; Fake.tick(); mode_Reticle:OnMouseDown({}); assert(Fake.nativeClicks==1 and TWD_FP.state.context=="combat"); assert(Fake.agents.twd_fp_weapon.hidden)')
    def test_drawn_weapon_consumes_exploration_clicks(self):
        self.lua.execute('Fake.press(71); mode_Reticle:OnMouseDown({}); Navigate_OnMouseL({}); assert(Fake.nativeClicks==0); Fake.press(1); assert(TWD_FP.state.shots==1)')
    def test_alt_restores_native_click(self):
        self.lua.execute('Fake.press(71); Fake.keys[18]=true; Fake.tick(); mode_Reticle:OnMouseDown({}); assert(Fake.nativeClicks==1 and not Fake.confined)')
    def test_scene_close_cleans_agents_and_new_scene_recovers(self):
        self.lua.execute('Fake.press(71); Callback_OnGameSceneClose:Run(); assert(not Fake.agents.twd_fp_eye.valid and not Fake.agents.twd_fp_weapon.valid); assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"]); Callback_SceneOpenFinished:Run(); Fake.tick(); assert(Fake.agents.twd_fp_eye.valid and TWD_FP.state.enabled)')
    def test_wall_intercepts_shot_without_damaging_walker(self):
        self.lua.execute('Fake.hit=Fake.new_agent("wall",{},Vector(1,1,5)); Fake.press(71); Fake.press(1); assert(TWD_FP.state.shots==1 and not Fake.hit.hidden and Fake.hit.selectable)')
    def test_walker_damage_and_original_visibility_survive_fire(self):
        self.lua.execute('Fake.hit=Fake.new_agent("zombie_test",{},Vector(1,0,6)); Fake.hit.hasHead=true; Fake.press(71); for i=1,3 do Fake.tick(20); Fake.press(1) end; assert(TWD_FP.state.shots==3 and not Fake.hit.selectable and not Fake.player.hidden)')
    def test_native_failure_backs_off_and_releases_mouse(self):
        self.lua.execute('AgentGetWorldPos=function() error("test native failure") end; Fake.tick(); assert(TWD_FP.recovery.status=="waiting" and not Fake.confined); assert(Fake.originalUpdates==3)')
    def test_duplicate_bootstrap_does_not_double_hook(self):
        self.lua.execute((ROOT/"src/fp_main.lua").read_text())
        self.lua.execute('Fake.tick(); assert(Fake.originalUpdates==3)')
    def test_direct_head_query_ignores_stale_proxy_position(self):
        self.lua.execute('Fake.agents.twd_fp_eye.pos=Vector(100,100,100); Fake.tick(); assert(Fake.scene.camera.pos.y<2 and TWD_FP.state.enabled)')
    def test_old_scene_avatar_is_not_followed(self):
        self.lua.execute('Fake.player.scene={name="old_scene"}; Fake.tick(); assert(not Fake.agents.twd_fp_eye.valid and not Fake.confined)')
    def test_native_scene_name_matches_player_scene_object(self):
        self.lua.execute('SceneGetBottomScene=function() return "test_scene" end; Fake.tick(); assert(Fake.agents.twd_fp_eye.valid and TWD_FP.state.enabled and Fake.scene.camera.pos.y>1.6)')
    def test_camera_change_stays_at_head_and_restores_previous(self):
        self.lua.execute('local old=Fake.scene.camera; Fake.scene.camera=Fake.new_agent("newcam",{["Field of View"]=60},Vector(9,9,9)); Fake.tick(); assert(old.pos.x==5 and old.pos.y==4); assert(Fake.scene.camera.pos.y<2 and TWD_FP.state.enabled)')
    def test_animated_visibility_cannot_restore_head_inside_camera(self):
        self.lua.execute('Fake.player.runtime["Mesh sk54_lee_head - Visible"]=true; Fake.tick(); assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"]==false)')
    def test_peek_tracks_authored_camera_movement_with_stationary_player(self):
        self.lua.execute('mode_peek.active=true; Fake.tick(); local y=Fake.scene.camera.pos.y; Fake.scene.camera.pos.y=5; Fake.tick(); assert(TWD_FP.state.context=="peek" and Fake.scene.camera.pos.y>y+0.5); mode_peek:OnDirection({code=87,type=0}); assert(Fake.peekEvent.code==87)')
    def test_native_movement_axes_follow_first_person_camera(self):
        self.lua.execute('assert(Fake.scene.camera.mProps["NavCam - Direct Control Axis Agent"]==""); assert(Fake.scene.camera.mProps["NavCam - Direct Control Axis Update"]==true); TWD_FP.toggle(); assert(rawget(Fake.scene.camera.runtime,"NavCam - Direct Control Axis Agent")==nil)')
    def test_weapon_switch_uses_new_agent_name_before_deferred_destroy(self):
        self.lua.execute('Fake.press(71); local old=Fake.agents.twd_fp_weapon.name; Fake.press(50); assert(Fake.agents.twd_fp_weapon.name~=old)')
    def station(self):
        self.lua.execute('''
          Fake.station=Fake.new_agent("Station01",{["Field of View"]=43},Vector(1.6965,3.5297,-12.0338),Vector(5,170,0))
          Fake.station.resource="cam_station.prop"; Fake.scene.camera=Fake.station
          Fake.player.pos=Vector(1.61,-0.09,19.89); Fake.tick(2)
        ''')
    def test_motel_station_uses_authored_projection_not_distant_head(self):
        self.station()
        self.lua.execute('''
          assert(TWD_FP.state.context=="station")
          assert(VectorDistance(Fake.station.pos,Vector(1.6965,3.5297,-12.0338))<0.0001)
          assert(Fake.station.mProps["Field of View"]==43 and not Fake.confined)
          assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"])
          Navigate_OnMouseL(); mode_Reticle:OnChoice({})
          assert(Fake.nativeClicks==1 and Fake.nativeChoices==1)
        ''')
    def test_station_look_returns_exactly_to_authored_interaction_view(self):
        self.station()
        self.lua.execute('''
          Fake.keys[2]=true; Fake.tick(); Fake.cursor.x=0.6; Fake.tick()
          assert(Fake.confined and Fake.station.rot.y~=170)
          Fake.keys[2]=false; Fake.tick()
          assert(not Fake.confined and Fake.station.rot.y==170 and Fake.station.rot.x==5)
        ''')
    def test_station_parent_is_detected_without_names(self):
        self.station()
        self.lua.execute('''
          local child=Fake.new_agent("anonymous_child",{},Vector(),Vector())
          child.parent=Fake.station; Fake.scene.camera=child; Fake.tick()
          assert(TWD_FP.state.context=="station")
        ''')
    def test_station_state_does_not_override_unrelated_cutscene_camera(self):
        self.station()
        self.lua.execute('''
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.scene.camera=Fake.new_agent("cut",{},Vector(9,9,9)); Fake.tick()
          assert(TWD_FP.state.context=="cinematic" and Fake.confined)
          assert(Fake.scene.camera.pos.z>19)
        ''')
    def test_station_movement_tracks_authored_changes_without_moving_avatar(self):
        self.station()
        self.lua.execute('''
          Fake.station.pos=Vector(1.4253,3.5764,-11.1003); Fake.tick()
          assert(VectorDistance(Fake.station.pos,Vector(1.4253,3.5764,-11.1003))<0.0001)
          assert(Fake.player.pos.z==19.89)
        ''')
    def test_cutscene_mouse_survives_native_reticle_recentering(self):
        self.lua.execute('''
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.updateReticle=true; Fake.tick(); Fake.cursor.x=0.6; Fake.tick()
          assert(TWD_FP.state.context=="cinematic" and TWD_FP.state.yaw < -10)
          assert(Fake.reticleOriginal and Fake.confined)
        ''')
    def test_cutscene_choice_releases_cursor_and_keeps_native_clicks(self):
        self.lua.execute('''
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true; Fake.tick()
          mode_DialogChoice.active=true; Fake.tick(); mode_Reticle:OnMouseDown({})
          assert(not Fake.confined and Fake.nativeClicks==1)
        ''')
    def test_authored_look_target_controls_focus_direction(self):
        self.lua.execute('''
          Fake.new_agent("focus_object",{},Vector(5,1.65,2))
          Fake.player.base["Look At - Agent"]="focus_object"
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true; Fake.tick()
          assert(math.abs(Fake.scene.camera.rot.y-90)<0.01)
          local camera=Fake.scene.camera
          local target=AgentGetWorldPos(AgentFind("focus_object"))
          local origin,forward=AgentGetWorldPos(camera),AgentGetForwardVec(camera)
          local distance=VectorDistance(origin,target)
          assert(VectorDistance(VectorAdd(origin,VectorScale(forward,distance)),target)<0.001)
        ''')
    def test_focus_assist_respects_mouse_then_recenters(self):
        self.lua.execute('''
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true; Fake.tick()
          Fake.cursor.x=0.7; Fake.tick(); local yaw=TWD_FP.state.yaw
          Fake.tick(60); assert(math.abs(TWD_FP.state.yaw-yaw)<0.001)
          Fake.keys[9]=true; Fake.tick(20); assert(math.abs(TWD_FP.state.yaw)<1)
          Fake.keys[9]=false; Fake.cursor.x=0.7; Fake.tick(); Fake.tick(360)
          assert(math.abs(TWD_FP.state.yaw)<0.2)
        ''')
    def test_transient_fault_rebuilds_without_refilling_ammo(self):
        self.lua.execute('''
          Fake.press(71); Fake.press(1); local ammo=TWD_FP.state.magazines[1]
          local original=AgentGetWorldPos; local failed=false
          AgentGetWorldPos=function(...) if not failed then failed=true; error("transient") end; return original(...) end
          Fake.tick(); assert(TWD_FP.recovery.status=="waiting" and not Fake.confined)
          Fake.tick(30); assert(TWD_FP.recovery.status=="active")
          assert(TWD_FP.camera_ready and TWD_FP.state.magazines[1]==ammo)
        ''')
    def test_repeated_faults_stop_retrying_until_manual_recovery(self):
        self.lua.execute('''
          local original=AgentGetWorldPos
          AgentGetWorldPos=function() error("persistent") end
          Fake.tick(400); assert(TWD_FP.recovery.status=="blocked" and not Fake.confined)
          local errors=FP_Log.errors; Fake.tick(400); assert(FP_Log.errors==errors)
          AgentGetWorldPos=original; Fake.press(119)
          assert(TWD_FP.recovery.status=="active" and TWD_FP.camera_ready)
        ''')
    def test_manual_disable_is_not_undone_by_watchdog(self):
        self.lua.execute('TWD_FP.toggle(); Fake.tick(600); assert(not TWD_FP.state.enabled and not Fake.confined); Fake.press(119); assert(not TWD_FP.state.enabled)')
    def test_missing_camera_releases_input_until_camera_returns(self):
        self.lua.execute('''
          local cam=Fake.scene.camera; Fake.scene.camera=nil; Fake.tick()
          assert(not Fake.confined and not TWD_FP.camera_ready)
          Fake.scene.camera=cam; Fake.tick(); assert(TWD_FP.camera_ready and Fake.confined)
        ''')
    def test_missed_scene_open_recovers_only_after_new_avatar(self):
        self.lua.execute('''
          Callback_OnGameSceneClose:Run(); Fake.tick(200)
          assert(not TWD_FP.camera_ready)
          local old=Fake.player; Fake.player=Fake.new_agent("Lee",old.base,Vector(4,0,4))
          Fake.player.hasHead=true; Fake.tick(2)
          assert(TWD_FP.camera_ready and Fake.scene.camera.pos.x>3.9)
        ''')
    def test_weapon_failure_does_not_disable_camera_and_can_retry(self):
        self.lua.execute('''
          local original=AgentCreate; local failed=false
          AgentCreate=function(name,...) if string.find(name,"twd_fp_weapon") and not failed then failed=true; error("weapon fault") end; return original(name,...) end
          Fake.press(71); assert(TWD_FP.camera_ready and TWD_FP.recovery.status=="active")
          Fake.tick(30); assert(Fake.agents.twd_fp_weapon.valid)
        ''')
    def test_nonfinite_camera_fault_restores_native_input(self):
        self.lua.execute('Fake.scene.camera.pos.x=0/0; Fake.tick(); assert(TWD_FP.recovery.status=="waiting" and not Fake.confined)')
    def test_fov_animation_is_preserved_when_returning_to_authored_view(self):
        self.lua.execute('''
          Fake.scene.camera.runtime["Field of View"]=37; Fake.tick()
          Fake.keys[18]=true; Fake.tick(); assert(Fake.scene.camera.mProps["Field of View"]==37)
          Fake.keys[18]=false; Fake.tick(); assert(Fake.scene.camera.mProps["Field of View"]==FP_Config.fov)
          TWD_FP.toggle(); assert(Fake.scene.camera.mProps["Field of View"]==37)
        ''')
    def test_focus_failure_falls_back_without_disabling_camera(self):
        self.lua.execute('''
          SceneGetAgents=function() error("focus query fault") end
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.tick(800); assert(TWD_FP.recovery.status=="active" and TWD_FP.camera_ready)
          local errors=FP_Log.errors; Fake.tick(400); assert(FP_Log.errors==errors)
        ''')
    def test_head_visibility_survives_repeated_station_to_exploration_transitions(self):
        self.station()
        self.lua.execute('''
          local station=Fake.station
          for i=1,20 do
            Fake.scene.camera=Fake.agents.camera; Fake.tick()
            assert(not Fake.player.mProps["Mesh sk54_lee_head - Visible"])
            Fake.scene.camera=station; Fake.tick()
            assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"])
          end
          TWD_FP.toggle(); assert(Fake.player.mProps["Mesh sk54_lee_head - Visible"])
        ''')
    def test_station_and_peek_never_fire_exploration_weapon(self):
        self.lua.execute('Fake.press(71)')
        self.station()
        self.lua.execute('''
          Fake.press(1); assert(TWD_FP.state.shots==0 and Fake.agents.twd_fp_weapon.hidden)
          mode_peek.active=true; Fake.press(1); assert(TWD_FP.state.shots==0)
          Navigate_OnMouseL(); assert(Fake.nativeClicks==1)
        ''')


if __name__=="__main__": unittest.main(verbosity=2)
