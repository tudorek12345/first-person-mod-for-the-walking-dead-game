"""Camera comfort regressions through the real adapter and a minimal engine fixture."""
import unittest

from test_mod import runtime


class ViewComfortTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime(True)
        self.lua.execute('''
          Fake.headHeight=1.65
          local original=AgentGetWorldPos
          AgentGetWorldPos=function(agent,node)
            if agent==Fake.player and node=="head" then
              return VectorAdd(Fake.player.pos,Vector(0,Fake.headHeight,0))
            end
            return original(agent,node)
          end
        ''')

    def assert_eye_height(self, head_height, expected):
        self.lua.globals().Fake.headHeight = head_height
        self.lua.execute('Fake.tick(2)')
        self.assertAlmostEqual(self.lua.eval('Fake.scene.camera.pos.y'), expected, places=6)
        self.assertTrue(self.lua.eval('TWD_FP.camera_ready'))
        self.assertEqual(self.lua.eval('TWD_FP.camera_policy'), 'player_eye')

    def test_standing_camera_raises_head_to_comfortable_eye_height(self):
        self.assert_eye_height(1.65, 1.79)

    def test_crouched_pose_keeps_small_clearance(self):
        self.assert_eye_height(0.8, 0.835)

    def test_short_character_does_not_receive_adult_standing_lift(self):
        self.assert_eye_height(1.0, 1.035)

    def test_transition_pose_uses_smooth_intermediate_lift(self):
        self.assert_eye_height(1.475, 1.5625)

    def test_eye_lift_is_relative_to_actor_root_not_world_elevation(self):
        self.lua.execute('Fake.tick(2); Fake.player.pos.y=12; Fake.tick(90)')
        self.assertAlmostEqual(self.lua.eval('Fake.scene.camera.pos.y-Fake.player.pos.y'), 1.79, places=6)
        self.lua.execute('Fake.player.pos.y=-6; Fake.headHeight=0.8; Fake.tick(90)')
        self.assertAlmostEqual(self.lua.eval('Fake.scene.camera.pos.y-Fake.player.pos.y'), 0.835, places=6)

    def test_cutscene_focus_aims_from_adjusted_eye_position(self):
        self.lua.execute('''
          Fake.tick(2)
          Fake.new_agent("comfort_target",{},Vector(5,2.8,2))
          Fake.player.base["Look At - Agent"]="comfort_target"
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.tick(2)
        ''')
        self.assertEqual(self.lua.eval('TWD_FP.state.context'), 'cinematic')
        self.lua.execute('''
          local expectedPitch=-math.deg(math.atan((2.8-1.79)/4))
          assert(math.abs(Fake.scene.camera.rot.x-expectedPitch)<0.00001,
                 "Focus pitch did not use raised eye height")
          local camera=Fake.scene.camera
          local target=AgentGetWorldPos(AgentFind("comfort_target"))
          local pos=AgentGetWorldPos(camera)
          local forward=AgentGetForwardVec(camera)
          local length=VectorDistance(pos,target)
          local alignment=((target.x-pos.x)*forward.x+(target.y-pos.y)*forward.y+
                           (target.z-pos.z)*forward.z)/length
          assert(alignment>0.999999,"Focus target no longer lies on camera forward axis")
        ''')

    def test_aim_smoothly_reaches_65_and_returns_to_100(self):
        self.lua.execute('Fake.tick(2)')
        self.assertAlmostEqual(self.lua.eval('Fake.scene.camera.mProps["Field of View"]'), 100, places=6)
        self.lua.execute('Fake.press(71); Fake.keys[2]=true; Fake.tick()')
        transition = self.lua.eval('Fake.scene.camera.mProps["Field of View"]')
        self.assertGreater(transition, 65)
        self.assertLess(transition, 100)
        self.lua.execute('Fake.tick(60)')
        self.assertAlmostEqual(self.lua.eval('Fake.scene.camera.mProps["Field of View"]'), 65, places=4)
        self.lua.execute('Fake.keys[2]=false; Fake.tick()')
        transition = self.lua.eval('Fake.scene.camera.mProps["Field of View"]')
        self.assertGreater(transition, 65)
        self.assertLess(transition, 100)
        self.lua.execute('Fake.tick(60)')
        self.assertAlmostEqual(self.lua.eval('Fake.scene.camera.mProps["Field of View"]'), 100, places=4)

    def test_station_keeps_original_projection_despite_eye_and_fov_defaults(self):
        self.lua.execute('''
          Fake.tick(2)
          Fake.station=Fake.new_agent("Station01",{["Field of View"]=43},
            Vector(1.6965,3.5297,-12.0338),Vector(5,170,0))
          Fake.station.resource="cam_station.prop"; Fake.scene.camera=Fake.station
          Fake.player.pos=Vector(1.61,-0.09,19.89)
          for _,height in ipairs({1.65,0.8,1.3}) do
            Fake.headHeight=height; Fake.tick(2)
            assert(TWD_FP.state.context=="station" and TWD_FP.camera_policy=="authored")
            assert(VectorDistance(Fake.station.pos,Vector(1.6965,3.5297,-12.0338))<0.000001)
            assert(Fake.station.mProps["Field of View"]==43)
          end
        ''')
