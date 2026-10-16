"""Input/projection preservation across native authored gameplay modes."""
import unittest
from test_mod import runtime


class PolicyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime(True)
        self.lua.execute('Fake.tick(2)')

    def test_native_shotgun_keeps_absolute_cursor_and_projection(self):
        self.lua.execute('''
          mode_shotgun.active=true; Fake.cursor=Vector(.83,.27,0); Fake.tick(3)
          assert(TWD_FP.state.context=="combat" and not Fake.cursorHidden)
          assert(Fake.cursor.x==.83 and Fake.cursor.y==.27)
          assert(VectorDistance(Fake.scene.camera.pos,Vector(5,4,6))<.001)
          assert(Fake.scene.camera.mProps["Field of View"]==55)
          mode_Reticle:OnMouseDown({}); assert(Fake.nativeClicks==1)
        ''')

    def test_sniper_ignores_mod_right_mouse_look(self):
        self.lua.execute('''
          mode_sniper.active=true; Fake.keys[2]=true; Fake.cursor=Vector(.7,.3,0); Fake.tick()
          assert(Fake.cursor.x==.7 and Fake.cursor.y==.3)
          assert(TWD_FP.state.context=="combat" and TWD_FP.state.yaw==0)
        ''')

    def test_telescope_closeup_keeps_position_and_returns_to_exploration(self):
        self.lua.execute('''
          local cam=Fake.new_agent("cam_panningTelescope",{["Field of View"]=15},Vector(20,5,10),Vector(0,50,0))
          Game_EnterCloseUp("cam_panningTelescope"); Fake.tick()
          assert(TWD_FP.state.context=="closeup" and not Fake.cursorHidden)
          assert(cam.pos.x==20 and cam.mProps["Field of View"]==15)
          Fake.keys[2]=true; Fake.tick(); Fake.cursor.x=.6; Fake.tick()
          assert(cam.rot.y~=50 and cam.pos.x==20)
          Fake.keys[2]=false; Fake.tick(); assert(cam.rot.y==50)
          Game_ExitCloseUp("cam_panningTelescope"); Fake.tick()
          assert(TWD_FP.state.context=="explore")
        ''')

    def test_qte_map_overrides_cutscene_capture(self):
        self.lua.execute('''
          mode_Cutscene_Movement.active=true; mode_Cutscene_Interaction.active=true
          Fake.inputMaps={["struggle.imap"]=true}; Fake.keys[2]=true
          Fake.cursor=Vector(.8,.2,0); Fake.tick()
          assert(TWD_FP.state.context=="qte" and not Fake.cursorHidden)
          assert(Fake.cursor.x==.8 and Fake.cursor.y==.2)
        ''')

    def test_balance_and_spatial_choices_preserve_native_input(self):
        self.lua.execute('''
          Fake.press(71); mode_balance.active=true; Fake.tick()
          assert(TWD_FP.state.context=="qte" and Fake.agents.twd_fp_weapon.hidden)
          mode_balance.active=false; mode_choice.active=true
          mode_Reticle:OnChoice({}); assert(Fake.nativeChoices==1)
          Fake.tick(); assert(TWD_FP.state.context=="choice" and not Fake.cursorHidden)
        ''')

    def test_recap_transient_explore_flags_cannot_enable_free_guns(self):
        self.lua.execute('''
          Fake.scene.name="adv_previouslyOn104.scene"; Fake.tick(); Fake.press(71)
          assert(TWD_FP.state.context=="presentation" and not TWD_FP.state.drawn)
          assert(Fake.scene.camera.pos.x==5)
        ''')

    def test_hidden_avatar_uses_authored_view_without_mouse_capture(self):
        self.lua.execute('''
          Fake.player.hidden=true; Fake.tick()
          assert(TWD_FP.state.context=="scripted" and not Fake.cursorHidden)
          assert(Fake.scene.camera.pos.x==5)
        ''')

    def test_independently_destroyed_crosshair_rebuilds_both_ui_agents(self):
        self.lua.execute('''
          Fake.press(71); local old=Fake.agents.twd_fp_hud
          AgentDestroy(Fake.agents.twd_fp_crosshair); Fake.tick()
          assert(not old.valid and Fake.agents.twd_fp_crosshair.valid)
          assert(TWD_FP.camera_ready and FP_Log.errors==0)
        ''')

    def test_missing_weapon_does_not_consume_native_clicks_or_retry_forever(self):
        self.lua.execute('''
          Fake.missing={}
          for _,name in ipairs(FP_Config.weapons[1].props) do Fake.missing[name]=true end
          Fake.press(71); Navigate_OnMouseL(); assert(Fake.nativeClicks==1)
          Fake.tick(400); assert(not TWD_FP.state.drawn and TWD_FP.camera_ready)
          local errors=FP_Log.errors; Fake.tick(400); assert(FP_Log.errors==errors)
        ''')
