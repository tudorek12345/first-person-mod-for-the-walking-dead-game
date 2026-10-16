-- Opt-in native API smoke tests, built only with --native-test enabled.
-- Uses disposable agents; never loads a save, advances a dialog, or saves.
local F,L=TWD_FP,FP_Log
ThreadStart(function()
  Sleep(3)
  if Main_GetAvatar() and AgentIsValid(Main_GetAvatar()) then
    L.write("info","native_test_skipped",{reason="Gameplay already active"})
    F.testing=nil
    return
  end
  local fixture
  local owned={}
  local savedDrawn,savedWeapon=F.state.drawn,F.state.weapon
  local passed,failed=0,0
  local function check(name,fn)
    local ok=L.try("native_test_error:"..name,fn)
    if ok then passed=passed+1 else failed=failed+1 end
    L.write(ok and "info" or "error","native_test_result",{test=name,passed=ok})
    return ok
  end
  local ok=L.try("native_test_setup_error",function()
    check("retail_error_trace",function()
      local good,detail=xpcall(function() assert(false,"fp-native-sentinel") end,L.traceback)
      assert(not good and string.find(detail,"fp-native-sentinel",1,true),"Error details lost")
    end)
    local testScene=SceneGetBottomScene()
    assert(testScene,"No scene ready for native fixtures")
    check("visibility_original_module_hook",function()
      assert(FP_Visibility.stats().hooks>=1,"Original camera visibility callback was not intercepted")
    end)
    check("visibility_scoped_ownership",function()
      local probe=AgentCreate("twd_fp_test_visibility","module_null.prop",Vector(),Vector(),testScene,false,false)
      owned[#owned+1]=probe
      FP_Visibility.update(true,testScene,nil)
      FP_Visibility.camera_call(function() AgentHide(probe,true) end)
      assert(not AgentIsHidden(probe),"Camera-only hide was not compensated")
      AgentHide(probe,true)
      FP_Visibility.restore()
      assert(AgentIsHidden(probe),"Story hide was incorrectly restored")
      FP_Visibility.camera_call(function() AgentHide(probe,true) end)
      FP_Visibility.update(true,testScene,nil)
      assert(not AgentIsHidden(probe),"Delayed camera hide compensation failed")
      FP_Visibility.restore()
      assert(AgentIsHidden(probe),"Authored visibility restoration failed")
      AgentDestroy(probe)
    end)
    check("focus_direction_convention",function()
      local probe=AgentCreate("twd_fp_test_direction","module_null.prop",Vector(0,0,0),Vector(23,47,0),testScene,true,false)
      owned[#owned+1]=probe
      local forward=AgentGetForwardVec(probe,true)
      local pitch,yaw=FP_View.direction(Vector(0,0,0),forward)
      L.write("info","native_direction_probe",{x=forward.x,y=forward.y,z=forward.z,pitch=pitch,yaw=yaw})
      AgentDestroy(probe)
      assert(math.abs(pitch-23)<0.05 and math.abs(yaw-47)<0.05,"Focus direction disagrees with engine rotation")
    end)
    check("moving_parent_camera_ownership",function()
      local parent=AgentCreate("twd_fp_test_rig","module_null.prop",Vector(10,0,0),Vector(),testScene,true,false)
      local child=AgentCreate("twd_fp_test_child","module_null.prop",Vector(),Vector(),testScene,true,false)
      owned[#owned+1]=child; owned[#owned+1]=parent
      AgentAttach(child,parent,false); AgentSetPos(child,Vector(5,4,6)); AgentSetRot(child,Vector())
      local saved=FP_Camera.snapshot(child)
      AgentSetWorldPos(child,Vector(1,1.7,2)); AgentSetWorldRot(child,Vector(5,20,0)); FP_Camera.applied(child,saved)
      AgentSetPos(parent,Vector(13,0,0)); AgentSetRot(parent,Vector(0,30,0))
      local expected=AgentLocalToWorld(parent,Vector(5,4,6))
      FP_Camera.observe(child,saved)
      assert(VectorDistance(saved.authorPos,expected)<0.001,"Parent movement contaminated authored view")
      FP_Camera.restore_position(child,saved); FP_Camera.restore_rotation(child,saved)
      assert(VectorDistance(AgentGetWorldPos(child),expected)<0.001,"Camera restoration missed moving rig")
      assert(VectorDistance(AgentGetRot(child),Vector())<0.01,"Local rotation restoration failed")
      AgentDestroy(child); AgentDestroy(parent)
    end)
    -- These synchronous checks destroy the fixture before yielding/rendering.
    fixture=AgentCreate("twd_fp_test_player","sk54_lee.prop",Vector(10,0,10),Vector(0,0,0),testScene,false,false)
    assert(fixture and AgentIsValid(fixture),"Lee prefab could not be created")
    check("animated_head_query",function()
      assert(AgentHasNode(fixture,"head"),"Missing head bone")
      local head=AgentGetWorldPos(fixture,"head")
      assert(head.x==head.x and head.y==head.y and head.z==head.z,"Invalid head coordinates")
    end)
    local originalCam=SceneGetCamera(testScene)
    local originalPos,originalRot=AgentGetWorldPos(originalCam),AgentGetWorldRot(originalCam)
    local originalForward,originalRight=AgentGetForwardVec(originalCam,true),AgentGetRightVec(originalCam,true)
    local originalFov=originalCam.mProps["Field of View"]
    if check("adapter_camera_and_head",function()
      F.testing.setup(fixture)
      assert(fixture.mProps["Mesh sk54_lee_head - Visible"]==false,"Head visibility override missing")
      assert(F.testing.update_camera("explore"),"No active scene camera")
      local _,cam=F.testing.get()
      local _,_,eye=F.testing.get(); owned[#owned+1]=eye
      local distance=VectorDistance(AgentGetWorldPos(cam),AgentGetWorldPos(fixture,"head"))
      assert(distance<0.5,"Camera missed head by "..tostring(distance))
      local head=AgentGetWorldPos(fixture,"head")
      local root=AgentGetWorldPos(fixture)
      local lift=FP_View.eye_lift(head.y-root.y,F.config)
      assert(math.abs(AgentGetWorldPos(cam).y-head.y-lift)<0.001,"Standing eye lift was not applied")
      assert(math.abs(cam.mProps["Field of View"]-F.config.fov)<0.01,"Wider FOV was not applied")
      L.write("info","native_view_comfort",{head_height=head.y-root.y,eye_lift=lift,
        eye_height=AgentGetWorldPos(cam).y-root.y,fov=cam.mProps["Field of View"]})
    end) then
      for i,weapon in ipairs(F.config.weapons) do
        check("weapon_"..weapon.id,function()
          F.state.weapon,F.state.drawn=i,true
          assert(F.testing.ensure_weapon(),"Weapon resource unavailable")
          assert(F.testing.update_weapon("explore"),"Weapon transform update failed")
          local _,_,_,gun=F.testing.get()
          assert(AgentIsValid(gun),"Invalid created gun")
          owned[#owned+1]=gun
          local matches=false
          for _,resource in ipairs(weapon.props) do
            if AgentIsParentProperty(gun,resource) then matches=true end
          end
          assert(matches,"Created weapon does not match requested prefab")
        end)
      end
      check("station_projection_restore",function()
        F.state.yaw,F.state.pitch=0,0
        assert(F.testing.update_camera("station"),"Station camera unavailable")
        assert(VectorDistance(AgentGetWorldPos(originalCam),originalPos)<0.001,"Station position changed")
        local actual=AgentGetWorldRot(originalCam)
        L.write("info","native_station_rotation",{before_x=originalRot.x,before_y=originalRot.y,before_z=originalRot.z,
          after_x=actual.x,after_y=actual.y,after_z=actual.z})
        assert(VectorDistance(AgentGetForwardVec(originalCam,true),originalForward)<0.001 and
          VectorDistance(AgentGetRightVec(originalCam,true),originalRight)<0.001,"Station orientation changed")
        assert(math.abs(originalCam.mProps["Field of View"]-originalFov)<0.01,"Station FOV changed")
        assert(fixture.mProps["Mesh sk54_lee_head - Visible"]~=false,"Authored view retained hidden head")
      end)
      check("cinematic_focus_adapter",function()
        local head=AgentGetWorldPos(fixture,"head")
        local target=AgentCreate("twd_fp_test_focus","module_null.prop",Vector(head.x+3,head.y,head.z),Vector(),testScene,false,false)
        owned[#owned+1]=target
        -- Do not set the actor's native look-at property: that starts engine
        -- tracking threads whose lifetime extends beyond this disposable test.
        F.testing.set_focus(target)
        assert(F.testing.update_camera("cinematic"),"Cinematic camera unavailable")
        assert(VectorDistance(AgentGetWorldPos(originalCam),AgentGetWorldPos(fixture,"head"))<0.5,"Cinematic position missed head")
        local forward=AgentGetForwardVec(originalCam,true)
        local expected=VectorNormalize(VectorSubtract(AgentGetWorldPos(target),AgentGetWorldPos(originalCam)))
        assert(VectorDistance(forward,expected)<0.001,"Focus missed authored target")
        local screen=CameraGetScreenPosFromWorldPos(originalCam,AgentGetWorldPos(target))
        L.write("info","native_focus_projection",{x=screen.x,y=screen.y,z=screen.z})
        assert(math.abs(screen.x-0.5)<0.05 and math.abs(screen.y-0.5)<0.05,"Focused target not near screen center")
        AgentDestroy(target)
      end)
    end
    check("adapter_cleanup",function()
      F.testing.cleanup()
      local p,c,e,g=F.testing.get()
      assert(not p and not c and not e and not g,"Adapter retained old agents")
    end)
  end)
  if not ok then failed=failed+1 end
  L.try("native_final_cleanup_error",F.testing.cleanup)
  for _,agent in ipairs(owned) do
    if AgentIsValid(agent) then L.try("native_owned_cleanup_error",AgentDestroy,agent) end
  end
  if fixture and AgentIsValid(fixture) then L.try("native_fixture_cleanup_error",AgentDestroy,fixture) end
  F.state.drawn,F.state.weapon=savedDrawn,savedWeapon
  -- AgentDestroy is deferred until the next engine update.
  Yield(); Yield()
  check("deferred_agent_destruction",function()
    for _,agent in ipairs(owned) do assert(not AgentIsValid(agent),"Owned agent survived destruction") end
    assert(not AgentExists("twd_fp_test_player"),"Fixture survived deferred destruction")
  end)
  F.testing=nil
  L.write(failed==0 and "info" or "error","native_tests_finished",{passed=passed,failed=failed})
end)
