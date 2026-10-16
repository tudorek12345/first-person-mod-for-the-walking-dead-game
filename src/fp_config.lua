-- Rebuild after editing. All angles are in degrees.
FP_Config = {
  enabled=true, fov=100, aim_fov=65, near_clip=0.035, sensitivity=150,
  invert_y=false, pitch_limit=80, head_forward=0.065, head_up=0.14,
  -- Lift standing eyes; retain the small offset for low poses/short avatars.
  low_pose_head_up=0.035, low_pose_height=1.35, standing_head_height=1.60,
  motion_smoothing_rate=20, motion_max_lag=0.12, motion_root_jump=2.5,
  motion_head_jump=0.75, motion_confirm_time=0.08, motion_candidate_radius=0.5,
  focus_cut_delay=0.12, camera_visibility=true,
  fallback_eye_height=1.67, cinematic_roll=false, hide_head=true,
  free_weapons=true, infinite_reserve=true, damage_walkers=true,
  damage_story_characters=false, show_hud=true,
  toggle_key=117, draw_key=71, reload_key=82, use_key=70, cursor_key=18,
  recover_key=119, focus_key=9, cutscene_free_look=true,
  focus_assist=true, focus_delay=2.5, focus_speed=1.6,
  log_path="twd_firstperson.log",
  -- Some retail prefabs omit default mesh-visibility keys from enumeration.
  -- These names are verified against this installation's mesh resources.
  head_meshes={
    ["sk54_lee.prop"]={"sk54_lee_head"},
    ["sk54_leejacket.prop"]={"sk54_leejacket_head"},
    ["sk54_lee103.prop"]={"sk54_lee103_head"},
    ["sk54_lee104.prop"]={"sk54_lee104_head"},
    ["sk54_lee105.prop"]={"sk54_lee105_head"}
  },
  weapons={
    {id="pistol",label="Pistol",capacity=15,reserve=90,cooldown=0.23,
     reload=1.6,damage=34,recoil=1.4,range=70,pellets=1,
     props={"obj_gunglock.prop","obj_gunglock104.prop","obj_gunpistol.prop"},
     sound="wpn_handgun.wav",flash="fx_muzzleflashpistol.prop",
     offset={x=0.16,y=-0.19,z=0.38},aim_offset={x=0,y=-0.115,z=0.4},
     rotation={x=0,y=0,z=0}},
    {id="shotgun",label="Shotgun",capacity=2,reserve=30,cooldown=0.85,
     reload=2.4,damage=22,recoil=4.2,range=35,pellets=8,spread=0.014,
     props={"obj_shotgunwd.prop","obj_shotgunhershel.prop"},
     sound="wpn_hershel_shotgun_blast.wav",flash="fx_muzzleflashshotgun.prop",
     offset={x=0.18,y=-0.23,z=0.47},aim_offset={x=0,y=-0.13,z=0.48},
     rotation={x=0,y=0,z=0}},
    {id="rifle",label="Rifle",capacity=5,reserve=40,cooldown=0.7,
     reload=2.1,damage=100,recoil=2.8,range=150,pellets=1,
     props={"obj_riflescoped.prop","obj_gunrifle.prop","obj_riflecharlotte.prop"},
     sound="wpn_gunshot_real_strong.wav",flash="fx_muzzleflashpistol.prop",
     offset={x=0.18,y=-0.23,z=0.48},aim_offset={x=0,y=-0.12,z=0.5},
     rotation={x=0,y=0,z=0}}
  }
}
